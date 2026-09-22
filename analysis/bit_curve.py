#!/usr/bin/env python3
"""Curva de error por bit: eje x = bit flipeado, eje y = l2_rel promediado sobre coeficientes.

Primero combina las seeds de la misma config en cada (limb, coeff, bit) con la media,
despues combina los coeficientes de cada bit con --stat.

  --split gap   dos subplots: coeficientes con coeff % gap == 0 y el resto,
                con gap = (N/2) / slots = 2^(logN - 1 - logSlots)
  --vary COL    una curva por cada valor de COL (logQ, stage, library, amountBits, seed, limb...)
  --per COL     una figura por cada valor de COL (tipicamente op_step)

Ejemplos:
  python3 bit_curve.py --title decode --where library=heaan stage=decode pipeline=add logQ=60
  python3 bit_curve.py --title logQ   --where stage=decode pipeline=add --vary logQ --xnorm over_q
  python3 bit_curve.py --title add_gap --where stage=add pipeline=add --per op_step --split gap
"""
import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))
from utils.results import load_campaigns, load_data, select, require_single_config  # noqa: E402

FONT = 18
IMG_DIR = Path(__file__).resolve().parent / "img"
COLORS = ["#E31A1C", "#4382B4", "#EE7733", "#31A354", "#AA3377", "#663333", "#66CCEE", "#CCBB44"]
STATS = {"mean": "mean", "median": "median",
         "geomean": lambda x: float(np.exp(np.log(np.maximum(x, 1e-300)).mean()))}
# Metrics that live in [0, 1]: with --stat mean they are probabilities, so they get a
# linear y axis instead of symlog. See load_data() in utils/results.py.
RATE_METRICS = {"is_sdc", "is_masked", "frac_bad", "frac_failed", "detected",
                "misclassified", "sdc_undetected", "false_alarm"}
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


def parse_args():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results", default="../results")
    p.add_argument("--where", nargs="+", default=[], metavar="COL=VAL")
    p.add_argument("--vary", nargs="*", default=[], help="columnas: una curva por combinacion de valores")
    p.add_argument("--per", default=None, help="columna: una figura por valor (ej: op_step)")
    p.add_argument("--split", choices=["none", "gap"], default="none")
    p.add_argument("--metric", default="l2_rel", help="columna de los datos a graficar")
    p.add_argument("--stat", choices=list(STATS), default="mean",
                   help="como combinar los coeficientes de cada bit")
    p.add_argument("--xnorm", choices=["none", "minus_delta", "over_q"], default="none",
                   help="eje x: bit | bit - logDelta | bit / logQ")
    p.add_argument("--drop_coeffs", nargs="*", default=[], help="coeficientes a excluir: 0 N/2 ...")
    p.add_argument("--band", action="store_true", help="sombrea percentil 10-90 entre coeficientes")
    p.add_argument("--title", default="bit_curve")
    p.add_argument("--yscale", choices=["auto", "linear", "log", "symlog"], default="auto",
                   help="auto: linear for the rate metrics (is_sdc, frac_bad, detected, "
                        "misclassified), symlog for the error magnitudes")
    p.add_argument("--show", action="store_true")
    return p.parse_args()


