#!/usr/bin/env python3
"""Compara mapas de registro lado a lado usando register_map.py.

Guarda este archivo en la MISMA carpeta que register_map.py.
Edita Panel: cada entrada contiene (valor del parametro variable, numero).
Los numeros iniciales son ejemplos; reemplazalos por los de tu enum.

Ejemplo:
  python3 register_map_compare.py --results ../../results \
      --where library=heaan logN=6 "pipeline=add; mul" \
      --vary stage --values encrypt_c1 add mul rescale --op_step 0 \
      --title stages

--values selecciona y ordena los paneles. Si se omite, se usa todo el enum
en el orden de declaracion. El parametro de --vary no debe estar en --where.
Para comparar otra columna, cambia --vary y los valores del enum; por ejemplo,
con --vary logDelta podrias definir D40 = (40, 1) y D45 = (45, 3).

Se guarda una figura por op_step, con una escala de color comun a todas.
Si --vary es op_step, se guarda una sola figura comparando esos pasos.
--no-legend oculta la leyenda superior; conserva los numeros de los paneles.
"""
import argparse
from enum import Enum

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

import register_map as rm


# EDITA ESTE ENUM: (valor exacto en campaigns_start, numero bajo el panel).
class Panel(Enum):
    ENCRYPT_C1 = ("encrypt_c1", 1)
    ADD = ("add", 3)
    MUL = ("mul", 4)
    RESCALE = ("rescale", 7)


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results", default="../../results")
    p.add_argument("--where", nargs="+", default=[], metavar="COL=VAL")
    p.add_argument("--vary", default="stage", help="unica columna que cambia entre paneles")
    p.add_argument("--values", nargs="+", type=rm.parse_value,
                   help="valores a comparar, en el orden deseado; por defecto, todo Panel")
    p.add_argument("--op_step", default="all", help="all | 5 | 0,5,10 | 0-25")
    p.add_argument("--stat", choices=["median", "mean", "max"], default="median")
    p.add_argument("--title", default="register_compare", help="prefijo de los archivos de salida")
    p.add_argument("--no-legend", "--no_legend", dest="no_legend", action="store_true")
    p.add_argument("--show", action="store_true")
    return p.parse_args()


def panel_selection(values):
    entries = [member.value for member in Panel]
    numbers = dict(entries)
    if len(numbers) != len(entries):
        raise ValueError("Panel contiene mas de una entrada para el mismo valor.")
    values = list(numbers) if values is None else values
    if not values or len(values) != len(set(values)):
        raise ValueError("Selecciona al menos un panel, sin valores repetidos.")
    missing = [value for value in values if value not in numbers]
    if missing:
        raise ValueError(f"Faltan estos valores en el enum Panel: {missing}")
    return [(value, numbers[value]) for value in values]


def load_comparisons(args, selected):
    filters = {key: rm.parse_value(value)
               for key, value in (item.split("=", 1) for item in args.where)}
    if args.vary in filters:
        raise ValueError(f"Quita {args.vary} de --where; selecciona sus valores con --values.")
    camps = rm.select(rm.load_campaigns(args.results), **filters)
    if args.vary not in camps.columns:
        raise ValueError(f"No existe la columna {args.vary!r} en las campanias.")
    camps = camps[camps[args.vary].isin([value for value, _ in selected])]
    if camps.empty:
        raise ValueError("No hay campanias terminadas para esos filtros y paneles.")

    steps = rm.parse_op_steps(args.op_step, camps["op_step"].unique())
    missing_steps = sorted(set(steps) - set(camps["op_step"]))
    if missing_steps:
        raise ValueError(f"No hay campanias para los op_step solicitados: {missing_steps}")
    camps = camps[camps["op_step"].isin(steps)]
    if camps.empty:
        raise ValueError("No quedaron campanias despues de filtrar --op_step.")

    groups = [(None, camps)] if args.vary == "op_step" else camps.groupby("op_step", sort=True)
    comparisons = {}
    for step, group in groups:
        # Reutiliza la validacion del proyecto: las seeds pueden variar.
        # Al igualar SOLO --vary, cualquier otra diferencia sigue siendo un error.
        comparable = group.copy()
        comparable[args.vary] = group[args.vary].iloc[0]
        try:
            rm.require_single_config(comparable)
        except ValueError as exc:
            raise ValueError(f"op_step={step}: ademas de {args.vary!r}, cambia otra "
                             f"parte de la configuracion. Ajusta --where. {exc}") from exc

        panels = []
        for value, number in selected:
            panel_camps = group[group[args.vary] == value]
            if panel_camps.empty:
                raise ValueError(f"Falta el panel {args.vary}={value!r} en op_step={step}.")
            cfg = rm.require_single_config(panel_camps).iloc[0]
            cells = rm.mrep_per_cell(rm.load_data(panel_camps, args.results), args.stat)
            if cells.empty:
                raise ValueError(f"Sin datos para {args.vary}={value!r}, op_step={step}.")
            panels.append((number, cfg, cells))
        comparisons[step] = panels
    return comparisons


