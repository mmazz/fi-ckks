"""
MLP 784 -> 64 -> 10 con activación polinómica (aprox. de tanh), pensado para
inferencia homomórfica CKKS.

La activación NO se toca: sigue siendo  p(z) = 0.98*z - 0.23*z^3

Mejoras respecto de la versión original:
  1. Carga de CSV ~50x más rápida (pandas + caché .npy) en vez de np.loadtxt.
  2. Semilla fija -> resultados reproducibles.
  3. BatchNorm antes de la activación, que al exportar se PLIEGA dentro de
     W1/b1. Los 4 CSV exportados quedan con las mismas formas de siempre
     (64x784, 64, 10x64, 10) y tu pipeline CKKS no cambia una línea.
  4. Penalización de rango sobre la pre-activación: el polinomio deja de ser
     monótono en |z| > 1.19 y CAMBIA DE SIGNO en |z| > 2.06. Fuera de ahí la
     red se rompe y el ruido de CKKS se dispara. La penalización mantiene z
     dentro de la zona segura sin tocar el polinomio.
  5. Split de validación (10%): la mejor época se elige por macro F1 de
     validación, no mirando el test.
  6. Accuracy y macro F1 de train y test impresos por época y al final.
  7. Verificación numérica: se recargan los CSV exportados y se hace el
     forward en numpy puro, comparando contra PyTorch. Si el folding o la
     precisión del CSV estuvieran mal, salta acá y no en el circuito CKKS.
"""

import copy
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset

# ----------------------------- Configuración -----------------------------
SEED          = 0
EPOCHS        = 30
BATCH_SIZE    = 128
LR            = 1e-3
WEIGHT_DECAY  = 1e-4      # pesos chicos => menos crecimiento de escala en CKKS
VAL_SPLIT     = 0.1       # 0.0 para entrenar con las 60k y usar la última época
USE_BN        = True      # se pliega en W1/b1 al exportar (export idéntico)
Z_SAFE        = 1.5       # |z| objetivo; el polinomio se da vuelta en 2.0645
LAMBDA_RANGE  = 1e-2      # peso de la penalización de rango (0 = desactivada)
N_CLASSES     = 10

DATA_DIR = Path("data")
OUT_DIR  = DATA_DIR / "weights"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Puntos críticos del polinomio p(z) = 0.98 z - 0.23 z^3
Z_MONOTONE = float(np.sqrt(0.98 / (3 * 0.23)))   # 1.1917: máximo de p
Z_FLIP     = float(np.sqrt(0.98 / 0.23))         # 2.0645: p cambia de signo

torch.manual_seed(SEED)
np.random.seed(SEED)


# ------------------------------ Datos ------------------------------------
def _has_header(path: Path) -> bool:
    with open(path) as f:
        first = f.readline()
    try:
        [float(v) for v in first.strip().split(",")]
        return False
    except ValueError:
        return True


def load_mnist_csv(path: Path):
    """Devuelve (imágenes normalizadas a [-1,1], labels). Cachea en .npy."""
    path = Path(path)
    cache = path.with_suffix(".npy")

    if cache.exists() and cache.stat().st_mtime >= path.stat().st_mtime:
        raw = np.load(cache)
    else:
        skip = 1 if _has_header(path) else 0
        try:
            import pandas as pd
            raw = pd.read_csv(path, header=0 if skip else None).to_numpy()
        except ImportError:
            raw = np.loadtxt(path, delimiter=",", skiprows=skip)
        # MNIST son enteros 0..255: guardar en uint8 achica mucho la caché
        as_u8 = raw.astype(np.uint8)
        np.save(cache, as_u8 if np.array_equal(as_u8, raw) else raw.astype(np.float32))
        raw = np.load(cache)

    labels = torch.tensor(raw[:, 0].astype(np.int64), dtype=torch.long)
    images = torch.tensor(raw[:, 1:].astype(np.float32) / 255.0 * 2.0 - 1.0)
    return images, labels


train_x, train_y = load_mnist_csv(DATA_DIR / "mnist_train.csv")
test_x,  test_y  = load_mnist_csv(DATA_DIR / "mnist_test.csv")

full_train = TensorDataset(train_x, train_y)
if VAL_SPLIT > 0:
    n_val = int(len(full_train) * VAL_SPLIT)
    n_tr  = len(full_train) - n_val
    g = torch.Generator().manual_seed(SEED)
    train_set, val_set = torch.utils.data.random_split(full_train, [n_tr, n_val], generator=g)
else:
    train_set, val_set = full_train, None

test_set = TensorDataset(test_x, test_y)

train_loader = DataLoader(train_set, batch_size=BATCH_SIZE, shuffle=True, drop_last=True)
train_eval_loader = DataLoader(train_set, batch_size=1024, shuffle=False)
val_loader = DataLoader(val_set, batch_size=1024, shuffle=False) if val_set else None
test_loader = DataLoader(test_set, batch_size=1024, shuffle=False)