# ------------------------------------------------------------------ #
# Datos
# ------------------------------------------------------------------ #
def load_curve_data(camps, results, vary, drop_coeffs, metric):
    """Una fila por (curva, limb, coeff, bit): seeds ya promediadas. Agrega gap_aligned."""
    keys = [c for c in vary if c in camps.columns]          # 'limb' viene de los datos, no del registry
    groups = camps.groupby(keys) if keys else [((), camps)]
    parts = []
    for _, g in groups:
        cfg = require_single_config(g).iloc[0]              # dentro de una curva solo varian seeds
        N = 1 << int(cfg["logN"])
        gap = (N // 2) // (1 << int(cfg["logSlots"]))
        d = load_data(g, results)
        n_before = len(d)
        d = d[np.isfinite(d[metric].to_numpy())]
        if len(d) < n_before:
            print(f"  {n_before - len(d)} non-finite {metric} rows dropped "
                  f"(use --metric err_bits to keep them, clipped)")
        drop = {N // 2 if c == "N/2" else int(c) for c in drop_coeffs}
        d = d[~d["coeff"].isin(drop)]
        d = (d.groupby(["limb", "coeff", "bit"], as_index=False)[metric].mean())  # promedio entre seeds
        for c in ["logN", "logSlots", "logQ", "logDelta", "stage", "pipeline", *keys]:
            d[c] = cfg[c]
        d["gap"] = gap
        d["gap_aligned"] = (d["coeff"] % gap == 0)
        parts.append(d)
    return pd.concat(parts, ignore_index=True)


def x_values(bits, df, xnorm):
    if xnorm == "minus_delta":
        return bits - df["logDelta"].iloc[0]
    if xnorm == "over_q":
        return bits / df["logQ"].iloc[0]
    return bits


# ------------------------------------------------------------------ #
# Plot
# ------------------------------------------------------------------ #
def plot_curves(ax, data, vary, args, subset_label=""):
    groups = data.groupby(vary) if vary else [(None, data)]
    for i, (val, d) in enumerate(groups):
        # A non-finite value (a flip in a high bit can overflow the decode) makes the mean
        # of that bit inf, and matplotlib drops the point SILENTLY: the curve just stops
        # early and nothing says why. Average over the finite rows and mark those bits.
        finite = np.isfinite(d[args.metric].to_numpy(dtype=float))
        overflow_bits = np.unique(d.loc[~finite, "bit"].to_numpy())
        per_bit = d[finite].groupby("bit")[args.metric]
        y = per_bit.agg(STATS[args.stat])
        x = x_values(y.index.to_numpy(), d, args.xnorm)
        yv = y.to_numpy(dtype=float)
        color = COLORS[i % len(COLORS)]
        label = None
        if vary:
            vals = val if isinstance(val, tuple) else (val,)
            label = ", ".join(f"{k}={v}" for k, v in zip(vary, vals))
        ax.plot(x, yv, marker="o", ms=4, lw=1.8, color=color, label=label)
        if overflow_bits.size:
            ax.plot(x_values(overflow_bits, d, args.xnorm),
                    np.full(overflow_bits.size, 0.97), ls="none", marker="|", ms=9,
                    color=color, alpha=0.8, transform=ax.get_xaxis_transform(), zorder=4,
                    label=None if i else f"bits with non-finite {args.metric}")
            print(f"  {(~finite).sum()} non-finite {args.metric} rows on "
                  f"{overflow_bits.size} bit(s) {list(overflow_bits[:6])}: averaged over the "
                  f"rest, marked at the top (use --metric err_bits to keep them, clipped)")
        if args.band:
            lo, hi = per_bit.quantile(0.1).to_numpy(), per_bit.quantile(0.9).to_numpy()
            ax.fill_between(x, lo, hi, color=color, alpha=0.15, lw=0)

    # Referencias logDelta / logQ solo si son las mismas para todas las curvas
    same_params = data["logDelta"].nunique() == 1 and data["logQ"].nunique() == 1
    for col, name in [("logDelta", r"$\log\Delta$"), ("logQ", r"$\log Q$")]:
        if data[col].nunique() == 1 and (args.xnorm == "none" or same_params):
            ref = x_values(np.array([data[col].iloc[0]]), data, args.xnorm)[0]
            ax.axvline(ref, color="black", ls="--", lw=1)
            ax.text(ref, 1.0, f" {name}", transform=ax.get_xaxis_transform(),
                    va="bottom", ha="center", fontsize=FONT - 4)
    # The top has to be set from the finite values: autoscaling with an inf in the frame
    # leaves the limit at inf and the whole figure collapses into one line.
    finite_vals = data[args.metric].to_numpy(dtype=float)
    finite_vals = finite_vals[np.isfinite(finite_vals)]
    scale = args.yscale
    if scale == "auto":
        scale = "linear" if args.metric in RATE_METRICS else "symlog"
    if scale == "symlog":
        # symlog so a 0 (fully masked fault) is still visible.
        ax.set_yscale("symlog", linthresh=_linthresh(finite_vals))
    else:
        ax.set_yscale(scale)
    if scale == "log":
        pos = finite_vals[finite_vals > 0]
        if pos.size:
            ax.set_ylim(float(pos.min()) / 3.0, float(pos.max()) * 3.0)
    elif args.metric in RATE_METRICS and scale == "linear":
        ax.set_ylim(-0.02, 1.02)
    else:
        top = float(finite_vals.max()) * 3.0 if finite_vals.size else 1.0
        ax.set_ylim(0, top if np.isfinite(top) and top > 0 else float(finite_vals.max()))
    xlabel = {"none": "Bit index", "minus_delta": r"Bit index $-\ \log\Delta$",
              "over_q": r"Bit index / $\log Q$"}[args.xnorm]
    ax.set_xlabel(xlabel, fontsize=FONT)
    ax.set_ylabel(f"{args.stat} {args.metric} over coeffs", fontsize=FONT)
    ax.grid(True, ls="--", alpha=0.3)
    if subset_label:
        ax.set_title(subset_label, fontsize=FONT, pad=26)
    if vary:
        ax.legend(fontsize=FONT - 6, frameon=False)


def _linthresh(values):
    """symlog lineal solo cerca de 0: por debajo del menor error no nulo."""
    pos = values[values > 0]
    return float(10 ** np.floor(np.log10(pos.min()))) if len(pos) else 1e-12


def make_figure(data, vary, args, name):
    if args.split == "gap":
        fig, axes = plt.subplots(1, 2, figsize=(16, 5), sharey=True)
        gap = data["gap"].iloc[0] if data["gap"].nunique() == 1 else "var"
        plot_curves(axes[0], data[data["gap_aligned"]], vary, args, f"coeff % gap == 0  (gap={gap})")
        plot_curves(axes[1], data[~data["gap_aligned"]], vary, args, "coeff % gap != 0")
        axes[1].set_ylabel("")
    else:
        fig, ax = plt.subplots(figsize=(12, 5))
        plot_curves(ax, data, vary, args)

    def show(col):
        vals = data[col].unique()
        return str(vals[0]) if len(vals) == 1 else f"{col}: varios"
    fig.suptitle(f"{show('stage')}  [{show('pipeline')}]", fontsize=FONT - 2,
                 y=1.06 if args.split == "gap" else 1.02)

    IMG_DIR.mkdir(exist_ok=True)
    out = IMG_DIR / name
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", dpi=120)
    print(f"-> {out}.png")
    if args.show:
        plt.show()
    plt.close(fig)


def main():
    args = parse_args()
    filters = {k: parse_value(v) for k, v in (w.split("=", 1) for w in args.where)}
    camps = select(load_campaigns(args.results), **filters)
    if camps.empty:
        sys.exit(f"No finished campaigns match {filters}")

    per_values = sorted(camps[args.per].unique()) if args.per else [None]
    for pv in per_values:
        sub = camps if pv is None else camps[camps[args.per] == pv]
        try:
            data = load_curve_data(sub, args.results, args.vary, args.drop_coeffs, args.metric)
        except ValueError as e:
            sys.exit(f"ERROR: {e}\n  -> add a filter with --where, or use --vary/--per for that columns")
        name = args.title if pv is None else f"{args.title}_{args.per}_{pv}"
        make_figure(data, args.vary, args, name)


if __name__ == "__main__":
    main()
