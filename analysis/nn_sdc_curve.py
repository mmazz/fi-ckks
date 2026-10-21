#!/usr/bin/env python3
"""NN workloads: probability that a bit flip changes the predicted class, per bit.

`misclassified` is 0/1 per injection (class of the faulty run != class of the fault-free
CKKS run), so its mean over every sample of a bit is a probability. All samples of a bit
are pooled: every coefficient, limb, seed and image of the same config.

One panel per stage, in the --stages order. Default: the client-side registers, top row
before sending to the server, bottom row after receiving from it.

  --mode rate    P(SDC) per bit with its 95% Wilson interval (default)
  --mode stack   stacked fractions per bit: masked / tolerable SDC / critical SDC
  --mode map     op_step x bit map of P(SDC), one row per experiment of the --stages (the
                 internal ones: hidden_layer, cheby_tanh3, ...), one column for the aligned
                 coefficients and one for the other ones. Gray: bits not injected.
  --mode tolerance  P(SDC) as a function of E_L2 of the 10 logits instead of the bit, one
                 curve per stage: faults before the network in one panel, faults in the
                 logits (decrypt_*, decode) in the other.

  --split gap    (rate mode) one curve for the coefficients aligned to the gap and one for
                 the other ones, plus P(some logit moves > 0.1 %) on the aligned ones.
                 The same split as bit_curve.py --split gap; with the NN parameters
                 gap = 2, so aligned = even coefficients.

Each panel title carries P(SDC | random bit of the register): the per-bit curve
interpolated over every bit in [0, logQ) and averaged. The sampled bits of a random
campaign are not uniform (dense near logDelta and logQ), so the plain mean of the
samples would be biased; the interpolated mean is not.

Examples:
  python3 nn_sdc_curve.py --title nn_client --where library=heaanNN
  python3 nn_sdc_curve.py --title nn_client_stack --where library=heaanNN --mode stack
  python3 nn_sdc_curve.py --title nn_client --where library=heaanNN --split gap
  python3 nn_sdc_curve.py --title nn_internal --where library=heaanNN --mode map \\
      --stages hidden_layer cheby_tanh3
  python3 nn_sdc_curve.py --title nn_tolerance --where library=heaanNN --mode tolerance
  python3 nn_sdc_curve.py --title nn_enc --where library=heaanNN --stages encrypt_c0 encrypt_c1 --ncols 2
"""
import argparse
import sys
from pathlib import Path

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))
import register_map as rm                                              # noqa: E402
from utils.results import (load_campaigns, load_data, select, require_single_config,  # noqa: E402
                           assign_config_id, parse_value)

CLIENT_STAGES = ["encode", "encrypt_c0", "encrypt_c1", "decrypt_c0", "decrypt_c1", "decode"]

# Panel titles: number of the injection point in the client diagram of the thesis
# (Fig. NN_diag, the one of the DSN paper: 1, 3, 4, 7, 8, 9) + register.
STAGE_LABEL = {"encode": "1: plaintext (encode)", "encrypt_c0": "3: $c_0$ (encrypt)",
               "encrypt_c1": "4: $c_1$ (encrypt)", "decrypt_c0": "7: $c_0$ (before decrypt)",
               "decrypt_c1": "8: $c_1$ (before decrypt)", "decode": "9: plaintext (decode)"}

def comma(v, digits=2):
    """Decimal comma, as in the text of the thesis: 0.37 -> '0,37'."""
    return f"{v:.{digits}f}".replace(".", ",")
# Levels the HEAAN network spends before the logits: W1, x^2, x^3, -0.23*x^3, W2
# (workloads/nn/heaan_nn.cpp). The output registers live mod 2^(logQ - NN_LEVELS*logDelta).
NN_LEVELS = 5
OUTPUT_STAGES = {"decrypt_c0", "decrypt_c1", "decode"}
RATE_CMAP = mcolors.LinearSegmentedColormap.from_list("rate", [rm.GREEN, rm.YELLOW, rm.RED])
# gamma < 1 so that a small but non-zero rate is already visibly yellow, not green.
RATE_NORM = mcolors.PowerNorm(gamma=0.5, vmin=0.0, vmax=1.0)
BAND_COLOR = "#6BAED6"
# --split gap: one color per group of coefficients, the same in every NN figure.
GROUP_COLOR = {"aligned": "#2a78d6", "other": "#eb6834"}
GROUP_MARKER = {"aligned": "o", "other": "^"}
GROUP_LABEL = {"aligned": "aligned coefficients", "other": "other coefficients",
               "all": "all coefficients"}