# ------------------------------ Modelo -----------------------------------
class HomomorphicMLP(nn.Module):
    def __init__(self, use_bn: bool = True):
        super().__init__()
        self.fc1 = nn.Linear(784, 64)
        self.bn = nn.BatchNorm1d(64) if use_bn else nn.Identity()
        self.fc2 = nn.Linear(64, 10)
        if use_bn:
            # arrancar con sigma(z) ~ 0.5 => ~3 sigmas caben en la zona segura
            nn.init.constant_(self.bn.weight, 0.5)

    def forward(self, x, return_z: bool = False):
        z = self.bn(self.fc1(x))            # pre-activación
        h = 0.98 * z - 0.23 * z ** 3        # ACTIVACIÓN polinómica  <- intacta
        out = self.fc2(h)
        return (out, z) if return_z else out


device = "cuda" if torch.cuda.is_available() else "cpu"
model = HomomorphicMLP(USE_BN).to(device)


# ------------------------------ Métricas ---------------------------------
def metrics_from_cm(cm: torch.Tensor):
    """Accuracy, macro F1 y F1 por clase a partir de la matriz de confusión."""
    cm = cm.double()
    tp = cm.diag()
    fp = cm.sum(0) - tp
    fn = cm.sum(1) - tp
    prec = tp / (tp + fp).clamp(min=1e-12)
    rec  = tp / (tp + fn).clamp(min=1e-12)
    f1 = 2 * prec * rec / (prec + rec).clamp(min=1e-12)
    f1[(tp + fp + fn) == 0] = 0.0          # equivalente a zero_division=0
    acc = (tp.sum() / cm.sum().clamp(min=1)).item()
    return acc, f1.mean().item(), f1.numpy()


@torch.no_grad()
def evaluate(model, loader):
    """Devuelve acc, macro F1, F1 por clase y diagnóstico del rango de z."""
    model.eval()
    cm = torch.zeros(N_CLASSES, N_CLASSES, dtype=torch.long)
    z_max, n_out_safe, n_out_flip, n_z = 0.0, 0, 0, 0

    for x, y in loader:
        x, y = x.to(device), y.to(device)
        out, z = model(x, return_z=True)
        preds = out.argmax(1)
        cm += torch.bincount(y * N_CLASSES + preds,
                             minlength=N_CLASSES ** 2).cpu().reshape(N_CLASSES, N_CLASSES)
        az = z.abs()
        z_max = max(z_max, az.max().item())
        n_out_safe += (az > Z_SAFE).sum().item()
        n_out_flip += (az > Z_FLIP).sum().item()
        n_z += az.numel()

    acc, f1, f1_per_class = metrics_from_cm(cm)
    diag = dict(z_max=z_max,
                pct_out_safe=100.0 * n_out_safe / max(n_z, 1),
                pct_out_flip=100.0 * n_out_flip / max(n_z, 1))
    return acc, f1, f1_per_class, diag


# ---------------------------- Entrenamiento ------------------------------
criterion = nn.CrossEntropyLoss()
optimizer = optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)

best_score, best_state, best_epoch = -1.0, None, -1

print(f"device={device} | train={len(train_set)} val={len(val_set) if val_set else 0} "
      f"test={len(test_set)}")
print(f"zona segura |z| <= {Z_SAFE} | p(z) pierde monotonía en {Z_MONOTONE:.4f} "
      f"y cambia de signo en {Z_FLIP:.4f}\n")

for epoch in range(1, EPOCHS + 1):
    model.train()
    total_loss = 0.0
    for x, y in train_loader:
        x, y = x.to(device), y.to(device)

        optimizer.zero_grad()
        out, z = model(x, return_z=True)
        loss = criterion(out, y)
        if LAMBDA_RANGE > 0:
            # solo penaliza lo que se sale de la zona segura
            loss = loss + LAMBDA_RANGE * ((z.abs() - Z_SAFE).clamp(min=0) ** 2).mean()
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
    scheduler.step()

    tr_acc, tr_f1, _, tr_d = evaluate(model, train_eval_loader)
    te_acc, te_f1, _, _    = evaluate(model, test_loader)
    line = (f"Epoch {epoch:2d}/{EPOCHS} | loss {total_loss/len(train_loader):.4f} | "
            f"TRAIN acc {tr_acc*100:6.2f}% F1 {tr_f1:.4f} | "
            f"TEST acc {te_acc*100:6.2f}% F1 {te_f1:.4f}")

    if val_loader is not None:
        va_acc, va_f1, _, _ = evaluate(model, val_loader)
        line += f" | VAL acc {va_acc*100:6.2f}% F1 {va_f1:.4f}"
        score = va_f1
    else:
        score = tr_f1

    line += f" | max|z| {tr_d['z_max']:.2f}"
    print(line)

    if score > best_score:
        best_score, best_epoch = score, epoch
        best_state = copy.deepcopy(model.state_dict())

