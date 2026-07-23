"""
main.py
=======

Punto de entrada del proyecto. Lee un fichero de configuracion YAML (por defecto
config.yaml) y ejecuta el experimento indicado en el campo 'modo':

    - "calibracion"    -> barrido de hiperparametros del GA (exp_calibracion.py)
    - "comparativo"    -> comparacion A/B/C con Nivel 1 (exp_comparativo.py)
    - "una_ejecucion"  -> una sola ejecucion del GA con la estrategia elegida

Uso:
    python main.py                 # usa config.yaml
    python main.py mi_config.yaml  # usa otro fichero de configuracion
"""

from __future__ import annotations

import os
import sys

# Permitir importar los modulos de src/ y los experimentos/
RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(RAIZ, "CODIGO_FUENTE"))
sys.path.insert(0, os.path.join(RAIZ, "EXPERIMENTOS"))

from modelo import Instancia


def cargar_config(ruta: str) -> dict:
    """Lee el YAML de configuracion. Requiere PyYAML."""
    try:
        import yaml
    except ImportError:
        raise SystemExit("Falta PyYAML. Instala con: pip install pyyaml")
    with open(ruta, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def ruta_abs(rel: str) -> str:
    return rel if os.path.isabs(rel) else os.path.join(RAIZ, rel)


def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(RAIZ, "configuracion.yaml")     
    cfg = cargar_config(cfg_path)

    inst = Instancia.desde_json(ruta_abs(cfg["instancia"]))
    print(inst.resumen())

    dir_tablas = ruta_abs(cfg["salida"]["dir_tablas"])
    dir_figuras = ruta_abs(cfg["salida"]["dir_figuras"])
    modo = cfg.get("modo", "comparativo")
    print(f"\nModo de ejecucion: {modo}\n" + "=" * 50)

    if modo == "calibracion":
        import exp_calibracion as ec
        # Sobrescribir la rejilla y ajustes desde el YAML
        c = cfg["calibracion"]
        ec.REJILLA = {"tam_poblacion": c["tam_poblacion"], "prob_cruce": c["prob_cruce"],
                      "prob_mutacion": c["prob_mutacion"], "k_torneo": c["k_torneo"]}
        ec.N_GENERACIONES = c["n_generaciones"]
        ec.SEMILLAS_REPLICA = c["semillas"]
        out = ec.ejecutar_calibracion(inst, dir_tablas)
        m = out["mejor"]
        print("\nMejor configuracion:", m)

    elif modo == "comparativo":
        import exp_comparativo as cp
        ga = cfg["algoritmo_genetico"]
        cp.CFG_BASE = dict(tam_poblacion=ga["tam_poblacion"], n_generaciones=ga["n_generaciones"],
                           prob_cruce=ga["prob_cruce"], prob_mutacion=ga["prob_mutacion"],
                           k_torneo=ga["k_torneo"])
        comp = cfg["comparativo"]
        cp.SEMILLAS_REPLICA = comp["semillas"]
        cp.FRAC_SEMILLA_C = comp["frac_semilla"]
        cp.TAM_POOL_N1 = comp["tam_pool_n1"]
        cp.main(inst, dir_tablas, dir_figuras)

    elif modo == "una_ejecucion":
        from ga_engine import ConfigGA, MotorGA
        ga = cfg["algoritmo_genetico"]
        ue = cfg["una_ejecucion"]
        pool = None
        if ue["tipo_init"].upper() in ("B", "C"):
            try:
                from nivel1_exacto import SolverNivel1
                solver = SolverNivel1(inst)
                n1 = cfg["nivel1"]
                if n1["estrategia_pool"] == "kbest":
                    pool = solver.pool_kbest(K=n1["k_best"])
                else:
                    pool = solver.pool_perturbacion(n=cfg["comparativo"]["tam_pool_n1"],
                                                    sigma=n1["sigma_perturbacion"], semilla=0)
            except ImportError:
                raise SystemExit("La estrategia B/C requiere PuLP para el Nivel 1.")
        config = ConfigGA(tam_poblacion=ga["tam_poblacion"], n_generaciones=ga["n_generaciones"],
                          tiempo_max=ga["tiempo_max"], prob_cruce=ga["prob_cruce"],
                          prob_mutacion=ga["prob_mutacion"], k_torneo=ga["k_torneo"],
                          elitismo=ga["elitismo"], tipo_init=ue["tipo_init"],
                          frac_semilla=ue["frac_semilla"], semilla=ue["semilla"], verbose=True)
        res = MotorGA(inst, config, pool_n1=pool).ejecutar()
        print("\n" + res.resumen())
        print("Mejor solucion:")
        for r in res.mejor.rutas_activas():
            print("  ", r)
    else:
        raise SystemExit(f"Modo '{modo}' no reconocido. Use calibracion | comparativo | una_ejecucion.")


if __name__ == "__main__":
    main()