MOVED_COLOR = "#7a7975"
# Faint reference line: with the output destroyed, a class drawn at random among the 10
# would give P(mis) = 1 - 1/10. A reading of the plateau, not a measurement.
RANDOM_CLASS = 0.9
# --mode map: what each op_step of the network-specific stages holds
# (workloads/nn/heaan_nn.cpp). Even op_steps flip c0 (bx), odd ones c1 (ax).
STEP_LABEL = {
    "hidden_layer": ["input", "input", r"$W_1 x$", r"$W_1 x$",
                     "copy to rotate", "copy to rotate", "rotated", "rotated",
                     "accumulator", "accumulator", "acc. + rotated", "acc. + rotated",
                     r"$+ b_1$", r"$+ b_1$"],
    "cheby_tanh3": [r"$z$", r"$z$", r"$z$ at the level of $z^2$", r"$z$ at the level of $z^2$",
                    r"$z^3$", r"$z^3$", r"$z$ before $\times 0.98$", r"$z$ before $\times 0.98$",
                    r"$0.98 z$", r"$0.98 z$"],
}
STAGE_SHORT = {"hidden_layer": "hidden", "cheby_tanh3": "act."}
# Each sampled bit is drawn as a cell of at most 2*CELL_HALF + 1 bits; the bits nobody
# injected stay gray, so the map does not suggest a value between two samples.
CELL_HALF = 3
MAP_CMAP = plt.get_cmap("Reds").copy()
MAP_CMAP.set_bad("#e8e8e6")
# --mode tolerance: bins of log10 E_L2 of the logits, the range they cover (values outside
# go to the end bins) and the fewest injections a bin needs to be drawn.
TOL_BIN = 0.5
TOL_RANGE = (-8.0, 14.0)
TOL_MIN_N = 30
TOL_STYLE = [("#1baf7a", "o"), ("#6250d6", "s"), ("#c98500", "D")]
Z95 = 1.959964
FONT = 16


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results", default="../results_NN")
    p.add_argument("--where", nargs="+", default=[], metavar="COL=VAL")
    p.add_argument("--stages", nargs="+", default=CLIENT_STAGES,
                   help="one panel per stage, in this order (missing stages are skipped)")
    p.add_argument("--ncols", type=int, default=3)
    p.add_argument("--mode", choices=["rate", "stack", "map", "tolerance"], default="rate")
    p.add_argument("--split", choices=["none", "gap"], default="none",
                   help="rate and map modes: aligned vs other coefficients (gap = (N/2) / slots)")
    p.add_argument("--legend", choices=["top", "none", "only"], default="top",
                   help="rate mode: legend on top of the figure, no legend, or an image with "
                        "only the legend (for figures of one panel that share it)")
    p.add_argument("--title", default="nn_sdc")
    p.add_argument("--show", action="store_true")
    args = p.parse_args()
    if args.split == "gap" and args.mode not in ("rate", "map"):
        p.error("--split gap only applies to --mode rate and --mode map")
    if args.legend != "top" and args.mode != "rate":
        p.error("--legend none / only only apply to --mode rate")
    return args


