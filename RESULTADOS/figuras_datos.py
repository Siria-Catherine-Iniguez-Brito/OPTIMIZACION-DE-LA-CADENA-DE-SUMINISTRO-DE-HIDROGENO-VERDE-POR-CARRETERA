"""
figuras_datos.py
================
Genera las FIGURAS de la seccion DATOS del TFM:

  1) Mapa de los nodos (plantas candidatas y clientes) sobre el contorno de Espana
     peninsular.  ->  HV_D_MapaNodos.png
  2) Perfiles renovables horarios Ren_{i,t} de un dia tipo, para una planta solar
     y una eolica.                                   ->  HV_D_PerfilRenovable.png

No requiere paquetes cartograficos externos: dibuja un contorno esquematico de la
Peninsula y coloca los nodos por sus coordenadas (lat/lon). Usa solo matplotlib.

Uso:
    python figuras_datos.py                     # lee la instancia large por defecto
    python figuras_datos.py --instancia ../data/instancia_medium.json
Las figuras se guardan en ../resultados/figuras/ con los nombres que usa el LaTeX.
"""

from __future__ import annotations

import argparse
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

# Colores por tipo de cliente y por zona de recurso de planta.
COLOR_CLIENTE = {
    "refineria": "#B33A3A", "quimica": "#2E6F9E",
    "fertilizante": "#3F8F5B", "siderurgia": "#7A5195",
}
MARCADOR_PLANTA = {
    "solar_alto": "#E1A100", "solar_medio": "#F0C34D",
    "eolico": "#4C9BE0", "mixto": "#6FB07F",
}

# Contorno esquematico (muy simplificado) de la Espana peninsular, en (lon, lat).
# Solo pretende dar contexto geografico a la nube de nodos, no precision cartografica.
CONTORNO_ES = [
    (-9.30, 43.05), (-8.00, 43.75), (-4.00, 43.55), (-1.80, 43.40), (-0.30, 42.60),
    (0.70, 42.80), (3.30, 42.45), (3.20, 41.20), (0.80, 40.60), (0.00, 39.60),
    (-0.30, 38.30), (-0.70, 37.60), (-1.90, 36.80), (-3.50, 36.70), (-5.30, 36.10),
    (-6.30, 36.20), (-7.40, 37.20), (-6.90, 38.20), (-7.10, 39.30), (-7.00, 40.20),
    (-6.90, 41.00), (-8.20, 41.80), (-8.90, 42.60), (-9.30, 43.05),
]


def cargar(instancia_path: str) -> dict:
    with open(instancia_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def figura_mapa(inst: dict, salida: str) -> None:
    coord = {k: v for k, v in inst["coordenadas"].items() if not k.startswith("_")}
    plantas = inst["plantas"]
    clientes = inst["clientes"]

    fig, ax = plt.subplots(figsize=(8, 9))

    # Contorno peninsular
    xs = [p[0] for p in CONTORNO_ES]
    ys = [p[1] for p in CONTORNO_ES]
    ax.plot(xs, ys, color="#999999", linewidth=1.0, zorder=1)
    ax.fill(xs, ys, color="#F3F1EC", zorder=0)

    # Clientes (circulos coloreados por tipo)
    for cid, cd in clientes.items():
        lat, lon = coord[cid]
        ax.scatter(lon, lat, s=55, c=COLOR_CLIENTE.get(cd["tipo"], "#555555"),
                   marker="o", edgecolors="white", linewidths=0.6, zorder=3)

    # Plantas candidatas (estrellas coloreadas por zona de recurso)
    for pid, pdat in plantas.items():
        lat, lon = coord[pid]
        ax.scatter(lon, lat, s=190, c=MARCADOR_PLANTA.get(pdat["zona_recurso"], "#333333"),
                   marker="*", edgecolors="black", linewidths=0.7, zorder=4)

    # Leyenda combinada
    leg_cli = [Line2D([0], [0], marker="o", color="w", markerfacecolor=c,
                      markeredgecolor="white", markersize=9, label=f"Cliente: {t}")
               for t, c in COLOR_CLIENTE.items()]
    leg_pl = [Line2D([0], [0], marker="*", color="w", markerfacecolor=c,
                     markeredgecolor="black", markersize=15, label=f"Planta: {z}")
              for z, c in MARCADOR_PLANTA.items()]
    ax.legend(handles=leg_cli + leg_pl, loc="lower left", fontsize=8, framealpha=0.9)

    ax.set_xlabel("Longitud (\u00b0)")
    ax.set_ylabel("Latitud (\u00b0)")
    ax.set_title("Ubicaciones candidatas de plantas y nodos de demanda industrial")
    ax.set_aspect(1.3)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    os.makedirs(os.path.dirname(salida), exist_ok=True)
    fig.savefig(salida, dpi=150)
    plt.close(fig)
    print(f"Mapa guardado en {salida}")


def figura_perfiles(inst: dict, salida: str) -> None:
    plantas = inst["plantas"]
    # Elegir una planta solar_alto y una eolica (si existen); si no, las dos primeras.
    solar = next((p for p, d in plantas.items() if d["zona_recurso"] == "solar_alto"), None)
    eolica = next((p for p, d in plantas.items() if d["zona_recurso"] == "eolico"), None)
    elegidas = [x for x in (solar, eolica) if x] or list(plantas)[:2]

    horas = list(range(24))
    fig, ax = plt.subplots(figsize=(9, 5))
    estilos = {"solar_alto": ("#E1A100", "-"), "solar_medio": ("#F0C34D", "-"),
               "eolico": ("#4C9BE0", "-"), "mixto": ("#6FB07F", "-")}
    for pid in elegidas:
        d = plantas[pid]
        color, ls = estilos.get(d["zona_recurso"], ("#333333", "-"))
        ax.plot(horas, d["Ren"], color=color, linestyle=ls, linewidth=2.2, marker="o",
                markersize=3, label=f"{d['nombre']} ({d['zona_recurso']})")

    ax.set_xlabel("Hora del dia (t)")
    ax.set_ylabel("$Ren_{i,t}$  (kg H$_2$/h producibles)")
    ax.set_title("Perfil horario de produccion renovable (dia tipo)")
    ax.set_xticks(range(0, 24, 2))
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    os.makedirs(os.path.dirname(salida), exist_ok=True)
    fig.savefig(salida, dpi=150)
    plt.close(fig)
    print(f"Perfiles guardados en {salida}")


if __name__ == "__main__":
    aqui = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="Genera las figuras de la seccion DATOS.")
    ap.add_argument("--instancia", required=True,
                  help="ruta al JSON de la instancia (cualquiera con la estructura estandar)")
    ap.add_argument("--dir_figuras", default=os.path.join(aqui, "..", "RESULTADOS", "figuras"))
    args = ap.parse_args()

    inst = cargar(os.path.abspath(args.instancia))
    dirfig = os.path.abspath(args.dir_figuras)
    figura_mapa(inst, os.path.join(dirfig, "HV_D_MapaNodos.png"))
    figura_perfiles(inst, os.path.join(dirfig, "HV_D_PerfilRenovable.png"))
