#!/usr/bin/env python3
"""Mapa de registro: cada coeficiente en el eje x, cada bit en el eje y, un circulo por
(coeff, bit) coloreado segun el MREP = max relative error por slot, en % (linf_rel * 100).

Combina (mediana / media / max) las seeds de la MISMA config, y hace una figura
por cada op_step encontrado.

Ejemplos:
  python3 register_analysis.py --results ../../results --title mul \
      --where library=heaan stage=mul "pipeline=add; mul" logN=6 --op_step all

  python3 register_analysis.py --results ../../results --title rescale \
      --where library=heaan stage=rescale "pipeline=mul x2" --op_step 0-3 --stat max
"""
import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.lines import Line2D
import numpy as np

sys.path.append(str(Path(__file__).resolve().parent.parent))
from utils.results import load_campaigns, load_data, select, require_single_config  # noqa: E402

# ------------------------------------------------------------------ #
# Categorias de MREP (en %). Ajusta los umbrales aca.
# ------------------------------------------------------------------ #
MASKED_PCT = 0.1      # < 0.1 %          -> Masked
MINOR_PCT = 10.0      # 0.1 % .. 10 %    -> Minor SDC
MODERATE_PCT = 100.0  # 10 % .. 100 %    -> Moderate SDC ;  > 100 % -> Severe (gradiente)

GREEN, YELLOW, ORANGE, RED, NOCOLOR = "#008000", "#FFD700", "#FFA500", "#FF0000", "#BBBBBB"
SEVERE_CMAP = mcolors.LinearSegmentedColormap.from_list("severe", [RED, "black"])

FONT = 20
IMG_DIR = Path(__file__).resolve().parent.parent / "img"


# ------------------------------------------------------------------ #
# CLI
# ------------------------------------------------------------------ #
def parse_value(v):
    for cast in (int, float):
        try:
            return cast(v)
        except ValueError:
            pass
    return v


def parse_op_steps(spec, available):
    """'all' | '5' | '0,5,10' | '0-25'"""
    if spec == "all":
        return sorted(available)
    steps = set()
    for part in spec.split(","):
        if "-" in part:
            a, b = map(int, part.split("-"))
            steps.update(range(a, b + 1))
        else:
            steps.add(int(part))
    return sorted(steps)


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results", default="../../results", help="directorio de resultados")
    p.add_argument("--where", nargs="+", default=[], metavar="COL=VAL",
                   help='filtros exactos sobre campaigns_start, ej: stage=mul "pipeline=add; mul"')
    p.add_argument("--op_step", default="all", help="all | 5 | 0,5,10 | 0-25")
    p.add_argument("--stat", default="median", choices=["median", "mean", "max"],
                   help="como combinar las seeds en cada (coeff, bit)")
    p.add_argument("--title", default="register")
    p.add_argument("--no_legend", action="store_true")
    p.add_argument("--show", action="store_true")
    return p.parse_args()


# ------------------------------------------------------------------ #
# Datos
# ------------------------------------------------------------------ #
def mrep_per_cell(data, stat):
    """Una fila por (limb, coeff, bit) con el MREP combinado entre seeds."""
    data = data.assign(mrep=data["linf_rel"].astype(float) * 100.0)
    return data.groupby(["limb", "coeff", "bit"], as_index=False)["mrep"].agg(stat)


def mrep_colors(mrep, vmax):
    """RGBA por punto: color por categoria; los severos en gradiente log entre 100 % y vmax."""
    rgba = np.tile(mcolors.to_rgba(NOCOLOR), (len(mrep), 1))     # NaN -> gris
    for mask, color in [(mrep < MASKED_PCT, GREEN),
                        ((mrep >= MASKED_PCT) & (mrep < MINOR_PCT), YELLOW),
                        ((mrep >= MINOR_PCT) & (mrep < MODERATE_PCT), ORANGE)]:
        rgba[mask] = mcolors.to_rgba(color)
    severe = mrep >= MODERATE_PCT
    if severe.any():
        norm = mcolors.LogNorm(vmin=MODERATE_PCT, vmax=max(vmax, MODERATE_PCT * 1.01), clip=True)
        rgba[severe] = SEVERE_CMAP(norm(mrep[severe]))
    return rgba


