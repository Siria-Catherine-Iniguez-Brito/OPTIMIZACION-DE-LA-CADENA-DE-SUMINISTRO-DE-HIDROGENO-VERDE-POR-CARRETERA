"""
estilo.py
=========

Estilo grafico unico para todas las figuras del marco experimental, de modo que las
figuras de la memoria sean visualmente coherentes entre si.

Criterios
---------
  - Paleta apta para daltonismo (Okabe-Ito): las series se distinguen sin depender
    del color.
  - Marcadores y estilos de linea distintos por serie: la figura sigue siendo
    legible impresa en blanco y negro.
  - Tipografia serif, cuerpo discreto y rejilla suave, acorde a un documento
    academico en LaTeX.
"""

from __future__ import annotations

from typing import List

import matplotlib
matplotlib.use("Agg")            # backend sin ventana: imprescindible en servidor
import matplotlib.pyplot as plt

from matplotlib.colors import LinearSegmentedColormap


# Paleta
PALETA: List[str] = [
    "#0E6E4F",   # verde abeto      (serie 1 - principal)
    "#2E86AB",   # azul petroleo    (serie 2)
    "#4FB8A0",   # verde-azulado    (serie 3)
    "#E0A72E",   # ambar calido     (serie 4 - contraste)
    "#8FBF6B",   # verde salvia     (serie 5)
    "#5B6C8F",   # azul pizarra     (serie 6)
    "#7A5230",   # siena tierra     (serie 7)
    "#3A3A3A",   # grafito          (serie 8)
]

CMAP_CALOR = LinearSegmentedColormap.from_list(
    "axpo_calor",
    [
        "#F2F4F1",  # versión muy clara del verde/gris
        "#8FBF6B",  # verde salvia
        "#4FB8A0",  # verde azulado
        "#0E6E4F",  # verde abeto
        "#2E86AB",  # azul petróleo
        "#5B6C8F",  # azul pizarra
    ],
    N=256
)
MARCADORES: List[str] = ["o", "s", "^", "D", "v", "P", "X", "*"]
LINEAS: List[str] = ["-", "--", "-.", ":", (0, (3, 1, 1, 1)), (0, (5, 2))]

# Colores semanticos reutilizados en varias figuras.
COLOR_FACTIBLE = "#009E73"
COLOR_INFACTIBLE = "#D55E00"
COLOR_GANADOR = "#0072B2"
COLOR_NEUTRO = "#9AA0A6"

DPI = 300


def aplicar_estilo() -> None:
    """Configura matplotlib. Llamar una vez antes de dibujar."""
    plt.rcParams.update({
        "figure.dpi": 110,
        "savefig.dpi": DPI,
        "savefig.bbox": "tight",
        "font.family": "serif",
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.labelsize": 10,
        "axes.prop_cycle": plt.cycler(color=PALETA),
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.alpha": 0.25,
        "grid.linewidth": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
        "legend.fontsize": 9,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "lines.linewidth": 1.7,
        "lines.markersize": 5,
    })


def color(i: int) -> str:
    return PALETA[i % len(PALETA)]


def marcador(i: int) -> str:
    return MARCADORES[i % len(MARCADORES)]


def linea(i: int):
    return LINEAS[i % len(LINEAS)]


def guardar(fig, ruta: str, cerrar: bool = True) -> str:
    """Guarda la figura en PNG a 300 dpi y devuelve la ruta."""
    fig.savefig(ruta, dpi=DPI, bbox_inches="tight")
    if cerrar:
        plt.close(fig)
    return ruta


def etiqueta_eje_lcoh() -> str:
    return r"LCOH (€/kg)"


def etiqueta_eje_fitness() -> str:
    return "Fitness (coste + penalización)"


def nota_infactibles(ax, n_sin: int) -> None:
    """Anota en la figura cuantas configuraciones no tuvieron ninguna ejecucion
    factible, para que la ausencia de una barra o una curva no se lea como un
    error de la figura."""
    if n_sin > 0:
        ax.text(0.02, 0.97,
                f"{n_sin} sin ejecuciones factibles (no representadas)",
                transform=ax.transAxes, ha="left", va="top",
                fontsize=7.5, style="italic", color=COLOR_INFACTIBLE)