if best_state is not None:
    model.load_state_dict(best_state)
    print(f"\nMejor época: {best_epoch} "
          f"({'val' if val_loader else 'train'} macro F1 = {best_score:.4f})")


# ------------------------ Reporte final (acc + macro F1) -----------------
tr_acc, tr_f1, tr_f1c, tr_d = evaluate(model, train_eval_loader)
te_acc, te_f1, te_f1c, te_d = evaluate(model, test_loader)

print("\n================= RESULTADOS FINALES =================")
print(f"TRAIN  ->  accuracy: {tr_acc*100:.2f}%   macro F1: {tr_f1:.4f}")
print(f"TEST   ->  accuracy: {te_acc*100:.2f}%   macro F1: {te_f1:.4f}")
if val_loader is not None:
    va_acc, va_f1, _, _ = evaluate(model, val_loader)
    print(f"VAL    ->  accuracy: {va_acc*100:.2f}%   macro F1: {va_f1:.4f}")

print("\nF1 por clase (test):")
print("  " + "  ".join(f"{c}:{f:.3f}" for c, f in enumerate(te_f1c)))

print("\nRango de la pre-activación z (lo que entra al polinomio):")
for name, d in (("train", tr_d), ("test", te_d)):
    print(f"  {name:5s}  max|z| = {d['z_max']:.3f} | "
          f"fuera de |z|>{Z_SAFE}: {d['pct_out_safe']:.3f}% | "
          f"fuera de |z|>{Z_FLIP:.2f} (p cambia de signo): {d['pct_out_flip']:.4f}%")
print("  Si el % fuera del punto de cambio de signo no es ~0, subí LAMBDA_RANGE.")


# ----------- Plegar BatchNorm dentro de W1/b1 y exportar CSVs ------------
def fold_bn(model):
    """BN(W1 x + b1) = W1' x + b1', así el export queda igual que siempre."""
    W1 = model.fc1.weight.detach().cpu().double().numpy()
    b1 = model.fc1.bias.detach().cpu().double().numpy()
    if isinstance(model.bn, nn.BatchNorm1d):
        bn = model.bn
        gamma = bn.weight.detach().cpu().double().numpy()
        beta  = bn.bias.detach().cpu().double().numpy()
        mu    = bn.running_mean.detach().cpu().double().numpy()
        var   = bn.running_var.detach().cpu().double().numpy()
        s = gamma / np.sqrt(var + bn.eps)
        W1 = W1 * s[:, None]
        b1 = b1 * s + beta - s * mu
    W2 = model.fc2.weight.detach().cpu().double().numpy()
    b2 = model.fc2.bias.detach().cpu().double().numpy()
    return W1, b1, W2, b2


W1, b1, W2, b2 = fold_bn(model)
for name, arr in (("W1", W1), ("b1", b1), ("W2", W2), ("b2", b2)):
    np.savetxt(OUT_DIR / f"{name}.csv", arr, delimiter=",", fmt="%.12e")

print(f"\nGuardado en {OUT_DIR}/  ->  "
      f"W1{W1.shape}  b1{b1.shape}  W2{W2.shape}  b2{b2.shape}")


# ------------- Verificación: forward en numpy desde los CSV --------------
def numpy_forward(X, W1, b1, W2, b2):
    z = X @ W1.T + b1
    h = 0.98 * z - 0.23 * z ** 3
    return h @ W2.T + b2


W1r = np.loadtxt(OUT_DIR / "W1.csv", delimiter=",")
b1r = np.loadtxt(OUT_DIR / "b1.csv", delimiter=",")
W2r = np.loadtxt(OUT_DIR / "W2.csv", delimiter=",")
b2r = np.loadtxt(OUT_DIR / "b2.csv", delimiter=",")

X = test_x.double().numpy()
logits_np = numpy_forward(X, W1r, b1r, W2r, b2r)
acc_np = (logits_np.argmax(1) == test_y.numpy()).mean()

model.eval()
with torch.no_grad():
    logits_pt = model(test_x.to(device)).cpu().double().numpy()

print("\n--------- Verificación del export (numpy vs PyTorch) ---------")
print(f"  accuracy desde los CSV : {acc_np*100:.2f}%   (PyTorch: {te_acc*100:.2f}%)")
print(f"  max |diff| en logits   : {np.abs(logits_np - logits_pt).max():.2e}")
print(f"  predicciones distintas : {(logits_np.argmax(1) != logits_pt.argmax(1)).sum()}"
      f" / {len(test_y)}")
print("  Si esto coincide, los CSV representan exactamente la red entrenada.")
