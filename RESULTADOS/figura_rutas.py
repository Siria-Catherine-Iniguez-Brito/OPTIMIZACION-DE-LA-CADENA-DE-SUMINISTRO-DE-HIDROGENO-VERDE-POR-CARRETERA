"""
figura_rutas.py
===============
Script OPCIONAL para ilustrar una SOLUCION del algoritmo genetico sobre el mapa de
Espana: dibuja, para cada camion activo, su ruta planta -> clientes -> planta,
coloreada segun el MODO de transporte empleado (comprimido / liquido / amoniaco).

Es independiente del resto del pipeline y puede usarse de dos maneras:

  (1) Desde tu codigo, pasando un objeto Cromosoma ya resuelto:
        from figura_rutas import dibujar_rutas
        dibujar_rutas(inst, cromosoma, "resultados/figuras/HV_R_Rutas.png")

  (2) De forma autonoma, leyendo la instancia (JSON) y una solucion guardada en un
      JSON de rutas (ver formato mas abajo):
        python figura_rutas.py --instancia ../data/instancia_small.json \
                               --solucion  ../resultados/solucion_small.json

Formato del JSON de solucion (lista de rutas):
    {
      "rutas": [
        {"planta": "pl_andalu", "modo": "liquido", "clientes": ["ref_huelva", "qui_huelva"]},
        {"planta": "pl_aragon", "modo": "amoniaco", "clientes": ["ind_zaragoza"]}
      ]
    }

Este JSON se puede generar facilmente desde un Cromosoma con la funcion
'guardar_solucion' incluida al final del modulo.
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

# Colores por modo de transporte (consistentes con la memoria).
COLOR_MODO = {
    "comprimido": "#1F77B4",   # azul
    "liquido":    "#2CA02C",   # verde
    "amoniaco":   "#D62728",   # rojo
}
COLOR_CLIENTE = "#444444"
COLOR_PLANTA = "#E1A100"

# Contorno esquematico de la Espana peninsular, en (lon, lat).
CONTORNO_ES = [
    (-9.30, 43.05), (-8.00, 43.75), (-4.00, 43.55), (-1.80, 43.40), (-0.30, 42.60),
    (0.70, 42.80), (3.30, 42.45), (3.20, 41.20), (0.80, 40.60), (0.00, 39.60),
    (-0.30, 38.30), (-0.70, 37.60), (-1.90, 36.80), (-3.50, 36.70), (-5.30, 36.10),
    (-6.30, 36.20), (-7.40, 37.20), (-6.90, 38.20), (-7.10, 39.30), (-7.00, 40.20),
    (-6.90, 41.00), (-8.20, 41.80), (-8.90, 42.60), (-9.30, 43.05),
]


# ---------------------------------------------------------------------------
# Utilidades para trabajar con instancias como dict (sin depender de modelo.py)
# ---------------------------------------------------------------------------
def _coords_de_instancia(inst_dict: dict) -> Dict[str, List[float]]:
    return {k: v for k, v in inst_dict["coordenadas"].items() if not k.startswith("_")}


def _rutas_de_solucion(solucion: dict) -> List[dict]:
    """Normaliza la solucion a una lista de rutas {planta, modo, clientes}."""
    return [r for r in solucion.get("rutas", []) if r.get("clientes")]


# ---------------------------------------------------------------------------
# Dibujo principal
# ---------------------------------------------------------------------------
def dibujar_rutas_desde_dict(inst_dict: dict, solucion: dict, salida: str,
                             titulo: str = "Solucion del algoritmo genetico") -> None:
    """Dibuja las rutas de una solucion sobre el mapa. Trabaja con dicts (JSON)."""
    coord = _coords_de_instancia(inst_dict)
    rutas = _rutas_de_solucion(solucion)
    plantas = set(inst_dict["plantas"].keys())
    clientes = set(inst_dict["clientes"].keys())

    fig, ax = plt.subplots(figsize=(8, 9))

    # Contorno
    xs = [p[0] for p in CONTORNO_ES]
    ys = [p[1] for p in CONTORNO_ES]
    ax.plot(xs, ys, color="#999999", linewidth=1.0, zorder=1)
    ax.fill(xs, ys, color="#F5F3EE", zorder=0)

    # Nodos de fondo: clientes (puntos grises) y plantas (estrellas). Las plantas
    # que realmente se usan se resaltaran despues.
    for cid in clientes:
        la, lo = coord[cid]
        ax.scatter(lo, la, s=28, c=COLOR_CLIENTE, marker="o",
                   edgecolors="white", linewidths=0.4, zorder=3)
    for pid in plantas:
        la, lo = coord[pid]
        ax.scatter(lo, la, s=120, c="#DDDDDD", marker="*",
                   edgecolors="#888888", linewidths=0.6, zorder=3)

    # Rutas: para cada camion, dibujar planta -> clientes -> planta.
    plantas_usadas = set()
    modos_presentes = set()
    for r in rutas:
        p = r["planta"]
        m = r["modo"]
        modos_presentes.add(m)
        plantas_usadas.add(p)
        color = COLOR_MODO.get(m, "#000000")
        secuencia = [p] + list(r["clientes"]) + [p]
        lons = [coord[n][1] for n in secuencia]
        lats = [coord[n][0] for n in secuencia]
        ax.plot(lons, lats, color=color, linewidth=1.8, alpha=0.85, zorder=4)
        # flechas de sentido en cada tramo
        for k in range(len(secuencia) - 1):
            x0, y0 = coord[secuencia[k]][1], coord[secuencia[k]][0]
            x1, y1 = coord[secuencia[k + 1]][1], coord[secuencia[k + 1]][0]
            ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                        arrowprops=dict(arrowstyle="->", color=color, alpha=0.7, lw=1.2),
                        zorder=4)

    # Resaltar las plantas efectivamente usadas
    for pid in plantas_usadas:
        la, lo = coord[pid]
        ax.scatter(lo, la, s=230, c=COLOR_PLANTA, marker="*",
                   edgecolors="black", linewidths=0.9, zorder=6)

    # Leyenda: modos presentes + simbolos de nodo
    leyenda = [Line2D([0], [0], color=COLOR_MODO[m], lw=2.5, label=f"Modo: {m}")
               for m in COLOR_MODO if m in modos_presentes]
    leyenda += [
        Line2D([0], [0], marker="*", color="w", markerfacecolor=COLOR_PLANTA,
               markeredgecolor="black", markersize=15, label="Planta activa"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=COLOR_CLIENTE,
               markeredgecolor="white", markersize=8, label="Cliente"),
    ]
    ax.legend(handles=leyenda, loc="lower left", fontsize=8, framealpha=0.9)

    n_camiones = len(rutas)
    ax.set_xlabel("Longitud (\u00b0)")
    ax.set_ylabel("Latitud (\u00b0)")
    ax.set_title(f"{titulo}\n({n_camiones} rutas, {len(plantas_usadas)} plantas activas)")
    ax.set_aspect(1.3)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    os.makedirs(os.path.dirname(salida), exist_ok=True)
    fig.savefig(salida, dpi=150)
    plt.close(fig)
    print(f"Figura de rutas guardada en {salida}")


def dibujar_rutas(inst, cromosoma, salida: str,
                  titulo: str = "Solucion del algoritmo genetico") -> None:
    """Version comoda para llamar desde el codigo con un objeto Cromosoma.

    'inst' es una Instancia (modelo.py) y 'cromosoma' un Cromosoma (cromosoma.py).
    Convierte ambos a la representacion dict y reutiliza el dibujo principal.
    """
    inst_dict = {
        "plantas": {p: {} for p in inst.P},
        "clientes": {c: {} for c in inst.J},
        "coordenadas": {n: list(inst.coordenadas[n]) for n in inst.N},
    }
    solucion = {"rutas": [
        {"planta": r.planta, "modo": r.modo, "clientes": list(r.clientes)}
        for r in cromosoma.rutas_activas()
    ]}
    dibujar_rutas_desde_dict(inst_dict, solucion, salida, titulo)


def guardar_solucion(cromosoma, ruta_json: str) -> None:
    """Vuelca un Cromosoma a un JSON de solucion (para usar el modo autonomo)."""
    sol = {"rutas": [
        {"planta": r.planta, "modo": r.modo, "clientes": list(r.clientes)}
        for r in cromosoma.rutas_activas()
    ]}
    os.makedirs(os.path.dirname(ruta_json), exist_ok=True)
    with open(ruta_json, "w", encoding="utf-8") as fh:
        json.dump(sol, fh, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    aqui = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="Dibuja las rutas de una solucion sobre el mapa (opcional).")
    ap.add_argument("--instancia", required=True, help="JSON de la instancia")
    ap.add_argument("--solucion", required=True, help="JSON de la solucion (lista de rutas)")
    ap.add_argument("--salida", default=os.path.join(aqui, "..", "RESULTADOS", "figuras", "HV_R_Rutas.png"))
    ap.add_argument("--titulo", default="Solucion del algoritmo genetico")
    args = ap.parse_args()

    with open(os.path.abspath(args.instancia), "r", encoding="utf-8") as fh:
        inst_dict = json.load(fh)
    with open(os.path.abspath(args.solucion), "r", encoding="utf-8") as fh:
        solucion = json.load(fh)

    dibujar_rutas_desde_dict(inst_dict, solucion, os.path.abspath(args.salida), args.titulo)