# ------------------------------------------------------------------ #
# Data
# ------------------------------------------------------------------ #
def select_campaigns(args):
    """Experiments of the --stages that pass --where, checked to be one network config."""
    filters = {k: parse_value(v) for k, v in (w.split("=", 1) for w in args.where)}
    if "stage" in filters:
        sys.exit("ERROR: remove stage from --where; use --stages")
    camps = select(load_campaigns(args.results), **filters)
    camps = camps[camps["stage"].isin(args.stages)]
    if camps.empty:
        sys.exit(f"ERROR: no finished campaigns for stages {args.stages} and {filters}")
    # Every panel (or row) must be the same config except for the stage, the op_step and
    # bitsPerCoeff: HEAAN's encode register and the key-switching registers (mod qQ) are
    # wider than a ciphertext, so their campaigns sweep more bits.
    together = camps.copy()
    together["stage"] = "*"
    together["op_step"] = 0
    together["bitsPerCoeff"] = 0
    try:
        require_single_config(assign_config_id(together))
    except ValueError as exc:
        sys.exit(f"ERROR: the stages differ in more than the stage: {exc}. Add them to --where.")
    return camps


def load_stages(args):
    """{stage: (cfg, data)} for the stages that have finished campaigns."""
    camps = select_campaigns(args)
    missing = [s for s in args.stages if s not in set(camps["stage"])]
    if missing:
        print(f"  no campaigns for {missing}: skipped")
    out = {}
    for stage in [s for s in args.stages if s not in missing]:
        group = camps[camps["stage"] == stage]
        out[stage] = (group.iloc[0], load_data(group, args.results))
        try:
            require_single_config(group)
        except ValueError as exc:
            sys.exit(f"ERROR: stage {stage}: {exc}. Add them to --where.")
    return out


def load_steps(args):
    """[((stage, op_step), cfg, data)] in --stages order, op_steps ascending: one row of the
    map per experiment. The internal stages have one experiment per op_step."""
    camps = select_campaigns(args)
    out = []
    for stage in args.stages:
        for step, group in camps[camps["stage"] == stage].groupby("op_step"):
            try:
                require_single_config(group)
            except ValueError as exc:
                sys.exit(f"ERROR: {stage} op_step {step}: {exc}. Add them to --where.")
            out.append(((stage, int(step)), group.iloc[0], load_data(group, args.results)))
    missing = [s for s in args.stages if s not in {key[0] for key, _, _ in out}]
    if missing:
        print(f"  no campaigns for {missing}: skipped")
    return out


