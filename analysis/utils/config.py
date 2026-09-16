import matplotlib.pyplot as plt
from pathlib import Path
import sys
import os


fontSize = 24
figSizeX = 10
figSizeY = 6
plt.rcParams['font.size']       = 24  # Tamaño de la fuente
plt.rcParams['figure.figsize']  = (10, 6)  # Tamaño de la figura
plt.rcParams['axes.titlesize']  = 24  # Tamaño del título de los ejes
plt.rcParams['axes.labelsize']  = 24  # Tamaño de las etiquetas de los ejes
plt.rcParams['xtick.labelsize'] = 24  # Tamaño de las etiquetas del eje x
plt.rcParams['ytick.labelsize'] = 24  # Tamaño de las etiquetas del eje y
plt.rcParams['legend.fontsize'] = 24 # Tamaño de la fuente de la leyenda

# Colores fijos
colors = {
    'blue': '#6BAED6',  # azul
    'orange': '#EE7733',  # naranja
    'green': '#83f28f',  # verde
    'green_light': '#31A354',  # verde
    'green_dark': '#013220',  # verde
    'red': '#E31A1C',  # rojo
    'violet': '#AA3377',  # púrpura
    'brown': '#663333',  # marrón
    'pink': '#EE99AA',  # rosa
    'grey': '#BBBBBB',  # gris
    'yellow': '#CCBB44',  # amarillo
    'cyan': '#66CCEE',  # cian
}

width=8
size = 80
alpha=0.7
show=True
