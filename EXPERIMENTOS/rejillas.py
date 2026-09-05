"""
rejillas.py
===========

Expansion de la rejilla de un experimento a la lista de configuraciones concretas
que hay que ejecutar, y construccion de los identificadores 'id_config'.

Que resuelve este modulo
------------------------
  1. PRODUCTO CARTESIANO automatico cuando la rejilla tiene varios parametros
     (calibraciones combinadas PM x PC, N x G, tipo_init x frac_semilla...).
  2. PARAMETROS COMPUESTOS: algunas rejillas no barren un parametro suelto sino
     una tupla que fija varios a la vez ('pesos_penal', 'presupuesto', 'parada').
     Aqui se traducen a los parametros reales de ConfigGA.
  3. COMBINACIONES REDUNDANTES: en E08_INIT, 'frac_semilla' solo influye si
     tipo_init == 'C'. Sin filtrar, se ejecutarian tres veces exactamente el mismo
     experimento para A y otras tres para B, gastando el triple de tiempo para
     obtener filas identicas. El bloque 'irrelevantes' del catalogo las elimina.
  4. ID_CONFIG legible y estable: 'PM=0.1', 'PM=0.1_PC=0.8', 'init=C_frac=0.5'.
"""

from __future__ import annotations

import itertools
from typing import Any, Dict, List, Tuple

# Abreviaturas para los id_config y las cabeceras de tabla.
ABREV: Dict[str, str] = {
    "prob_mutacion":  "PM",
    "prob_cruce":     "PC",
    "tam_poblacion":  "N",
    "n_generaciones": "G",
    "tiempo_max":     "tmax",
    "k_torneo":       "k",
    "tipo_init":      "init",
    "frac_semilla":   "frac",
    "pool_tipo":      "pool",
    "pool_n":         "npool",
    "pool_sigma":     "sigma",
    "m_ref":          "mref",
    "pesos_penal":    "w",
    "presupuesto":    "NxG",
    "parada":         "parada",
}


def _fmt(v: Any) -> str:
    """Formato compacto y estable de un valor para el id_config."""
    if isinstance(v, float):
        s = f"{v:g}"
        return s
    if isinstance(v, (list, tuple)):
        return "x".join(_fmt(u) for u in v)
    return str(v)


def id_config(valores: Dict[str, Any]) -> str:
    """'PM=0.1_PC=0.8' a partir de {'prob_mutacion':0.1,'prob_cruce':0.8}."""
    partes = [f"{ABREV.get(k, k)}={_fmt(v)}" for k, v in valores.items()]
    return "_".join(partes)


# ---------------------------------------------------------------------------
# Parametros compuestos: una entrada de la rejilla -> varios parametros reales
# ---------------------------------------------------------------------------
def expandir_compuestos(valores: Dict[str, Any]) -> Dict[str, Any]:
    """Traduce las claves compuestas del catalogo a parametros de ConfigGA.

        pesos_penal = (w1, w2, w3, w4)  -> w_visita, w_capacidad, w_camiones, w_produccion
        presupuesto = (N, G)            -> tam_poblacion, n_generaciones
        parada = ('generaciones', 100)  -> n_generaciones=100, tiempo_max=None
        parada = ('tiempo', 60.0)       -> tiempo_max=60.0, n_generaciones=None
    """
    out: Dict[str, Any] = {}
    for k, v in valores.items():
        if k == "pesos_penal":
            w1, w2, w3, w4 = v
            out.update({"w_visita": float(w1), "w_capacidad": float(w2),
                        "w_camiones": float(w3), "w_produccion": float(w4)})
        elif k == "presupuesto":
            n, g = v
            out.update({"tam_poblacion": int(n), "n_generaciones": int(g)})
        elif k == "parada":
            tipo, val = v
            if tipo == "tiempo":
                out.update({"tiempo_max": float(val), "n_generaciones": None})
            else:
                out.update({"n_generaciones": int(val), "tiempo_max": None})
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Filtrado de combinaciones redundantes
# ---------------------------------------------------------------------------
def _es_redundante(valores: Dict[str, Any],
                   irrelevantes: Dict[str, Dict[str, Any]]) -> bool:
    """True si esta combinacion duplica a otra ya cubierta.

    Regla del catalogo:
        "irrelevantes": {"frac_semilla": {"solo_si": {"tipo_init": ["C"]}}}
    significa que 'frac_semilla' solo importa cuando tipo_init es 'C'. Para el
    resto de valores de tipo_init se conserva UNA sola combinacion (la del primer
    valor de frac_semilla) y se descartan las demas, que darian filas identicas.
    """
    for param, regla in (irrelevantes or {}).items():
        if param not in valores:
            continue
        condiciones = regla.get("solo_si", {})
        aplica = all(valores.get(k) in v for k, v in condiciones.items())
        if not aplica and valores.get(param) != regla.get("_primer_valor"):
            return True
    return False


def expandir(rejilla: Dict[str, List[Any]],
             irrelevantes: Dict[str, Dict[str, Any]] | None = None,
             ) -> List[Tuple[str, Dict[str, Any], Dict[str, Any]]]:
    """Expande la rejilla a la lista de configuraciones a ejecutar.

    Devuelve una lista de tuplas (id_config, valores_rejilla, params_efectivos):
        id_config        : etiqueta legible, p. ej. 'PM=0.1_PC=0.8'
        valores_rejilla  : lo que se barre, tal cual (para las columnas de tabla)
        params_efectivos : ya traducido a parametros de ConfigGA (compuestos incluidos)

    Se conserva el ORDEN de la rejilla, de modo que las tablas y las leyendas de
    las figuras salgan en el orden en que escribiste los valores.
    """
    if not rejilla:
        return [("base", {}, {})]

    irrelevantes = dict(irrelevantes or {})
    for param, regla in irrelevantes.items():
        if param in rejilla and rejilla[param]:
            regla["_primer_valor"] = rejilla[param][0]

    claves = list(rejilla)
    combos = itertools.product(*(rejilla[k] for k in claves))

    salida: List[Tuple[str, Dict[str, Any], Dict[str, Any]]] = []
    vistos = set()
    for combo in combos:
        valores = dict(zip(claves, combo))
        if _es_redundante(valores, irrelevantes):
            continue
        params = expandir_compuestos(valores)
        etiqueta = id_config(valores)
        if etiqueta in vistos:
            continue
        vistos.add(etiqueta)
        salida.append((etiqueta, valores, params))
    return salida


def columnas_rejilla(rejilla: Dict[str, List[Any]]) -> List[str]:
    """Nombres de las columnas que identifican la configuracion en las tablas."""
    return list(rejilla)
