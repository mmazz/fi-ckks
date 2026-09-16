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
        per_bit = d.groupby("bit")[args.metric]
        y = per_bit.agg(STATS[args.stat])
        x = x_values(y.index.to_numpy(), d, args.xnorm)
        yv = y.to_numpy(dtype=float)
        color = COLORS[i % len(COLORS)]
        label = None
        if vary:
            vals = val if isinstance(val, tuple) else (val,)
            label = ", ".join(f"{k}={v}" for k, v in zip(vary, vals))
        ax.plot(x, yv, marker="o", ms=4, lw=1.8, color=color, label=label)
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

    ax.set_yscale("symlog", linthresh=_linthresh(data[args.metric]))   # symlog: el 0 (masked) se ve
    ax.set_ylim(bottom=0)
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
        sys.exit(f"No hay campanias terminadas que cumplan {filters}")

    per_values = sorted(camps[args.per].unique()) if args.per else [None]
    for pv in per_values:
        sub = camps if pv is None else camps[camps[args.per] == pv]
        try:
            data = load_curve_data(sub, args.results, args.vary, args.drop_coeffs, args.metric)
        except ValueError as e:
            sys.exit(f"ERROR: {e}\n  -> agrega un filtro con --where, o usa --vary/--per sobre esas columnas")
        name = args.title if pv is None else f"{args.title}_{args.per}_{pv}"
        make_figure(data, args.vary, args, name)


if __name__ == "__main__":
    main()
