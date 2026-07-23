"""
exp_calibracion.py
==================

Experimento de CALIBRACION del algoritmo genetico. Explora combinaciones de
hiperparametros (tamano de poblacion, probabilidad de cruce, probabilidad de
mutacion, tamano de torneo) y, para cada combinacion, ejecuta varias REPLICAS con
semillas distintas para estimar el rendimiento medio y su variabilidad.

Objetivo
--------
Determinar la configuracion de hiperparametros que ofrece el mejor compromiso
entre CALIDAD de la solucion (LCOH / fitness final) y COSTE COMPUTACIONAL (tiempo),
que se fijara despues como configuracion de referencia en la comparacion A/B/C.

Salida
------
  - resultados/tablas/calibracion.csv : una fila por (config, replica).
  - resultados/tablas/calibracion_resumen.csv : agregado por config (media/std).
  - impresion por consola de la mejor configuracion.

Nota sobre el pool del Nivel 1
------------------------------
La calibracion se hace con inicializacion ALEATORIA (tipo A) para que las
diferencias observadas se deban a los hiperparametros y NO al arranque. Una vez
calibrado, la comparacion A/B/C (exp_comparativo.py) usara esa configuracion fija.
"""

from __future__ import annotations

import os
import sys
from itertools import product

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "CODIGO_FUENTE"))


from modelo import Instancia
from ga_engine import ConfigGA, MotorGA
from utils import (asegurar_directorio, guardar_csv, resumen_estadistico,
                   media, desviacion)


# --- Malla de hiperparametros a explorar (editable) ---
REJILLA = {
    "tam_poblacion": [20, 40, 60],
    "prob_cruce": [0.8, 0.9],
    "prob_mutacion": [0.1, 0.2, 0.3],
    "k_torneo": [2, 3],
}
N_GENERACIONES = 80
SEMILLAS_REPLICA = [1, 2, 3, 4, 5]      # 5 replicas por configuracion


def ejecutar_calibracion(inst: Instancia, dir_salida: str) -> dict:
    filas = []
    resumen_por_config = []

    combos = list(product(REJILLA["tam_poblacion"], REJILLA["prob_cruce"],
                          REJILLA["prob_mutacion"], REJILLA["k_torneo"]))
    print(f"Calibracion: {len(combos)} configuraciones x {len(SEMILLAS_REPLICA)} replicas")

    for (tam, pc, pm, kt) in combos:
        fitness_finales, lcoh_finales, tiempos = [], [], []
        for s in SEMILLAS_REPLICA:
            cfg = ConfigGA(tam_poblacion=tam, n_generaciones=N_GENERACIONES,
                           prob_cruce=pc, prob_mutacion=pm, k_torneo=kt,
                           tipo_init="A", semilla=s)
            res = MotorGA(inst, cfg).ejecutar()
            fitness_finales.append(res.mejor_fitness)
            if res.mejor_lcoh is not None:
                lcoh_finales.append(res.mejor_lcoh)
            tiempos.append(res.tiempo_s)
            filas.append({
                "tam_poblacion": tam, "prob_cruce": pc, "prob_mutacion": pm,
                "k_torneo": kt, "semilla": s,
                "fitness_final": round(res.mejor_fitness, 4),
                "lcoh_final": round(res.mejor_lcoh, 6) if res.mejor_lcoh else "",
                "tiempo_s": round(res.tiempo_s, 4),
                "factible": res.factible,
            })

        rf = resumen_estadistico(fitness_finales)
        resumen_por_config.append({
            "tam_poblacion": tam, "prob_cruce": pc, "prob_mutacion": pm, "k_torneo": kt,
            "fitness_medio": round(rf["media"], 4),
            "fitness_std": round(rf["std"], 4),
            "fitness_min": round(rf["min"], 4),
            "lcoh_medio": round(media(lcoh_finales), 6) if lcoh_finales else "",
            "tiempo_medio_s": round(media(tiempos), 4),
        })

    # Guardar
    asegurar_directorio(dir_salida)
    guardar_csv(filas, os.path.join(dir_salida, "calibracion.csv"))
    guardar_csv(resumen_por_config, os.path.join(dir_salida, "calibracion_resumen.csv"))

    # Mejor config: menor fitness medio, desempate por menor std y menor tiempo
    mejor = min(resumen_por_config,
                key=lambda r: (r["fitness_medio"], r["fitness_std"], r["tiempo_medio_s"]))
    return {"filas": filas, "resumen": resumen_por_config, "mejor": mejor}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Calibracion de hiperparametros del GA.")
    ap.add_argument("--instancia", required=True,
                    help="ruta al JSON de la instancia (cualquier instancia con la estructura estandar)")
    ap.add_argument("--dir_out", default=None, help="carpeta de salida para las tablas CSV")
    args = ap.parse_args()

    inst = Instancia.desde_json(os.path.abspath(args.instancia))
    base = os.path.dirname(os.path.abspath(args.instancia))
    dir_out = os.path.abspath(args.dir_out) if args.dir_out else os.path.join(base, "tablas")

    out = ejecutar_calibracion(inst, os.path.abspath(dir_out))

    print("\n== MEJOR CONFIGURACION ==")
    m = out["mejor"]
    print(f"  tam_poblacion={m['tam_poblacion']}  prob_cruce={m['prob_cruce']}  "
          f"prob_mutacion={m['prob_mutacion']}  k_torneo={m['k_torneo']}")
    print(f"  fitness_medio={m['fitness_medio']}  (std={m['fitness_std']})  "
          f"lcoh_medio={m['lcoh_medio']}  tiempo_medio={m['tiempo_medio_s']} s")
    print(f"\nTablas guardadas en {os.path.abspath(dir_out)}")
