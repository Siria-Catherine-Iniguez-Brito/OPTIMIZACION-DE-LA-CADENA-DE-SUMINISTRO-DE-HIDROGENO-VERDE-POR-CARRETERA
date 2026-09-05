"""
runner.py
=========

Ejecuta UNA configuracion del algoritmo genetico con UNA semilla y devuelve UNA
fila de resultados (un dict). Es la unidad atomica de todo el marco experimental:
calibracion.py se limita a llamar aqui muchas veces.

Responsabilidades
-----------------
  - traducir un dict de parametros a un ConfigGA y a los pesos del EvaluadorFitness;
  - obtener el pool del Nivel 1 solo si la inicializacion lo necesita (B o C);
  - lanzar el GA, capturar excepciones y no dejar caer nunca una campana entera;
  - extraer del ResultadoGA todas las metricas de la fila, incluido el diagnostico
    de infactibilidad;
  - devolver aparte el historico de convergencia, en formato largo.

Criterio con los INFACTIBLES
----------------------------
Si la mejor solucion de una ejecucion es infactible, 'lcoh' vale None (celda vacia
en el CSV, nunca 0) y 'factible' es False. El 'fitness' esta siempre definido, de
modo que la ejecucion sigue siendo comparable. Las columnas 'viol_*' registran la
magnitud de cada violacion para poder diagnosticar por que fallo.
"""

from __future__ import annotations

import hashlib
import json
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import _rutas  # noqa: F401
import instancias as ins
from cromosoma import Cromosoma
from fitness import EvaluadorFitness
from ga_engine import ConfigGA, MotorGA, ResultadoGA
from modelo import Instancia


# ---------------------------------------------------------------------------
# Claves de configuracion que definen una ejecucion 
# ---------------------------------------------------------------------------
COLS_PARAMS: List[str] = [
    "tam_poblacion", "n_generaciones", "tiempo_max", "prob_cruce", "prob_mutacion",
    "k_torneo", "elitismo", "tipo_init", "frac_semilla",
    "pool_tipo", "pool_n", "pool_sigma", "m_ref",
    "w_visita", "w_capacidad", "w_camiones", "w_produccion",
]


def hash_config(cfg: Dict[str, Any]) -> str:
    """Huella corta y estable de una configuracion, para trazabilidad."""
    reducido = {k: cfg.get(k) for k in COLS_PARAMS}
    txt = json.dumps(reducido, sort_keys=True, default=str)
    return hashlib.md5(txt.encode("utf-8")).hexdigest()[:10]


def _a_config_ga(cfg: Dict[str, Any], semilla: int) -> ConfigGA:
    """Traduce el dict de parametros del experimento a un ConfigGA."""
    return ConfigGA(
        tam_poblacion=int(cfg["tam_poblacion"]),
        n_generaciones=(None if cfg.get("n_generaciones") is None
                        else int(cfg["n_generaciones"])),
        tiempo_max=(None if cfg.get("tiempo_max") is None
                    else float(cfg["tiempo_max"])),
        prob_cruce=float(cfg["prob_cruce"]),
        prob_mutacion=float(cfg["prob_mutacion"]),
        k_torneo=int(cfg["k_torneo"]),
        elitismo=bool(cfg.get("elitismo", True)),
        tipo_init=str(cfg["tipo_init"]).upper(),
        frac_semilla=float(cfg.get("frac_semilla", 0.5)),
        semilla=int(semilla),
        verbose=False,
    )


def _evaluador(inst: Instancia, cfg: Dict[str, Any]) -> EvaluadorFitness:
    """EvaluadorFitness con los pesos de penalizacion del experimento."""
    return EvaluadorFitness(
        inst,
        w_visita=float(cfg.get("w_visita", 1e5)),
        w_capacidad=float(cfg.get("w_capacidad", 1e4)),
        w_camiones=float(cfg.get("w_camiones", 1e5)),
        w_produccion=float(cfg.get("w_produccion", 1e4)),
    )