def wilson(k, n, z=Z95):
    """95% Wilson interval of a proportion. Unlike p +- std it stays inside [0, 1] and
    does not collapse to zero width when every sample is 0 or 1."""
    p = k / n
    den = 1 + z * z / n
    center = (p + z * z / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return center - half, center + half

def per_bit(data):
    """One row per bit: n, P(SDC), its interval, and the three-way split.

    Each row of a collapsed dir is one (limb, coeff, bit) cell with n_seeds injections, and
    misclassified / tolerable_sdc are the fraction of them that hit, so rate x n_seeds
    gives back the exact counts.
    """
    w = data["n_seeds"] if "n_seeds" in data.columns else pd.Series(1.0, index=data.index)
    d = pd.DataFrame({"bit": data["bit"], "n": w,
                      "k": data["misclassified"] * w, "k_tol": data["tolerable_sdc"] * w})
    out = d.groupby("bit")[["n", "k", "k_tol"]].sum()
    out["rate"] = out["k"] / out["n"]
    out["lo"], out["hi"] = wilson(out["k"].to_numpy(float), out["n"].to_numpy(float))
    out["tolerable"] = out["k_tol"] / out["n"]
    out["masked"] = 1.0 - out["rate"] - out["tolerable"]
    return out.reset_index()


def gap_of(cfg):
    """decode reads only the coefficients that are multiples of gap = (N/2) / slots."""
    return 2 ** (int(cfg["logN"]) - 1 - int(cfg["logSlots"]))


def split_gap(data, cfg):
    """{"aligned": rows with coeff % gap == 0, "other": the rest}, the split of
    bit_curve.py --split gap. With the NN parameters gap = 2: even / odd coefficients."""
    aligned = data["coeff"] % gap_of(cfg) == 0
    return {"aligned": data[aligned], "other": data[~aligned]}

def coeff_groups(data, cfg, split):
    """--split none: {"all": every row}; --split gap: split_gap."""
    return {"all": data} if split == "none" else split_gap(data, cfg)

def encode_shift(cfg):
    """HEAAN adds the encoded plaintext to the encryption mod qQ and then shifts right by
    logQ, so bit logQ + k of the encode register acts as bit k of a ciphertext. 0 elsewhere."""
    heaan_encode = str(cfg["library"]).startswith("heaan") and cfg["stage"] == "encode"
    return int(cfg["logQ"]) if heaan_encode else 0



def register_width(cfg):
    """Bits the fault can land in: the width of the register at the injection point.
    HEAAN: logQ for the input ciphertext, logQ - NN_LEVELS*logDelta for the logits
    (decrypt_*, decode), 2*logQ for encode (mod qQ; its lower logQ bits are rounded away).
    OpenFHE: logQ, the first limb."""
    if str(cfg["library"]).startswith("heaan") and cfg["stage"] in OUTPUT_STAGES:
        return int(cfg["logQ"]) - NN_LEVELS * int(cfg["logDelta"])
    return int(cfg["logQ"]) + encode_shift(cfg)

def shift_encode(data, cfg):
    """(data, shift): on the HEAAN encode register keep the bits at or above logQ and move
    them down by logQ, so the x axis reads like the one of encrypt_c0 (see encode_shift).
    The lower logQ bits are rounded away by the encryption: the largest P(mis) among them
    is printed, so that dropping them can be checked. Other stages: unchanged, shift 0."""
    shift = encode_shift(cfg)
    if not shift:
        return data, 0
    low = data[data["bit"] < shift]
    if not low.empty:
        print(f"  {cfg['stage']}: dropped bits below logQ = {shift}, "
              f"largest P(mis) among them = {per_bit(low)['rate'].max():.3f}")
    out = data[data["bit"] >= shift].copy()
    out["bit"] -= shift
    return out, shift

def register_rate(curve, log_q):
    """P(SDC) for a bit drawn uniformly from the register at the injection point, [0, log_q): interpolate the sampled bits."""
    bits = np.arange(int(log_q))
    return float(np.interp(bits, curve["bit"], curve["rate"]).mean())


# ------------------------------------------------------------------ #
# Plot
# ------------------------------------------------------------------ #
def mark_params(ax, cfg, shifted=0):
    """logDelta and the top of the register W. On the HEAAN encode register both sit logQ
    bits higher (encode_shift), unless the curve was already moved down by `shifted` bits."""
    s = encode_shift(cfg) - shifted
    for val, name in [(cfg["logDelta"] + s, r"$\log\Delta$"),
                      (register_width(cfg) - shifted, r"$W$")]:
        ax.axvline(val, color="black", lw=0.8, ls="--", alpha=0.7, zorder=4)
        ax.text(val, 1.02, name, transform=ax.get_xaxis_transform(),
                ha="center", va="bottom", fontsize=FONT - 5)


def draw_rate(ax, curve):
    x = curve["bit"].to_numpy()
    ax.fill_between(x, curve["lo"], curve["hi"], color=BAND_COLOR, alpha=0.45, lw=0, zorder=2)
    ax.scatter(x, curve["rate"], c=curve["rate"].to_numpy(), cmap=RATE_CMAP, norm=RATE_NORM,
               s=28, edgecolors="black", linewidths=0.3, zorder=3)
    ax.set_ylim(-0.05, 1.05)
    ax.set_yticks([0, 0.5, 1])
    ax.set_yticklabels(["0", "0,5", "1"])


def draw_split(ax, data, cfg):
    """P(mis) per bit for the aligned and the other coefficients, each with its Wilson band,
    plus P(some logit moves > 0.1 %) = P(mis) + P(tolerable SDC) on the aligned ones.

    The moved curve uses only the aligned coefficients: on the c0 output stages the other
    ones are masked, so a pooled curve would plateau at the fraction of aligned
    coefficients in the sample (about 0.53), not at a property of the network."""
    groups = split_gap(data, cfg)
    moved = per_bit(groups["aligned"])
    ax.plot(moved["bit"], moved["rate"] + moved["tolerable"], color=MOVED_COLOR, lw=1.4,
            ls="--", zorder=2)
    for name, sub in groups.items():
        curve = per_bit(sub)
        x = curve["bit"].to_numpy()
        ax.fill_between(x, curve["lo"], curve["hi"], color=GROUP_COLOR[name], alpha=0.18,
                        lw=0, zorder=2)
        ax.plot(x, curve["rate"], color=GROUP_COLOR[name], marker=GROUP_MARKER[name],
                lw=1.8, ms=4.5, zorder=3)
    ax.axhline(RANDOM_CLASS, color="#bdbcb6", lw=0.8, zorder=1)
    ax.set_ylim(-0.05, 1.05)
    ax.set_yticks([0, 0.5, RANDOM_CLASS, 1])
    ax.set_yticklabels(["0", "0,5", "0,9", "1"])


def draw_stack(ax, curve):
    x = curve["bit"].to_numpy()
    ax.stackplot(x, curve["masked"], curve["tolerable"], curve["rate"],
                 colors=[rm.GREEN, rm.YELLOW, rm.RED], alpha=0.9, zorder=2,
                 labels=["Masked", "Tolerable SDC", "Misclassification"])
    ax.set_ylim(0, 1)
    ax.set_yticks([0, 0.5, 1])

def legend_handles(args):
    """Handles of the rate-mode legend. All of them are proxies, so they do not depend on
    the data and the legend can also be drawn on its own (--legend only)."""
    if args.split == "gap":
        handles = [Line2D([], [], color=GROUP_COLOR[g], marker=GROUP_MARKER[g], lw=1.8, ms=4.5,
                          label=GROUP_LABEL[g]) for g in ("aligned", "other")]
        handles.append(Line2D([], [], color=MOVED_COLOR, ls="--", lw=1.4,
                              label="some logit moves > 0.1 % (aligned)"))
        return handles
    # Proxies: the scatter is colored point by point, its own handle would be green.
    return [Line2D([], [], ls="none", marker="o", mfc=rm.RED, mec="black", mew=0.3,
                   label=r"$P(\mathrm{mis})$ per bit"),
            Patch(facecolor=BAND_COLOR, alpha=0.45, label="95% Wilson CI")]


def plot_legend(args):
    """--legend only: an image with nothing but the legend, in one row."""
    handles = legend_handles(args)
    fig = plt.figure(figsize=(0.1, 0.1))
    fig.legend(handles=handles, loc="center", ncol=len(handles), frameon=False,
               fontsize=FONT - 4)
    return fig

def plot(stages, args):
    n = len(stages)
    ncols = min(args.ncols, n)
    nrows = -(-n // ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.2 * ncols, 3.4 * nrows),
                             sharex=False, sharey=True, squeeze=False)
    n_min = {}      # fewest injections behind any bit of each panel
    p_reg = {}      # P(SDC | uniformly random bit of the register), per panel
    for i, (ax, (stage, (cfg, data))) in enumerate(zip(axes.flat, stages.items())):
        data, shifted = shift_encode(data, cfg)
        curve = per_bit(data)
        n_min[stage] = int(curve["n"].min())
        if args.split == "gap":
            draw_split(ax, data, cfg)
        else:
            (draw_rate if args.mode == "rate" else draw_stack)(ax, curve)
        mark_params(ax, cfg, shifted)
        # interpolated over every bit of the register at the injection point and averaged
        # (dense near logDelta and logQ), so the plain mean of the samples would be biased.
        p_reg[stage] = register_rate(curve, register_width(cfg) - shifted)
        # x label on the panels with no panel below them
        if i + ncols >= n:
            ax.set_xlabel(r"Bit index $-\ \log Q$" if shifted else "Bit index",
                          fontsize=FONT - 2)
        ax.set_title(f"{STAGE_LABEL.get(stage, stage)}  (P = {comma(p_reg[stage])})",
                       fontsize=FONT - 3, pad=20)
        ax.grid(alpha=0.3)
        # Output registers are only log q_l = 70 bits wide: crop so that the window is
        # readable. The control points above (up to bitsPerCoeff) are all masked.
        if stage in OUTPUT_STAGES:
            ax.set_xlim(-3, register_width(cfg) + 30)
        ax.tick_params(labelsize=FONT - 5)
    for ax in axes.flat[n:]:
        ax.set_visible(False)
    for ax in axes[:, 0]:
        ax.set_ylabel(r"$P(\mathrm{mis})$" if args.mode == "rate" else "Fraction", fontsize=FONT - 2)
    if args.split == "gap":
        handles = [Line2D([], [], color=GROUP_COLOR[g], marker=GROUP_MARKER[g], lw=1.8, ms=4.5,
                          label=GROUP_LABEL[g]) for g in ("aligned", "other")]
        handles.append(Line2D([], [], color=MOVED_COLOR, ls="--", lw=1.4,
                              label="some logit moves > 0.1 % (aligned)"))
    if args.mode == "rate":
        handles = legend_handles(args)
    else:
        handles, _ = axes.flat[0].get_legend_handles_labels()
    if args.legend == "top":
        fig.legend(handles=handles, loc="upper center", ncol=len(handles), frameon=False,
                   fontsize=FONT - 4, bbox_to_anchor=(0.5, 1.05))
    fig.tight_layout()

    return fig, n_min, p_reg


# ------------------------------------------------------------------ #
# --mode map
# ------------------------------------------------------------------ #
def row_label(stage, step):
    """'hidden 4: copy to rotate ($c_0$)'; stages without STEP_LABEL get 'mul 4'."""
    names = STEP_LABEL.get(stage, [])
    short = STAGE_SHORT.get(stage, stage)
    if step >= len(names):
        return f"{short} {step}"
    return f"{short} {step}: {names[step]} ({'$c_1$' if step % 2 else '$c_0$'})"


def bit_cells(curve, width):
    """One row of the map: P(SDC) per bit in [0, width), NaN where nothing was injected.
    Each sampled bit covers up to CELL_HALF bits on each side, never past the midpoint
    with the next sampled bit."""
    row = np.full(width, np.nan)
    b = curve["bit"].to_numpy(int)
    mids = np.concatenate([[b[0] - CELL_HALF], (b[1:] + b[:-1]) / 2, [b[-1] + CELL_HALF]])
    for j, (bit, rate) in enumerate(zip(b, curve["rate"].to_numpy(float))):
        lo = int(max(bit - CELL_HALF, np.ceil(mids[j]), 0))
        hi = int(min(bit + CELL_HALF, np.floor(mids[j + 1]), width - 1))
        row[lo:hi + 1] = rate
    return row


def edges(curve):
    """(first bit with P >= 0.1, last bit with P >= 0.05, median P between them, sampled
    bits between them with P < 0.05), the numbers the text quotes for each row of the map.
    The last one flags a masked hole: [first, last] is then not one band.
    (None, None, 0, 0) if nothing breaks."""
    hit = curve[curve["rate"] >= 0.1]
    if hit.empty:
        return None, None, 0.0, 0
    first = int(hit["bit"].min())
    last = int(curve.loc[curve["rate"] >= 0.05, "bit"].max())
    inside = curve[(curve["bit"] >= first) & (curve["bit"] <= last)]
    return first, last, float(inside["rate"].median()), int((inside["rate"] < 0.05).sum())

def plot_map(steps, split):
    """Map op_step x bit: one row per (stage, op_step). One panel over every coefficient
    (--split none) or one per group, aligned | other (--split gap)."""
    width = max(int(cfg["bitsPerCoeff"]) for _, cfg, _ in steps)
    n = len(steps)
    groups = ("all",) if split == "none" else ("aligned", "other")
    fig, axes = plt.subplots(1, len(groups), figsize=(6.5 * len(groups), 1.6 + 0.34 * n),
                             sharey=True, squeeze=False)
    axes = axes[0]
    summary = {}
    for ax, group in zip(axes, groups):
        grid = np.full((n, width), np.nan)
        for i, (key, cfg, data) in enumerate(steps):
            curve = per_bit(coeff_groups(data, cfg, split)[group])
            grid[i] = bit_cells(curve, width)
            row = summary.setdefault(key, {"n": int(curve["n"].min())})
            row["n"] = min(row["n"], int(curve["n"].min()))   # fewest injections behind a bit
            row[group] = edges(curve)
        mesh = ax.pcolormesh(np.arange(width + 1), np.arange(n + 1), np.ma.masked_invalid(grid),
                             cmap=MAP_CMAP, vmin=0, vmax=1, shading="flat", rasterized=True)
        # one horizontal rule between stages
        for i in range(1, n):
            if steps[i][0][0] != steps[i - 1][0][0]:
                ax.axhline(i, color="black", lw=1.2)
        log_delta = int(steps[0][1]["logDelta"])
        ax.axvline(log_delta, color="black", lw=0.8, ls="--")
        ax.text(log_delta, 1.0, r"$\log\Delta$", transform=ax.get_xaxis_transform(),
                ha="center", va="bottom", fontsize=FONT - 5)
        ax.set_title(GROUP_LABEL[group], fontsize=FONT - 3, pad=20)
        ax.set_xlim(0, width)
        ax.set_xlabel("Bit index", fontsize=FONT - 2)
        ax.tick_params(labelsize=FONT - 5)
    axes[0].set_ylim(n, 0)
    axes[0].set_yticks(np.arange(n) + 0.5)
    axes[0].set_yticklabels([row_label(*key) for key, _, _ in steps], fontsize=FONT - 6)
    cbar = fig.colorbar(mesh, ax=axes, fraction=0.025, pad=0.02)
    cbar.set_label(r"$P(\mathrm{mis})$", fontsize=FONT - 3)
    cbar.set_ticks([0, 0.5, RANDOM_CLASS, 1])
    cbar.set_ticklabels(["0", "0,5", "0,9", "1"])
    cbar.ax.tick_params(labelsize=FONT - 5)
    return fig, summary


def print_map_summary(summary):
    """Per row and group: first, last, plateau and holes (see edges)."""
    def fmt(e):
        first, last, plateau, holes = e
        if first is None:
            return f"{'-':>5s} {'-':>5s} {0.0:5.2f} {'':>5s}"
        return f"{first:5d} {last:5d} {plateau:5.2f} {holes if holes else '':>5}"
    groups = [g for g in ("all", "aligned", "other") if g in next(iter(summary.values()))]
    print(f"  {'':16s} " + "  ".join(f"{g + ': first  last     P holes':>31s}" for g in groups)
          + "  min n/bit")
    for (stage, step), s in summary.items():
        print(f"  {stage:13s} {step:2d}   " + "  ".join(f"      {fmt(s[g])}" for g in groups)
              + f"  {s['n']:5d}")

# ------------------------------------------------------------------ #
# --mode tolerance
# ------------------------------------------------------------------ #
def tolerance_curve(data):
    """P(SDC) per bin of log10 E_L2 of the logits, with its Wilson interval.

    Injections with E_L2 = 0 (masked) have no bin and are left out. A non-finite E_L2 goes
    into the last bin: that run counts as a misclassification anyway (apps/fi_main.cpp).
    In a collapsed dir a row is one (limb, coeff, bit) cell averaged over n_seeds; the NN
    campaigns have one seed per image, so there a row is one injection."""
    w = data["n_seeds"] if "n_seeds" in data.columns else pd.Series(1.0, index=data.index)
    l2 = data["l2_rel"].astype(float)
    keep = l2 != 0                       # NaN != 0, so a NaN output is kept
    l2 = l2[keep].where(np.isfinite(l2[keep]), 10.0 ** TOL_RANGE[1])
    lg = np.log10(l2).clip(*TOL_RANGE)
    bins = pd.cut(lg, np.arange(TOL_RANGE[0], TOL_RANGE[1] + TOL_BIN, TOL_BIN),
                  include_lowest=True)
    d = pd.DataFrame({"bin": bins, "n": w[keep], "k": data.loc[keep, "misclassified"] * w[keep]})
    out = d.groupby("bin", observed=True)[["n", "k"]].sum()
    out = out[out["n"] >= TOL_MIN_N]
    out["center"] = [iv.mid for iv in out.index]
    out["rate"] = out["k"] / out["n"]
    out["lo"], out["hi"] = wilson(out["k"].to_numpy(float), out["n"].to_numpy(float))
    return out.reset_index(drop=True)


def plot_tolerance(stages):
    """Two panels: faults before the network (the error crosses it) and faults in the
    logits (decrypt_*, decode: only the logit of the correct class is hit)."""
    panels = [("fault before the network", [s for s in stages if s not in OUTPUT_STAGES]),
              ("fault in the logits", [s for s in stages if s in OUTPUT_STAGES])]
    panels = [(title, names) for title, names in panels if names]
    fig, axes = plt.subplots(1, len(panels), figsize=(6.6 * len(panels), 4.8), sharey=True,
                             squeeze=False)
    curves = {}
    for ax, (title, names) in zip(axes[0], panels):
        for (color, marker), stage in zip(TOL_STYLE, names):
            c = curves[stage] = tolerance_curve(stages[stage][1])
            x = 10.0 ** c["center"]
            ax.fill_between(x, c["lo"], c["hi"], color=color, alpha=0.18, lw=0, zorder=2)
            ax.plot(x, c["rate"], color=color, marker=marker, ms=5, lw=1.8, zorder=3,
                    label=STAGE_LABEL.get(stage, stage))
        ax.set_xscale("log")
        # E_L2 = 1: the error is as large as the logits themselves
        ax.axvline(1.0, color="black", lw=0.8, ls=":", zorder=1)
        ax.axhline(RANDOM_CLASS, color="#bdbcb6", lw=0.8, zorder=1)
        ax.set_title(title, fontsize=FONT - 3)
        ax.set_xlabel(r"$E_{L_2}$ of the logits", fontsize=FONT - 2)
        ax.grid(alpha=0.3)
        ax.tick_params(labelsize=FONT - 5)
        ax.legend(loc="upper left", frameon=False, fontsize=FONT - 6)
    axes[0][0].set_ylabel(r"$P(\mathrm{mis})$", fontsize=FONT - 2)
    axes[0][0].set_ylim(-0.05, 1.05)
    axes[0][0].set_yticks([0, 0.5, RANDOM_CLASS, 1])
    axes[0][0].set_yticklabels(["0", "0,5", "0,9", "1"])
    fig.tight_layout()
    return fig, curves


def print_tolerance(curves):
    """P(SDC) per bin (center of log10 E_L2), one column per stage, and per stage where the
    class starts to change: between the upper edge of the last bin with P <= 0.05 and the
    lower edge of the first bin with P > 0.05. Empty bins in between (no injection landed
    there) widen that interval; it is not a threshold measured to TOL_BIN."""
    table = pd.DataFrame({s: c.set_index("center")["rate"] for s, c in curves.items()})
    table.index = table.index.round(2)
    print(table.round(2).to_string(na_rep="."))
    for stage, c in curves.items():
        over = c.index[c["rate"] > 0.05]
        if not len(over):
            print(f"  {stage:12s} P <= 0.05 in every bin")
            continue
        below = c.loc[: over[0] - 1]
        lo = below["center"].max() + TOL_BIN / 2 if len(below) else float("nan")
        hi = c.loc[over[0], "center"] - TOL_BIN / 2
        print(f"  {stage:12s} class starts to change between E_L2 = 10^{lo:.1f} and 10^{hi:.1f}")


def main():
    args = parse_args()
    if args.legend == "only":
        fig = plot_legend(args)          # no data needed
    elif args.mode == "map":
        fig, summary = plot_map(load_steps(args), args.split)
        print_map_summary(summary)
    elif args.mode == "tolerance":
        fig, curves = plot_tolerance(load_stages(args))
        print_tolerance(curves)
    else:
        fig, n_min, p_reg = plot(load_stages(args), args)
        print(f"  {'stage':12s} {'min n/bit':>10s} {'P(SDC|reg)':>11s}")
        for stage, n in n_min.items():
            print(f"  {stage:12s} {n:10d} {p_reg[stage]:11.3f}")

    rm.IMG_DIR.mkdir(parents=True, exist_ok=True)
    out = rm.IMG_DIR / args.title
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", dpi=150)
    print(f"-> {out}.png / .pdf")
    if args.show:
        plt.show()
    plt.close(fig)


if __name__ == "__main__":
    main()
