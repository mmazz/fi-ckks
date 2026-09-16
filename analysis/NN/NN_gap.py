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
from utils.df_utils import split_by_gap, stats_by_bit_sdc, stats_by_bit_sdc
from utils.plotters import plot_bit_cat, plot_bit
show = config.show
width = int(config.width)
colors = config.colors
s = config.size+20
c = [colors["red"], colors["blue"]]

dir = "img/"
plt_std = True
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
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 5), sharey=True)
    s = config.size
    alpha = config.alpha

    ########################## DATA ################################
    selected = load_and_filter_campaigns(CSV_PATH, filters)
    data = load_campaign_data(selected, DATA_PATH)

    ########################## STATS ###############################
    stats_gaps, gap = split_by_gap(data, args.logN, args.logSlots)
    stats_aligned   = stats_by_bit_sdc(stats_gaps[stats_gaps["gap_class"] == "aligned"])
    stats_non_aligned = stats_by_bit_sdc(stats_gaps[stats_gaps["gap_class"] == "non_aligned"])

    plot_bit_cat(stats_aligned,     ax=ax1, label_prefix="", color=c[1],  size=s, plot_std=plt_std)
    plot_bit_cat(stats_non_aligned, ax=ax2, label_prefix="", color=c[1],  size=s, plot_std=plt_std)
    print(stats_non_aligned)
    #plt.title(f"NTT={args.withNTT}")

    handles, labels = ax1.get_legend_handles_labels()

    fig.legend(
        handles,
        labels,
        loc="upper center",
        ncol=3  # ajustá según cantidad de elementos
    )
    plt.savefig(dir+f"{savename}.pdf", bbox_inches='tight')
    plt.savefig(dir+f"{savename}.png", bbox_inches='tight')
    if show:
        plt.show()

if __name__ == "__main__":
    main()