def _pool_si_hace_falta(inst_id: str, cfg: Dict[str, Any],
                        verbose: bool = False) -> Optional[List]:
    """El pool del Nivel 1 solo se construye para las inicializaciones B y C."""
    if str(cfg["tipo_init"]).upper() == "A":
        return None
    return ins.pool_nivel1(
        inst_id,
        pool_tipo=str(cfg.get("pool_tipo", "perturbacion")),
        pool_n=int(cfg.get("pool_n", 8)),
        pool_sigma=float(cfg.get("pool_sigma", 0.15)),
        m_ref=cfg.get("m_ref"),
        verbose=verbose,
    )


# ---------------------------------------------------------------------------
# Diagnostico del mejor individuo
# ---------------------------------------------------------------------------
def _diagnostico(inst: Instancia, cromo: Cromosoma,
                 ev: EvaluadorFitness) -> Dict[str, Any]:
    """Desglosa el estado de la mejor solucion: violaciones y estructura.

    Sirve para responder 'por que salio infactible' sin volver a ejecutar. Con el
    reparador de reparacion.py lo habitual es que, si algo falla, sea el exceso de
    camiones irreducible o la capacidad de produccion, las dos infactibilidades
    que el reparador delega en la penalizacion.
    """
    try:
        e = ev.evaluar(cromo)
        det = e.detalle_infactibilidad
        modos = sorted({r.modo for r in cromo.rutas_activas()})
        return {
            "viol_visita":     det.get("visita", 0),
            "viol_capacidad":  det.get("capacidad_kg", 0.0),
            "viol_camiones":   det.get("camiones", 0),
            "viol_produccion": det.get("produccion_kg", 0.0),
            "n_camiones":         cromo.n_camiones(),
            "n_plantas_abiertas": len(cromo.plantas_abiertas()),
            "modos_usados":       "|".join(modos),
        }
    except Exception:
        return {"viol_visita": "", "viol_capacidad": "", "viol_camiones": "",
                "viol_produccion": "", "n_camiones": "",
                "n_plantas_abiertas": "", "modos_usados": ""}


def _generacion_del_mejor(hist: List[float]) -> Optional[int]:
    """Primera generacion en la que se alcanzo el mejor fitness del historico.

    Con reemplazo elitista el historico es monotono no creciente, asi que esto
    indica cuando dejo de mejorar: si es muy anterior al final, sobran generaciones.
    """
    if not hist:
        return None
    mejor = min(hist)
    for g, v in enumerate(hist):
        if v <= mejor + 1e-9:
            return g
    return len(hist) - 1