def common_vmax(comparisons):
    # Ignora NaN/inf al calcular el limite; NaN conserva el gris del original
    # e inf queda saturado en el extremo negro de la escala.
    vmax = rm.MODERATE_PCT
    for panels in comparisons.values():
        for _, _, cells in panels:
            values = cells["mrep"].to_numpy()
            finite = values[np.isfinite(values)]
            if finite.size:
                vmax = max(vmax, float(finite.max()))
    return vmax


def plot_comparison(panels, vmax, show_legend=True):
    n = len(panels)
    fig, axes = plt.subplots(1, n, figsize=(max(14, 3.5 * n), 6.5), squeeze=False)
    axes = axes[0]
    left, right, bottom, top = 0.075, 0.985, 0.22, 0.84
    # Fija el layout ANTES de dibujar: register_map usa el tamano del eje
    # para calcular el diametro de los circulos.
    fig.subplots_adjust(left=left, right=right, bottom=bottom, top=top, wspace=0.10)
    same_bits = len({int(cfg["bitsPerCoeff"]) for _, cfg, _ in panels}) == 1

    for i, (ax, (number, cfg, cells)) in enumerate(zip(axes, panels)):
        rm.plot_register_map(ax, cells, cfg, vmax)
        # La imagen conjunta solo lleva ejes, leyenda y numeros de panel.
        for text in list(ax.texts):
            text.remove()  # etiquetas logDelta/logQ del mapa individual
        for line in list(ax.lines):
            if line.get_linestyle() == "--":
                line.remove()  # conserva los separadores verticales de limb
        ax.set_xlabel("")
        ax.set_ylabel("")
        n_x = (1 << int(cfg["logN"])) * (int(cells["limb"].max()) + 1)
        # Etiqueta los bordes de las columnas: 0 y N, como en la referencia.
        ax.set_xticks([-0.5, n_x - 0.5])
        ax.set_xticklabels(["0", str(n_x)], rotation=0, fontsize=rm.FONT - 8)
        n_bits = int(cfg["bitsPerCoeff"])
        ax.set_yticks(range(0, n_bits, 5 if n_bits <= 128 else 32))
        ax.tick_params(axis="y", labelsize=rm.FONT - 8)
        if i and same_bits:
            ax.tick_params(axis="y", left=False, labelleft=False)
            ax.spines["left"].set_visible(False)
        ax.text(0.5, -0.09, str(number), transform=ax.transAxes,
                ha="center", va="center", color="white", fontsize=rm.FONT - 2,
                bbox=dict(boxstyle="circle,pad=0.35", facecolor="red", edgecolor="none"),
                clip_on=False)

    for ax, next_ax in zip(axes, axes[1:]):
        x = (ax.get_position().x1 + next_ax.get_position().x0) / 2
        fig.add_artist(Line2D([x, x], [bottom - 0.11, top + 0.025],
                              transform=fig.transFigure, color="black", lw=1, ls=":"))

    fig.text(0.02, (bottom + top) / 2, "i-th Bit of Register", rotation=90,
             ha="center", va="center", fontsize=rm.FONT - 4)
    fig.text((left + right) / 2, bottom - 0.14, "Coefficients",
             ha="center", va="center", fontsize=rm.FONT - 4)
    if show_legend:
        # Un eje transparente abarca todos los paneles para reutilizar
        # la leyenda de register_map sin duplicarla en cada subplot.
        host = fig.add_axes([left, bottom, right - left, top - bottom], frameon=False)
        host.set_axis_off()
        rm.add_legend(fig, host, vmax)
    return fig


def main():
    args = parse_args()
    try:
        selected = panel_selection(args.values)
        comparisons = load_comparisons(args, selected)
    except (ValueError, KeyError) as exc:
        raise SystemExit(str(exc)) from exc

    vmax = common_vmax(comparisons)
    rm.IMG_DIR.mkdir(parents=True, exist_ok=True)
    for step, panels in comparisons.items():
        fig = plot_comparison(panels, vmax, show_legend=not args.no_legend)
        suffix = "" if step is None else f"_op_step_{step}"
        out = rm.IMG_DIR / f"{args.title}{suffix}"
        fig.savefig(f"{out}.pdf", bbox_inches="tight")
        fig.savefig(f"{out}.png", bbox_inches="tight", dpi=120)
        print(f"{args.vary}: {[value for value, _ in selected]} -> {out}.png / .pdf")
        if args.show:
            plt.show()
        plt.close(fig)


if __name__ == "__main__":
    main()
