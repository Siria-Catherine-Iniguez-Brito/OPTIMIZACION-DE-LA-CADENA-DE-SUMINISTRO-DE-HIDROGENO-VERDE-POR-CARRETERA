"""
agregacion.py
=============

Convierte runs.csv (crudo, una fila por ejecucion) en:

    resumen.csv  -> UNA fila por (instancia x configuracion).  <-- TABLA CLAVE
    ranking.csv  -> UNA fila por configuracion (recuento entre instancias, opcional).

TRATAMIENTO DE LAS SOLUCIONES INFACTIBLES
-----------------------------------------
Aunque el enfoque hibrido (reparacion + penalizacion) mantiene la poblacion casi
siempre factible, la salida del GA PUEDE ser infactible: el reparador delega en la
penalizacion el exceso irreducible de camiones y la capacidad de produccion. Reglas
aplicadas aqui, sin excepcion:

  1. Un infactible NUNCA entra en una media de LCOH. Su 'lcoh' es vacio -> NaN.
  2. 'lcoh_media' se acompana SIEMPRE de 'n_factibles' y 'tasa_factibilidad'. Una
     media sobre 3 de 10 ejecuciones no es comparable con una sobre 10 de 10.
  3. 'fitness_media' (coste + penalizacion) esta SIEMPRE definida y permite ordenar
     configuraciones incluso si ninguna ejecucion fue factible.
  4. Si n_factibles == 0, las columnas de LCOH quedan VACIAS y la fila se marca
     'sin_factibles'. No se rellena con 0 ni se descarta en silencio.
  5. Con n_factibles < 3 la desviacion tipica se calcula pero se marca 'n_bajo':
     con dos valores no es informativa.
  6. Al marcar la mejor configuracion de cada instancia el criterio es lexicografico:
     (a) mayor tasa_factibilidad, (b) menor lcoh_media, (c) menor tiempo_medio_s.
     Asi una configuracion que solo acierta la mitad de las veces no se proclama
     ganadora por tener buena media sobre sus pocos aciertos.

NO se calcula ningun error ni gap: no existe optimo conocido del problema global y
el Nivel 1 (flujo directo, sin ruteo) no es una cota inferior valida. Las
configuraciones se comparan por su LCOH medio en EUR/kg dentro de cada instancia.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

import _rutas  # noqa: F401


# Umbral por debajo del cual la desviacion tipica no se considera informativa.
MIN_N_PARA_STD = 3


def _stats_lcoh(sub: pd.DataFrame) -> Dict[str, Any]:
    """Estadisticos de LCOH calculados SOLO sobre las ejecuciones factibles."""
    fact = sub[sub["factible"] == True]                       # noqa: E712
    lcoh = pd.to_numeric(fact["lcoh"], errors="coerce").dropna()

    if len(lcoh) == 0:
        return {
            "lcoh_media": np.nan, "lcoh_std": np.nan, "lcoh_mejor": np.nan,
            "lcoh_mediana": np.nan, "lcoh_peor": np.nan,
            "sin_factibles": True, "n_bajo": True,
        }
    return {
        "lcoh_media":   float(lcoh.mean()),
        "lcoh_std":     float(lcoh.std(ddof=1)) if len(lcoh) > 1 else 0.0,
        "lcoh_mejor":   float(lcoh.min()),
        "lcoh_mediana": float(lcoh.median()),
        "lcoh_peor":    float(lcoh.max()),
        "sin_factibles": False,
        "n_bajo":       len(lcoh) < MIN_N_PARA_STD,
    }


def _stats_fitness(sub: pd.DataFrame) -> Dict[str, Any]:
    """Estadisticos de fitness sobre TODAS las ejecuciones (siempre definidos).

    Es la metrica de respaldo: cuando no hay ninguna ejecucion factible sigue
    permitiendo distinguir 'poco infactible' de 'muy infactible'.
    """
    fit = pd.to_numeric(sub["fitness"], errors="coerce").dropna()
    if len(fit) == 0:
        return {"fitness_media": np.nan, "fitness_std": np.nan, "fitness_mejor": np.nan}
    return {
        "fitness_media": float(fit.mean()),
        "fitness_std":   float(fit.std(ddof=1)) if len(fit) > 1 else 0.0,
        "fitness_mejor": float(fit.min()),
    }


def _stats_coste(sub: pd.DataFrame) -> Dict[str, Any]:
    """Coste computacional y comportamiento de la convergencia."""
    t = pd.to_numeric(sub["tiempo_s"], errors="coerce").dropna()
    gm = pd.to_numeric(sub["gen_mejor"], errors="coerce").dropna()
    ge = pd.to_numeric(sub["gen_estancamiento"], errors="coerce").dropna()
    return {
        "tiempo_medio_s": float(t.mean()) if len(t) else np.nan,
        "tiempo_std_s":   float(t.std(ddof=1)) if len(t) > 1 else 0.0,
        "gen_mejor_media": float(gm.mean()) if len(gm) else np.nan,
        "gen_estancamiento_media": float(ge.mean()) if len(ge) else np.nan,
    }


def _stats_violaciones(sub: pd.DataFrame) -> Dict[str, Any]:
    """Diagnostico agregado: por que fallan las ejecuciones infactibles.

    Permite explicar en la memoria si la infactibilidad residual viene del exceso
    de camiones o de la capacidad de produccion, en lugar de constatarla sin mas.
    """
    out: Dict[str, Any] = {}
    infact = sub[sub["factible"] != True]                      # noqa: E712
    out["n_con_error"] = int((sub["error"].astype(str).str.len() > 0).sum())
    for col, alias in [("viol_visita", "visita"), ("viol_capacidad", "capacidad"),
                       ("viol_camiones", "camiones"), ("viol_produccion", "produccion")]:
        v = pd.to_numeric(infact[col], errors="coerce").fillna(0.0) if len(infact) else pd.Series(dtype=float)
        out[f"n_infact_{alias}"] = int((v > 0).sum()) if len(v) else 0
    return out


def _cols_config(runs: pd.DataFrame, cols_rejilla: Optional[List[str]]) -> List[str]:
    """Columnas de parametros que se arrastran al resumen."""
    base = ["id_config"]
    if cols_rejilla:
        base += [c for c in cols_rejilla if c in runs.columns]
    # Parametros clave, siempre presentes para que la tabla sea autocontenida.
    for c in ["tam_poblacion", "n_generaciones", "tiempo_max", "prob_cruce",
              "prob_mutacion", "k_torneo", "tipo_init", "frac_semilla"]:
        if c in runs.columns and c not in base:
            base.append(c)
    return base


def construir_resumen(runs: pd.DataFrame,
                      cols_rejilla: Optional[List[str]] = None) -> pd.DataFrame:
    """runs.csv -> resumen.csv: una fila por (instancia x configuracion).

    Esta es la tabla que decide la calibracion: promedia las semillas DENTRO de
    cada instancia, de modo que puedas leer, para una instancia dada, que valor
    del parametro minimiza el LCOH medio.
    """
    if runs.empty:
        return pd.DataFrame()

    runs = runs.copy()
    runs["factible"] = runs["factible"].astype(str).str.lower().isin(["true", "1", "yes"])
    if "error" not in runs.columns:
        runs["error"] = ""
    runs["error"] = runs["error"].fillna("")

    cols_cfg = _cols_config(runs, cols_rejilla)
    filas: List[Dict[str, Any]] = []

    # groupby con sort=False para conservar el orden en que se ejecutaron las
    # configuraciones, que es el orden en que el usuario escribio la rejilla.
    for (inst, idc), sub in runs.groupby(["instancia", "id_config"], sort=False):
        n = len(sub)
        n_fact = int(sub["factible"].sum())
        fila: Dict[str, Any] = {
            "exp_id": sub["exp_id"].iloc[0],
            "calibracion": sub.get("calibracion", pd.Series([""])).iloc[0],
            "instancia": inst,
        }
        for c in ["P", "J", "K", "HTotal"]:
            if c in sub.columns:
                fila[c] = sub[c].iloc[0]
        for c in cols_cfg:
            fila[c] = sub[c].iloc[0] if c in sub.columns else None

        fila.update({
            "n_ejec": n,
            "n_factibles": n_fact,
            "tasa_factibilidad": n_fact / n if n else np.nan,
        })
        fila.update(_stats_lcoh(sub))
        fila.update(_stats_fitness(sub))
        fila.update(_stats_coste(sub))
        fila.update(_stats_violaciones(sub))
        fila["semillas"] = "|".join(str(s) for s in sorted(sub["semilla"].unique()))
        filas.append(fila)

    res = pd.DataFrame(filas)
    return marcar_mejores(res)


def marcar_mejores(res: pd.DataFrame) -> pd.DataFrame:
    """Marca, dentro de cada instancia, la mejor configuracion.

    Criterio LEXICOGRAFICO: (1) mayor tasa de factibilidad, (2) menor LCOH medio,
    (3) menor tiempo medio. El primer criterio es el que evita proclamar ganadora
    a una configuracion inestable con buena media sobre pocas ejecuciones validas.
    """
    if res.empty:
        return res
    res = res.copy()
    res["es_mejor_en_instancia"] = False
    res["rank_en_instancia"] = np.nan

    for inst, sub in res.groupby("instancia", sort=False):
        orden = sub.sort_values(
            by=["tasa_factibilidad", "lcoh_media", "lcoh_std", "tiempo_medio_s"],
            ascending=[False, True, True, True],
            na_position="last",
        )
        # El rango solo se asigna a las filas con LCOH medio definido.
        puesto = 1
        for idx in orden.index:
            if pd.notna(res.at[idx, "lcoh_media"]):
                res.at[idx, "rank_en_instancia"] = puesto
                puesto += 1
        if len(orden):
            res.at[orden.index[0], "es_mejor_en_instancia"] = True
    return res


def construir_ranking(res: pd.DataFrame) -> pd.DataFrame:
    """resumen.csv -> ranking.csv (hoja auxiliar, opcional).

    NO promedia LCOH entre instancias: 'small' ronda 6 EUR/kg y 'large' 9 EUR/kg,
    esa media no significaria nada. Solo cuenta EN CUANTAS instancias cada
    configuracion resulto la mejor, para ver de un vistazo si el ganador es el
    mismo en todos los tamanos o cambia con la escala del problema.
    """
    if res.empty:
        return pd.DataFrame()

    n_inst = res["instancia"].nunique()
    filas: List[Dict[str, Any]] = []

    for idc, sub in res.groupby("id_config", sort=False):
        ganadas = sub[sub["es_mejor_en_instancia"] == True]     # noqa: E712
        filas.append({
            "exp_id": sub["exp_id"].iloc[0],
            "id_config": idc,
            "n_instancias": len(sub),
            "veces_mejor": int(len(ganadas)),
            "veces_mejor_txt": f"{len(ganadas)}/{n_inst}",
            "mejor_en": ", ".join(sorted(ganadas["instancia"].tolist())) or "-",
            "tasa_factibilidad_global": float(sub["tasa_factibilidad"].mean()),
            "rank_medio": float(sub["rank_en_instancia"].mean(skipna=True)),
            "tiempo_medio_s": float(sub["tiempo_medio_s"].mean(skipna=True)),
            "n_instancias_sin_factibles": int(sub["sin_factibles"].sum()),
        })

    rk = pd.DataFrame(filas).sort_values(
        by=["veces_mejor", "tasa_factibilidad_global", "rank_medio"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    rk["decision"] = ""
    if len(rk):
        rk.loc[0, "decision"] = "<- mas veces mejor"
    return rk


# ---------------------------------------------------------------------------
# Sugerencia del valor ganador (informativa: la decision es del usuario)
# ---------------------------------------------------------------------------
def sugerencias(res: pd.DataFrame, cols_rejilla: List[str]) -> Dict[str, Any]:
    """Extrae el valor sugerido para cada parametro barrido.

    Devuelve un dict con la sugerencia por instancia y la global. NO modifica
    CALIBRADO ni ningun fichero: solo informa, porque la eleccion final puede
    pesar el coste computacional y no solo el LCOH medio.
    """
    if res.empty:
        return {}
    out: Dict[str, Any] = {"por_instancia": {}, "global": None, "alternativa": None}

    for inst, sub in res.groupby("instancia", sort=False):
        g = sub[sub["es_mejor_en_instancia"] == True]           # noqa: E712
        if len(g):
            out["por_instancia"][inst] = {
                "id_config": g["id_config"].iloc[0],
                **{c: g[c].iloc[0] for c in cols_rejilla if c in g.columns},
                "lcoh_media": g["lcoh_media"].iloc[0],
                "tasa_factibilidad": g["tasa_factibilidad"].iloc[0],
                "tiempo_medio_s": g["tiempo_medio_s"].iloc[0],
            }

    rk = construir_ranking(res)
    if len(rk):
        out["global"] = rk["id_config"].iloc[0]
        # Alternativa: la mas rapida entre las que nunca fallaron.
        robustas = rk[rk["tasa_factibilidad_global"] >= 0.999]
        if len(robustas):
            out["alternativa"] = robustas.sort_values("tiempo_medio_s")["id_config"].iloc[0]
    return out


def imprimir_sugerencias(res: pd.DataFrame, cols_rejilla: List[str],
                         calibrado: Optional[Dict[str, Any]] = None) -> None:
    """Muestra por pantalla el ganador que se deduce del resumen y avisa si no
    coincide con lo fijado en CALIBRADO. No cambia nada por su cuenta."""
    sug = sugerencias(res, cols_rejilla)
    if not sug:
        return
    print("\n" + "-" * 72)
    print("SUGERENCIA (informativa: la decision final es tuya)")
    print("-" * 72)
    for inst, d in sug["por_instancia"].items():
        lc = f"{d['lcoh_media']:.4f}" if pd.notna(d["lcoh_media"]) else "sin factibles"
        print(f"  {inst:<10} mejor: {d['id_config']:<28} "
              f"LCOH medio={lc}  fact={d['tasa_factibilidad']:.2f}  "
              f"t={d['tiempo_medio_s']:.1f}s")
    if sug["global"]:
        print(f"  {'AGREGADO':<10} mas veces mejor: {sug['global']}")
    if sug["alternativa"] and sug["alternativa"] != sug["global"]:
        print(f"  {'':<10} alternativa rapida y robusta: {sug['alternativa']}")

    if calibrado:
        for p in cols_rejilla:
            fijado = calibrado.get(p)
            if fijado is None:
                print(f"\n  AVISO: CALIBRADO['{p}'] esta en None. Si cierras esta fase, "
                      f"escribe ahi el valor elegido para que lo hereden E02, E04...")
            else:
                print(f"\n  CALIBRADO['{p}'] = {fijado} (fijado por ti)")
    print("-" * 72)