# ---------------------------------------------------------------------------
# Ejecucion principal
# ---------------------------------------------------------------------------
def ejecutar_una(exp_id: str, calibracion: str, inst_id: str,
                 cfg: Dict[str, Any], semilla: int, id_config: str,
                 rep: int = 0, guardar_convergencia: bool = True,
                 cada_gen: int = 1, verbose: bool = False,
                 ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Ejecuta el GA una vez y devuelve (fila_de_runs, filas_de_convergencia).

    Nunca lanza excepcion por un fallo de una ejecucion concreta: si el GA se cae,
    la fila se marca con error='...' y la campana continua. Asi una campana de
    varias horas no se pierde por un caso patologico.
    """
    inst = ins.cargar(inst_id)
    etiq = ins.etiqueta(inst_id)

    fila: Dict[str, Any] = {
        "exp_id": exp_id,
        "calibracion": calibracion,
        "instancia": etiq,
        **ins.dimensiones(inst),
        "id_config": id_config,
        **{c: cfg.get(c) for c in COLS_PARAMS},
        "semilla": semilla,
        "rep": rep,
    }

    filas_conv: List[Dict[str, Any]] = []
    t0 = time.perf_counter()

    try:
        pool = _pool_si_hace_falta(inst_id, cfg, verbose=verbose)
        cfg_ga = _a_config_ga(cfg, semilla)

        motor = MotorGA(inst, cfg_ga, pool_n1=pool)
        # Pesos de penalizacion del experimento: se inyectan en el evaluador que
        # el motor ya creo, y tambien en el de los operadores, para que ambos
        # midan con la misma vara.
        ev = _evaluador(inst, cfg)
        motor.evaluador = ev
        motor.operadores.ev = ev

        res: ResultadoGA = motor.ejecutar()

        fila.update({
            "factible":     res.factible,
            "lcoh":         res.mejor_lcoh if res.factible else None,
            "fitness":      res.mejor_fitness,
            "generaciones_ejec": res.generaciones,
            "tiempo_s":     res.tiempo_s,
            "evaluaciones": cfg_ga.tam_poblacion * (res.generaciones + 1),
            "gen_mejor":    _generacion_del_mejor(res.hist_best_fitness),
            "error":        "",
        })

        # Desglose economico y diagnostico del mejor individuo.
        try:
            e = ev.evaluar(res.mejor)
            fila.update({
                "coste_total":  e.coste_total,
                "capex":        e.capex,
                "opex":         e.opex,
                "transporte":   e.transporte,
                "penalizacion": e.penalizacion,
            })
        except Exception:
            fila.update({"coste_total": None, "capex": None, "opex": None,
                         "transporte": None, "penalizacion": None})

        fila.update(_diagnostico(inst, res.mejor, ev))

        # Generaciones sin mejora al final: indica si el presupuesto sobraba.
        gm = fila["gen_mejor"]
        fila["gen_estancamiento"] = (res.generaciones - gm) if gm is not None else None

        if guardar_convergencia:
            for g, (bf, mf, bl) in enumerate(zip(res.hist_best_fitness,
                                                 res.hist_media_fitness,
                                                 res.hist_best_lcoh)):
                if cada_gen > 1 and g % cada_gen != 0 and g != len(res.hist_best_fitness) - 1:
                    continue
                filas_conv.append({
                    "exp_id": exp_id, "instancia": etiq, "id_config": id_config,
                    "semilla": semilla, "generacion": g,
                    "evaluaciones": cfg_ga.tam_poblacion * (g + 1),
                    "best_fitness": bf, "media_fitness": mf,
                    "best_lcoh": bl,
                    "factible_best": bl is not None,
                })

    except Exception as exc:
        # Fila de error: se registra y la campana sigue.
        fila.update({
            "factible": False, "lcoh": None, "fitness": None,
            "coste_total": None, "capex": None, "opex": None, "transporte": None,
            "penalizacion": None, "generaciones_ejec": None,
            "tiempo_s": time.perf_counter() - t0, "evaluaciones": None,
            "gen_mejor": None, "gen_estancamiento": None,
            "viol_visita": "", "viol_capacidad": "", "viol_camiones": "",
            "viol_produccion": "", "n_camiones": "", "n_plantas_abiertas": "",
            "modos_usados": "",
            "error": f"{type(exc).__name__}: {exc}",
        })
        if verbose:
            print(f"    [ERROR] {etiq} | {id_config} | semilla {semilla}")
            traceback.print_exc()

    fila["timestamp"] = datetime.now().isoformat(timespec="seconds")
    fila["hash_config"] = hash_config(cfg)
    return fila, filas_conv


# ---------------------------------------------------------------------------
# Orden de columnas de runs.csv
# ---------------------------------------------------------------------------
COLS_RUNS: List[str] = (
    ["exp_id", "calibracion", "instancia", "P", "J", "K", "M", "HTotal", "id_config"]
    + COLS_PARAMS
    + ["semilla", "rep",
       "factible", "lcoh", "coste_total", "capex", "opex", "transporte",
       "penalizacion", "fitness",
       "viol_visita", "viol_capacidad", "viol_camiones", "viol_produccion",
       "n_camiones", "n_plantas_abiertas", "modos_usados",
       "tiempo_s", "generaciones_ejec", "evaluaciones", "gen_mejor",
       "gen_estancamiento", "error", "timestamp", "hash_config"]
)