# ------------------------------------------------------------------ #
# Plot
# ------------------------------------------------------------------ #
def plot_register_map(ax, cells, cfg, vmax):
    N = 1 << int(cfg["logN"])
    n_limbs = int(cells["limb"].max()) + 1
    n_bits = int(cfg["bitsPerCoeff"])
    n_x = N * n_limbs

    x = cells["limb"].to_numpy() * N + cells["coeff"].to_numpy()
    y = cells["bit"].to_numpy()
    c = mrep_colors(cells["mrep"].to_numpy(), vmax)

    # Tamano del circulo: que entre en la celda (coeff, bit) sin pisarse
    fig = ax.figure
    bbox = ax.get_window_extent().transformed(fig.dpi_scale_trans.inverted())
    cell_pt = min(bbox.width * 72 / n_x, bbox.height * 72 / n_bits)
    size = (0.85 * cell_pt) ** 2

    ax.scatter(x, y, c=c, s=size, linewidths=0, zorder=3)
    ax.set_xlim(-0.5, n_x - 0.5)
    ax.set_ylim(-0.5, n_bits - 0.5)

    # Eje x: cada coeficiente es una columna; ticks legibles
    step = 1 if n_x <= 32 else (2 if n_x <= 64 else max(1, n_x // 32))
    ax.set_xticks(range(0, n_x, step))
    ax.set_xticklabels([str(i % N) for i in range(0, n_x, step)], rotation=90, fontsize=FONT - 8)
    for l in range(1, n_limbs):                      # separadores de limb (OpenFHE)
        ax.axvline(l * N - 0.5, color="black", lw=1)

    # Eje y: referencias en logDelta y logQ
    ax.set_yticks(range(0, n_bits, 8 if n_bits <= 128 else 32))
    for val, name in [(cfg["logDelta"], r"$\log\Delta$"), (cfg["logQ"], r"$\log Q$")]:
        if val < n_bits:
            ax.axhline(val - 0.5, color="black", lw=1, ls="--", zorder=4)
            ax.text(n_x - 0.5, val - 0.5, f" {name}", va="center", ha="left",
                    fontsize=FONT - 6, clip_on=False)

    ax.set_xlabel("Coefficient" + (" (per limb)" if n_limbs > 1 else ""), fontsize=FONT)
    ax.set_ylabel("i-th bit of register", fontsize=FONT)
    ax.tick_params(axis="y", labelsize=FONT - 4)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def add_legend(fig, ax, vmax):
    handles = [
        Line2D([], [], marker="o", ls="", color=GREEN,  ms=12, label=f"Masked (<{MASKED_PCT:g}%)"),
        Line2D([], [], marker="o", ls="", color=YELLOW, ms=12, label=f"Minor ({MASKED_PCT:g}–{MINOR_PCT:g}%)"),
        Line2D([], [], marker="o", ls="", color=ORANGE, ms=12, label=f"Moderate ({MINOR_PCT:g}–{MODERATE_PCT:g}%)"),
    ]
    ax.legend(handles=handles, loc="lower left", bbox_to_anchor=(0, 1.02), ncol=3,
              frameon=False, fontsize=FONT - 6, handletextpad=0.2, columnspacing=1.0)
    if vmax > MODERATE_PCT:
        sm = plt.cm.ScalarMappable(cmap=SEVERE_CMAP, norm=mcolors.LogNorm(MODERATE_PCT, vmax))
        cb = fig.colorbar(sm, ax=ax, pad=0.07, fraction=0.04)
        cb.set_label("Severe SDC: MREP (%)", fontsize=FONT - 6)
        cb.ax.tick_params(labelsize=FONT - 8)


# ------------------------------------------------------------------ #
def main():
    args = parse_args()
    filters = dict(w.split("=", 1) for w in args.where)
    filters = {k: parse_value(v) for k, v in filters.items()}

    camps = select(load_campaigns(args.results), **filters)
    if camps.empty:
        sys.exit(f"No hay campanias terminadas que cumplan {filters}")

    steps = parse_op_steps(args.op_step, camps["op_step"].unique())
    camps = camps[camps["op_step"].isin(steps)]

    # Primero cargo todo: la escala de color (vmax) es COMUN a todas las figuras,
    # asi los op_step se pueden comparar a ojo.
    per_step = {}
    for step, group in camps.groupby("op_step"):
        cfg = require_single_config(group).iloc[0]      # solo pueden variar las seeds
        cells = mrep_per_cell(load_data(group, args.results), args.stat)
        per_step[step] = (cfg, cells, group["seed"].nunique())
    vmax = max(float(cells["mrep"].max()) for _, cells, _ in per_step.values())

    IMG_DIR.mkdir(exist_ok=True)
    for step, (cfg, cells, n_seeds) in per_step.items():
        fig, ax = plt.subplots(figsize=(14, 8))
        plot_register_map(ax, cells, cfg, vmax)
        if not args.no_legend:
            add_legend(fig, ax, vmax)
        ax.set_title(f"{cfg['stage']}  op_step={step}  [{cfg['pipeline']}]  "
                     f"{args.stat} of {n_seeds} seeds", fontsize=FONT - 4, pad=40)

        out = IMG_DIR / f"{args.title}_op_step_{step}"
        fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
        fig.savefig(out.with_suffix(".png"), bbox_inches="tight", dpi=120)
        print(f"op_step={step}: {len(cells)} celdas, {n_seeds} seeds -> {out}.png")
        if args.show:
            plt.show()
        plt.close(fig)


if __name__ == "__main__":
    main()
