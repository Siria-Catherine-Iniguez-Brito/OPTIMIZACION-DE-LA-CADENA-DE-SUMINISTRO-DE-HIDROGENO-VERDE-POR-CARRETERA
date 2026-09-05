"""
config_experimentos.py
======================

Fichero a editar para lanzar experimentos.

Contiene:
  1. SEMILLAS         : bloque fijo y comun de semillas (comparacion pareada).
  2. INSTANCIAS       : instancias por defecto.
  3. BASE             : hiperparametros de arranque, antes de calibrar nada.
  4. CALIBRADO        : parametros YA decididos por ti al cerrar cada fase.
  5. EXPERIMENTOS     : catalogo de experimentos, cada uno con su rejilla.

Precedencia con la que se construye la configuracion de cada ejecucion:

        BASE  <-  CALIBRADO (solo lo que no es None)  <-  rejilla del experimento

De modo que un parametro que estas barriendo SIEMPRE gana sobre el valor calibrado,
y el valor calibrado gana sobre el de arranque.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


# ===========================================================================
# 1. SEMILLAS  --  bloque FIJO y COMUN
# ===========================================================================
# Todas las configuraciones de un experimento se ejecutan con estas mismas
# semillas, en este mismo orden. Es lo que hace que la comparacion entre, por
# ejemplo, PM=0.1 y PM=0.2 sea PAREADA: misma poblacion inicial de partida.
#
# 20 semillas : con mas repeticiones por configuracion las
# diferencias entre valores candidatos se ven mas claras y la media/desviacion
# tipica son mas fiables para decidir el ganador de cada fase de calibracion.
SEMILLAS: List[int] = [
    101, 202, 303, 404, 505, 606, 707, 808, 909, 1010,
    1111, 1212, 1313, 1414, 1515, 1616, 1717, 1818, 1919, 2020,
]


# ===========================================================================
# 2. INSTANCIAS por defecto
# ===========================================================================
# Alias reconocidos: 'small', 'medium', 'large'. Tambien admite rutas a JSON
# propios, p. ej. "tablas/mi_instancia.json" o una ruta absoluta.
INSTANCIAS: List[str] = ["small", "medium", "large"]


# ===========================================================================
# 3. BASE  --  configuracion de arranque (antes de calibrar)
# ===========================================================================
# Valores deliberadamente genericos para la primera fase (E01_PM), de modo que
# el efecto del parametro barrido se aisle. PC=1.0 (cruce total) replica el
# criterio de la calibracion secuencial de la memoria.
BASE: Dict[str, Any] = {
    "tam_poblacion":   40,
    "n_generaciones":  100,
    "tiempo_max":      None,      # si se fija, tiene PRIORIDAD sobre n_generaciones
    "prob_cruce":      1.0,
    "prob_mutacion":   None,
    "k_torneo":        3,
    "elitismo":        True,
    "tipo_init":       "A",       # 'A' aleatoria | 'B' semilla N1 | 'C' mixta
    "frac_semilla":    0.5,
    # --- pool del Nivel 1 (solo relevante para tipo_init B y C) ---
    "pool_tipo":       "nogood",   # 'perturbacion' | 'kbest'
    "pool_n":          8,
    "pool_sigma":      0.15,
    "m_ref":           None,      # None = modo menos eficiente (criterio conservador)
}


# ===========================================================================
# 4. CALIBRADO  --  lo que decidimos al cerrar cada fase
# ===========================================================================
# Deja None lo que aun no has decidido. Cuando cierres una fase, escribe aqui el
# valor ganador (una sola linea) y todos los experimentos posteriores lo heredan.
#
# El script te IMPRIME la sugerencia que se deduce de resumen.csv y te AVISA si no
# coincide con lo que tengas fijado, pero la decision
# es tuya (puede pesar el coste computacional, no solo el LCOH medio).
CALIBRADO: Dict[str, Optional[Any]] = {
    "prob_mutacion":   None,       # <- fijado tras E01_PM (revisado y confirmado en E03_PMPC)
    "prob_cruce":      None,       # <- fijado tras E02_PC (confirmado en E03_PMPC)
    "tam_poblacion":   None,       # <- fijado tras E04_N (confirmado en E06_NG)
    "n_generaciones":  None,       # <- fijado tras E05_G (confirmado en E06_NG)
    "k_torneo":        None,       # <- fijado tras E07_TORNEO (robustez y velocidad)
    "tipo_init":       None,       # <- fijado tras E08_INIT (mejora +4.3%/+4.9% en medium/large)
    "frac_semilla":    None,       # no aplica a tipo_init="B" (solo relevante para "C")
    # --- pesos de penalizacion de fitness.py (calibrados en E09_PENAL) -----
    # Se mantienen los valores por defecto: ya en zona de saturacion (mejora
    # nula en medium y de solo 0.16% en large al subir un orden de magnitud
    # adicional).
    "m_ref":           None,      # <- se fija tras E10_MREF (solo relevante con tipo_init B/C)
}


# ===========================================================================
# 5. CATALOGO DE EXPERIMENTOS
# ===========================================================================
# Cada entrada es un dict con:
#   nombre  : etiqueta legible para tablas y figuras
#   rejilla : dict {parametro: [valores]}. Si hay VARIOS parametros se recorre el
#             PRODUCTO CARTESIANO automaticamente (calibracion combinada).
#   fijos   : (opcional) fuerza valores concretos para este experimento, por
#             encima de BASE y de CALIBRADO. Util para la fase de arranque.
#   etiquetas: (opcional) parametros que forman el id_config; por defecto, los
#             de la rejilla.
#   presupuesto_cte: (opcional) True -> las curvas de convergencia se dibujan
#             frente al numero de EVALUACIONES, no de generaciones.

EXPERIMENTOS: Dict[str, Dict[str, Any]] = {

    # ---------------------------------------------------------------- E01
    "E01_PM": {
        "nombre": "Calibracion de la probabilidad de mutacion",
        "rejilla": {"prob_mutacion": [0.001, 0.01, 0.05, 0.1, 0.2]},
        "fijos":   {"prob_cruce": 1.0, "tam_poblacion": 40, "n_generaciones": 100},
    },

    # ---------------------------------------------------------------- E02
    "E02_PC": {
        "nombre": "Calibracion de la probabilidad de cruce",
        "rejilla": {"prob_cruce": [0.6, 0.75, 0.9, 1.0]},
        "fijos":   {"tam_poblacion": 40, "n_generaciones": 100},
    },

    # ---------------------------------------------------------------- E03
    "E03_PMPC": {
        "nombre": "Calibracion combinada de PM y PC",
        "rejilla": {
            "prob_mutacion": [0.05, 0.1, 0.2],
            "prob_cruce":    [0.6, 0.8, 1.0],
        },
        "fijos": {"tam_poblacion": 40, "n_generaciones": 100},
    },

    # ---------------------------------------------------------------- E04
    "E04_N": {
        "nombre": "Calibracion del tamano de la poblacion",
        "rejilla": {"tam_poblacion": [50, 100, 150, 200]},
        "fijos":   {"n_generaciones": 100},
    },

    # ---------------------------------------------------------------- E05
    "E05_G": {
        "nombre": "Calibracion del numero de generaciones",
        "rejilla": {"n_generaciones": [50, 100, 200, 400]},
    },

    # ---------------------------------------------------------------- E06
    "E06_NG": {
        "nombre": "Calibracion combinada de tamano de poblacion y generaciones",
        "rejilla": {
            "tam_poblacion":  [20, 40, 80],
            "n_generaciones": [50, 100, 200],
        },
    },

    # ---------------------------------------------------------------- E07
    "E07_TORNEO": {
        "nombre": "Calibracion de la presion selectiva (tamano del torneo)",
        "rejilla": {"k_torneo": [2, 3, 5]},
    },

    # ---------------------------------------------------------------- E08
    "E08_INIT": {
        "nombre": "Estudio de las estrategias de inicializacion de la poblacion",
        "rejilla": {
            "tipo_init":    ["A", "B", "C"],
            "frac_semilla": [0.25, 0.5, 0.75],
        },
        # frac_semilla solo influye en C: calibracion.py elimina automaticamente
        # las combinaciones redundantes (A y B con distintos frac_semilla).
        "irrelevantes": {"frac_semilla": {"solo_si": {"tipo_init": ["C"]}}},
    },

    # ---------------------------------------------------------------- E10
    "E09_MREF": {
        "nombre": "Modo de referencia del Nivel 1",
        "rejilla": {"m_ref": ["min_efi", "max_efi", "min_coste"]},
        "fijos":   {"tipo_init": "B"},
    },

    # ---------------------------------------------------------------- E11
    "E10_PRESUP": {
        "nombre": "Comparacion a presupuesto computacional constante (N x G = cte)",
        # Todas las combinaciones consumen ~8000 evaluaciones, de modo que la
        # comparacion no la gana quien mas evaluaciones consume.
        "rejilla": {
            "presupuesto": [(20, 400), (40, 200), (80, 100), (160, 50)],
        },
        "presupuesto_cte": True,
    },

    # ---------------------------------------------------------------- E12
    "E11_PARADA": {
        "nombre": "Criterio de parada: generaciones frente a tiempo limite",
        "rejilla": {
            "parada": [
                ("generaciones", 100),
                ("generaciones", 200),
                ("tiempo", 30.0),
                ("tiempo", 60.0),
                ("tiempo", 120.0),
            ],
        },
    },
}


# ===========================================================================
# Utilidades de acceso
# ===========================================================================
def experimento(exp_id: str) -> Dict[str, Any]:
    """Devuelve la definicion de un experimento del catalogo."""
    if exp_id not in EXPERIMENTOS:
        disponibles = ", ".join(sorted(EXPERIMENTOS))
        raise KeyError(f"Experimento '{exp_id}' no existe. Disponibles: {disponibles}")
    return EXPERIMENTOS[exp_id]


def listar_experimentos() -> List[str]:
    return list(EXPERIMENTOS)


def config_base_efectiva(exp_id: str) -> Dict[str, Any]:
    """BASE sobrescrito por CALIBRADO (lo ya decidido) y por los 'fijos' del
    experimento. NO incluye la rejilla: eso lo anade calibracion.py."""
    cfg = dict(BASE)
    for k, v in CALIBRADO.items():
        if v is not None:
            cfg[k] = v
    cfg.update(experimento(exp_id).get("fijos", {}))
    return cfg
