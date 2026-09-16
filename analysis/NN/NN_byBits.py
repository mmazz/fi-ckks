import sys
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import copy

from pathlib import Path
sys.path.append(os.path.abspath("./"))
from utils import config

from utils.args import parse_args, build_filters
from utils.io_utils import load_campaign_data, load_and_filter_campaigns
from utils.df_utils import split_by_gap, stats_by_bit_sdc
from utils.plotters import plot_bit_cat
show = config.show
width = int(config.width)
colors = config.colors
s = config.size+20
c = [colors["red"], colors["blue"]]

dir = "img/"

SAVENAME = "heaan_NN"

CSV_PATH = config.CAMPAIGNS_CSV
CSV_PATH=  "../results_NN/campaigns_start.csv"
DATA_PATH = config.DATA_DIR
DATA_PATH = Path("../results_NN/data")
def main():
    args = parse_args()
    savename =  SAVENAME
    if args.title:
        savename = args.title


    filters = build_filters(args)

    selected = load_and_filter_campaigns(CSV_PATH, filters)

    if selected.empty:
        print(f"[WARN] No campaigns for doMul")

    data = load_campaign_data(selected, DATA_PATH)
    i = 0
    s = config.size
    alpha = config.alpha

    ########################## DATA ################################
    selected = load_and_filter_campaigns(CSV_PATH, filters)
    data = load_campaign_data(selected, DATA_PATH)
    plt.figure()
    coeffs_con_cero = []
    bit_min = 40
    bit_max = 60
# Filtrar primero por rango de bits
    df_filtrado = data[(data["bit"] >= bit_min) & (data["bit"] <= bit_max)]

# Agrupar por coeff
    for coeff, df_coeff in df_filtrado.groupby("coeff"):

        # Si existe algún is_sdc == 0
        if (df_coeff["is_sdc"] == 0).any():
            coeffs_con_cero.append(coeff)

    print(coeffs_con_cero)

    fallan = set(coeffs_con_cero)
    todos = set(data["coeff"].unique())
    no_fallan = todos - fallan

    for k in range(1, 12):
        M = 2**k

        clases_fallo = set(x % M for x in fallan)
        clases_ok = set(x % M for x in no_fallan)

        if clases_fallo.isdisjoint(clases_ok):
            print("Separación perfecta con mod", M)

  #  for coeff, df_coeff in data.sort_values(["coeff", "bit"]).groupby("coeff"):
  #      plt.clf()
  #      plt.scatter(
  #          df_coeff["bit"],
  #          df_coeff["is_sdc"],
  #          marker="o",
  #          label=f"coeff {coeff}"
  #      )

  #  plt.xlabel("bit")
  #  plt.ylabel("is_sdc")
  #  plt.legend()
  #  plt.show()
  #  plt.pause(2)

   # plt.savefig(dir+f"{savename}_flatten.pdf", bbox_inches='tight')
   # plt.savefig(dir+f"{savename}_flatten.png", bbox_inches='tight')
  #  if show:
  #      plt.show()
if __name__ == "__main__":
    main()
