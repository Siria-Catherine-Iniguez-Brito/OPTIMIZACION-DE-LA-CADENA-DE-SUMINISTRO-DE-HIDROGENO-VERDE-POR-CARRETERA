"""
exp_comparativo.py
==================

Experimento COMPARATIVO de las tres estrategias de inicializacion de la poblacion
del algoritmo genetico, nucleo del TFM:

    (A) ALEATORIA        - arranque sin informacion.
    (B) SEMILLA NIVEL 1  - warm start desde el pool exacto del Nivel 1.
    (C) MIXTA            - proporcion configurable de B y A.

Para cada estrategia se ejecutan varias REPLICAS (semillas distintas) con la
configuracion de hiperparametros previamente CALIBRADA (exp_calibracion.py) y se
comparan:
    - convergencia   : curva de mejor fitness por generacion (media de replicas).
    - calidad final  : mejor LCOH y fitness alcanzados.
    - eficiencia     : tiempo de computo (incluido el del Nivel 1 para B y C).
    - gap al optimo  : distancia relativa al optimo exacto del Nivel 1 (referencia).

El pool del Nivel 1 se obtiene con el solver exacto (nivel1_exacto.py, PuLP+CBC).
Si PuLP no esta instalado, el experimento avisa y omite B/C.

Salida
------
  - resultados/tablas/comparativa.csv
  - resultados/figuras/convergencia_ABC.png   (si matplotlib disponible)
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "CODIGO_FUENTE"))


from modelo import Instancia
from ga_engine import ConfigGA, MotorGA
from utils import (asegurar_directorio, guardar_csv, media, desviacion,
                   resumen_estadistico, gap_relativo, cronometro)


# --- Configuracion CALIBRADA (sustituir por la salida de exp_calibracion.py) ---
CFG_BASE = dict(tam_poblacion=40, n_generaciones=120,
                prob_cruce=0.9, prob_mutacion=0.2, k_torneo=3)
SEMILLAS_REPLICA = [1, 2, 3, 4, 5]
FRAC_SEMILLA_C = 0.5
TAM_POOL_N1 = 5          # nº de soluciones del pool del Nivel 1 para B/C


def obtener_pool_y_optimo(inst: Instancia):
    """Resuelve el Nivel 1 (PuLP+CBC): devuelve (pool, coste_optimo, tiempo_n1).
    Si PuLP no esta disponible, devuelve (None, None, 0.0)."""
    try:
        from nivel1_exacto import SolverNivel1
    except ImportError:
        print("[aviso] PuLP no disponible: se omiten las estrategias B y C.")
        return None, None, 0.0
    solver = SolverNivel1(inst)
    with cronometro("Nivel1") as c:
        opt = solver.resolver_optimo()
        pool = solver.pool_perturbacion(n=TAM_POOL_N1, semilla=0)
    return pool, opt.coste, c["t"]


def ejecutar_estrategia(inst, tipo, pool, cfg_base, semillas, frac=0.5):
    """Ejecuta las replicas de una estrategia y devuelve historicos y metricas."""
    curvas, fitness_fin, lcoh_fin, tiempos = [], [], [], []
    for s in semillas:
        cfg = ConfigGA(tipo_init=tipo, frac_semilla=frac, semilla=s, **cfg_base)
        res = MotorGA(inst, cfg, pool_n1=pool).ejecutar()
        curvas.append(res.hist_best_fitness)
        fitness_fin.append(res.mejor_fitness)
        if res.mejor_lcoh is not None:
            lcoh_fin.append(res.mejor_lcoh)
        tiempos.append(res.tiempo_s)
    return {"curvas": curvas, "fitness_fin": fitness_fin,
            "lcoh_fin": lcoh_fin, "tiempos": tiempos}


def curva_media(curvas):
    """Media por generacion de un conjunto de curvas (recorta a la mas corta)."""
    L = min(len(c) for c in curvas)
    return [media([c[g] for c in curvas]) for g in range(L)]


def main(inst: Instancia, dir_tablas: str, dir_figuras: str):
    pool, coste_opt, t_n1 = obtener_pool_y_optimo(inst)

    estrategias = ["A"] + (["B", "C"] if pool is not None else [])
    resultados = {}
    for tipo in estrategias:
        resultados[tipo] = ejecutar_estrategia(
            inst, tipo, pool, CFG_BASE, SEMILLAS_REPLICA, FRAC_SEMILLA_C)

    # --- Tabla comparativa ---
    filas = []
    for tipo in estrategias:
        r = resultados[tipo]
        rf = resumen_estadistico(r["fitness_fin"])
        # tiempo total: GA (+ Nivel 1 amortizado en B y C)
        t_ga = media(r["tiempos"])
        t_total = t_ga + (t_n1 if tipo in ("B", "C") else 0.0)
        fila = {
            "estrategia": tipo,
            "fitness_medio": round(rf["media"], 4),
            "fitness_std": round(rf["std"], 4),
            "fitness_min": round(rf["min"], 4),
            "lcoh_medio": round(media(r["lcoh_fin"]), 6) if r["lcoh_fin"] else "",
            "tiempo_GA_s": round(t_ga, 4),
            "tiempo_total_s": round(t_total, 4),
        }
        if coste_opt is not None:
            fila["gap_vs_N1_%"] = round(gap_relativo(rf["media"], coste_opt), 4)
        filas.append(fila)

    asegurar_directorio(dir_tablas)
    guardar_csv(filas, os.path.join(dir_tablas, "comparativa.csv"))

    print("\n== COMPARATIVA A / B / C ==")
    for f in filas:
        print(" ", f)
    if coste_opt is not None:
        print(f"\n  Optimo Nivel 1 (referencia de gap): coste={coste_opt:.2f}  "
              f"LCOH={coste_opt / inst.HTotal:.4f} EUR/kg  (t_N1={t_n1:.3f}s)")

    # --- Figura de convergencia (media por generacion) ---
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        asegurar_directorio(dir_figuras)
        fig, ax = plt.subplots(figsize=(8, 5))
        etiquetas = {"A": "(A) Aleatoria", "B": "(B) Semilla Nivel 1", "C": "(C) Mixta"}
        for tipo in estrategias:
            cm = curva_media(resultados[tipo]["curvas"])
            ax.plot(range(len(cm)), cm, label=etiquetas[tipo], linewidth=2)
        ax.set_xlabel("Generacion")
        ax.set_ylabel("Mejor fitness (coste total, EUR)")
        ax.set_title("Convergencia del GA segun la inicializacion")
        ax.legend()
        ax.grid(alpha=0.3)
        salida = os.path.join(dir_figuras, "convergencia_ABC.png")
        fig.tight_layout()
        fig.savefig(salida, dpi=150)
        print(f"\n  Figura guardada en {salida}")
    except ImportError:
        print("\n  [aviso] matplotlib no disponible: se omite la figura de convergencia.")

    return filas


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Experimento comparativo de inicializaciones A/B/C.")
    ap.add_argument("--instancia", required=True,
                    help="ruta al JSON de la instancia (cualquier instancia con la estructura estandar)")
    ap.add_argument("--dir_tablas", default=None, help="carpeta de salida para las tablas CSV")
    ap.add_argument("--dir_figuras", default=None, help="carpeta de salida para las figuras")
    args = ap.parse_args()

    inst = Instancia.desde_json(os.path.abspath(args.instancia))
    base = os.path.dirname(os.path.abspath(args.instancia))
    dir_tablas = os.path.abspath(args.dir_tablas) if args.dir_tablas else os.path.join(base, "tablas")
    dir_figuras = os.path.abspath(args.dir_figuras) if args.dir_figuras else os.path.join(base, "figuras")
    main(inst, dir_tablas, dir_figuras)
