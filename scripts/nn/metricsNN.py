import argparse
import pandas as pd
from pathlib import Path
from sklearn.metrics import accuracy_score, f1_score
parser = argparse.ArgumentParser()


parser.add_argument(
    "directory",
    nargs="?",
    default="results_NN_acc",
    help="Directorio con los resultados"
)

parser.add_argument(
    "campaign_id",
    nargs="?",
    type=int,
    default=9,
    help="ID de campaña"
)
args = parser.parse_args()

directory = Path(f"../../{args.directory}/data")
print(directory)
campaign_id = args.campaign_id

file_path = directory / f"campaign_{campaign_id:06d}.csv.gz"

print(f"Leyendo: {file_path}")

df = pd.read_csv(file_path)
y_true = df["hidden_layer"]
y_pred = df["reduceSum_layer"]

accuracy = accuracy_score(y_true, y_pred)
macro_f1 = f1_score(y_true, y_pred, average="macro")

print(f"Accuracy: {accuracy:.4f}")
print(f"Macro F1: {macro_f1:.4f}")
print(f"Cantidad de datos: {len(df)}")
