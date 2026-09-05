"""
instancias.py
=============

Resolucion de alias -> ruta, carga de instancias con cache y construccion (tambien
con cache) del pool de soluciones del Nivel 1.

Por que hay cache
-----------------
Una campana de calibracion ejecuta la MISMA instancia cientos de veces. Parsear el
JSON y, sobre todo, relanzar CBC para construir el pool del Nivel 1 en cada
ejecucion seria un desperdicio: ni la instancia ni el pool dependen de la semilla
del GA. Se cachean en memoria y, el pool, tambien en disco.

Sobre pool_tipo='nogood'
-------------------------
Estrategia recomendada frente a 'perturbacion' (ver nivel1_exacto.py): garantiza
aperturas y_i DISTINTAS mediante cortes no-good, en lugar de esperar a que una
perturbacion aleatoria de costes cambie la solucion optima (lo que en la practica
producia pools de solo 2 soluciones distintas, muy por debajo de pool_n). Como la
clave de cache incluye pool_tipo, cambiar a 'nogood' genera automaticamente un
.pkl nuevo (p.ej. pool_large_nogood_8_..._.pkl) sin colisionar con los .pkl
antiguos de 'perturbacion': no es necesario borrar la cache existente.
"""

from __future__ import annotations

import os
import pickle
from typing import Any, Dict, List, Optional, Tuple

import _rutas  # noqa: F401  (prepara sys.path para importar el nucleo)
from modelo import Instancia


# ---------------------------------------------------------------------------
# Localizacion de los ficheros de instancia
# ---------------------------------------------------------------------------
ALIAS = {
    "small":  "instancia_small.json",
    "medium": "instancia_medium.json",
    "large":  "instancia_large.json",
}

# Directorios donde se buscan los JSON, en orden de preferencia.
DIRS_BUSQUEDA = [
    os.environ.get("DIR_INSTANCIAS", ""),
    os.path.join(_rutas.DIR_RAIZ, "tablas"),
    os.path.join(_rutas.DIR_RAIZ, "DATOS", "tablas"),
    os.path.join(_rutas.DIR_RAIZ, os.pardir, "DATOS", "tablas"),
    os.path.join(_rutas.DIR_PAQUETE, "tablas"),
    _rutas.DIR_RAIZ,
    "tablas",
    ".",
]


def resolver_ruta(inst_id: str) -> str:
    """Traduce 'small' / 'medium' / 'large' o una ruta a un fichero existente.

    Si 'inst_id' ya es una ruta valida se devuelve tal cual, de modo que puedas
    pasar instancias propias sin registrarlas en ALIAS.
    """
    if os.path.isfile(inst_id):
        return inst_id

    nombre = ALIAS.get(inst_id.lower(), inst_id)
    if not nombre.endswith(".json"):
        nombre += ".json"

    for d in DIRS_BUSQUEDA:
        if not d:
            continue
        cand = os.path.join(d, nombre)
        if os.path.isfile(cand):
            return cand

    raise FileNotFoundError(
        f"No encuentro la instancia '{inst_id}'. Busque '{nombre}' en: "
        f"{[d for d in DIRS_BUSQUEDA if d]}. Pase una ruta explicita o defina "
        f"la variable de entorno DIR_INSTANCIAS."
    )


def etiqueta(inst_id: str) -> str:
    """Nombre corto y estable para las columnas 'instancia' de los CSV."""
    if inst_id.lower() in ALIAS:
        return inst_id.lower()
    base = os.path.basename(inst_id)
    if base.endswith(".json"):
        base = base[:-5]
    return base.replace("instancia_", "")


# ---------------------------------------------------------------------------
# Cache de instancias
# ---------------------------------------------------------------------------
_CACHE_INST: Dict[str, Instancia] = {}


def cargar(inst_id: str) -> Instancia:
    """Carga (y valida) una instancia, con cache en memoria."""
    ruta = resolver_ruta(inst_id)
    if ruta not in _CACHE_INST:
        _CACHE_INST[ruta] = Instancia.desde_json(ruta)
    return _CACHE_INST[ruta]


def dimensiones(inst: Instancia) -> Dict[str, Any]:
    """Columnas de identificacion de la instancia para los CSV."""
    return {
        "P": len(inst.P),
        "J": len(inst.J),
        "K": len(inst.K),
        "M": len(inst.M),
        "HTotal": inst.HTotal,
    }


# ---------------------------------------------------------------------------
# Modo de referencia del Nivel 1
# ---------------------------------------------------------------------------
def resolver_m_ref(inst: Instancia, m_ref: Optional[str]) -> Optional[str]:
    """Traduce las etiquetas de E10_MREF a un modo concreto de la instancia.

        None / 'min_efi'  -> modo MENOS eficiente (criterio conservador, defecto)
        'max_efi'         -> modo mas eficiente
        'min_coste'       -> modo mas barato por km
        cualquier otra    -> se interpreta como el nombre literal de un modo
    """
    if m_ref is None or m_ref == "min_efi":
        return None                       # SolverNivel1 ya aplica min Efi por defecto
    if m_ref == "max_efi":
        return max(inst.M, key=lambda m: inst.modos[m].Efi)
    if m_ref == "min_coste":
        return min(inst.M, key=lambda m: inst.modos[m].coste_por_km)
    if m_ref in inst.modos:
        return m_ref
    raise ValueError(f"m_ref '{m_ref}' no reconocido para la instancia {inst.nombre}.")


# ---------------------------------------------------------------------------
# Cache del pool del Nivel 1
# ---------------------------------------------------------------------------
_CACHE_POOL: Dict[Tuple, List] = {}

# Estrategias validas de pool_tipo. 'nogood' es la recomendada (ver docstring
# del modulo y de nivel1_exacto.pool_nogood); 'perturbacion' y 'kbest' se
# mantienen por compatibilidad con campanas anteriores (E08_INIT, E08b_POOL).
POOL_TIPOS_VALIDOS = ("nogood", "perturbacion", "kbest")

# Parametros por defecto de pool_nogood (gap relajado + limite de tiempo por
# resolucion): pueden sobreescribirse via pool_gap_rel / pool_time_limit si
# en el futuro se quieren calibrar tambien (p.ej. en E08b_POOL).
POOL_NOGOOD_GAP_REL_DEFECTO = 0.10
POOL_NOGOOD_TIME_LIMIT_DEFECTO = 5.0


def _clave_pool(inst_id: str, pool_tipo: str, pool_n: int,
                pool_sigma: float, m_ref: Optional[str], semilla_pool: int,
                pool_gap_rel: Optional[float] = None,
                pool_time_limit: Optional[float] = None) -> Tuple:
    # pool_gap_rel/pool_time_limit solo se anaden a la clave si difieren de los
    # valores por defecto de 'nogood', para no romper la compatibilidad de
    # nombres de cache ya generados para 'perturbacion'/'kbest' (que no los usan).
    extra: Tuple = ()
    if pool_tipo == "nogood":
        gr = POOL_NOGOOD_GAP_REL_DEFECTO if pool_gap_rel is None else pool_gap_rel
        tl = POOL_NOGOOD_TIME_LIMIT_DEFECTO if pool_time_limit is None else pool_time_limit
        extra = (round(float(gr), 4), round(float(tl), 2))
    return (etiqueta(inst_id), pool_tipo, int(pool_n), round(float(pool_sigma), 4),
            str(m_ref), int(semilla_pool)) + extra


def pool_nivel1(inst_id: str, pool_tipo: str = "nogood", pool_n: int = 8,
                pool_sigma: float = 0.15, m_ref: Optional[str] = None,
                semilla_pool: int = 12345, usar_disco: bool = True,
                verbose: bool = False,
                pool_gap_rel: Optional[float] = None,
                pool_time_limit: Optional[float] = None) -> List:
    """Devuelve el pool de soluciones del Nivel 1, con cache en memoria y disco.

    El pool NO depende de la semilla del GA (solo de la instancia y de los
    parametros del propio pool), por eso se comparte entre todas las ejecuciones
    de una misma configuracion. 'semilla_pool' es fija para que el pool sea
    reproducible.

    pool_tipo:
        'nogood'       (recomendado, por defecto) -> solver.pool_nogood(...).
                        Garantiza pool_n aperturas y_i distintas (si existen) y
                        acepta soluciones factibles no optimas (pool_gap_rel) para
                        acelerar cada resolucion del MILP simplificado.
        'perturbacion' (heredado, E08_INIT original) -> solver.pool_perturbacion(...).
                        Puede devolver menos soluciones distintas de las pedidas
                        si la perturbacion de costes no cambia la apertura optima.
        'kbest'        -> solver.pool_kbest(...). Como 'nogood' pero exigiendo
                        optimalidad estricta en cada resolucion (mas lento).

    'pulp' se importa AQUI y no al principio del modulo: la estrategia de
    inicializacion A no necesita el Nivel 1, asi que los experimentos que solo
    usan A funcionan aunque CBC no este disponible.
    """
    if pool_tipo not in POOL_TIPOS_VALIDOS:
        raise ValueError(
            f"pool_tipo '{pool_tipo}' no valido ({' | '.join(POOL_TIPOS_VALIDOS)})."
        )

    clave = _clave_pool(inst_id, pool_tipo, pool_n, pool_sigma, m_ref, semilla_pool,
                        pool_gap_rel, pool_time_limit)
    if clave in _CACHE_POOL:
        return _CACHE_POOL[clave]

    ruta_pkl = None
    if usar_disco:
        os.makedirs(_rutas.DIR_CACHE, exist_ok=True)
        nombre = "pool_" + "_".join(str(c).replace(".", "p") for c in clave) + ".pkl"
        ruta_pkl = os.path.join(_rutas.DIR_CACHE, nombre)
        if os.path.isfile(ruta_pkl):
            try:
                with open(ruta_pkl, "rb") as fh:
                    pool = pickle.load(fh)
                _CACHE_POOL[clave] = pool
                if verbose:
                    print(f"    [pool] recuperado de cache: {os.path.basename(ruta_pkl)}")
                return pool
            except Exception:
                pass          # cache corrupta o de otra version: se regenera

    try:
        from nivel1_exacto import SolverNivel1
    except ImportError as exc:
        raise ImportError(
            "Las estrategias de inicializacion B y C necesitan el Nivel 1, que "
            "requiere la libreria PuLP con el solver CBC. Use tipo_init='A' si no "
            "desea resolver el modelo exacto."
        ) from exc

    inst = cargar(inst_id)
    solver = SolverNivel1(inst, modo_referencia=resolver_m_ref(inst, m_ref))

    if verbose:
        print(f"    [pool] resolviendo Nivel 1 ({pool_tipo}, n={pool_n}) ...")

    if pool_tipo == "nogood":
        gap_rel = POOL_NOGOOD_GAP_REL_DEFECTO if pool_gap_rel is None else pool_gap_rel
        time_limit = POOL_NOGOOD_TIME_LIMIT_DEFECTO if pool_time_limit is None else pool_time_limit
        pool = solver.pool_nogood(K=pool_n, gap_rel=gap_rel, time_limit=time_limit,
                                  sigma=pool_sigma, semilla=semilla_pool)
    elif pool_tipo == "kbest":
        pool = solver.pool_kbest(K=pool_n)
    elif pool_tipo == "perturbacion":
        pool = solver.pool_perturbacion(n=pool_n, sigma=pool_sigma, semilla=semilla_pool)
    else:  # pragma: no cover - cubierto por la validacion de arriba
        raise ValueError(f"pool_tipo '{pool_tipo}' no valido.")

    if not pool:
        raise RuntimeError(f"El pool del Nivel 1 salio vacio para '{inst_id}'.")

    _CACHE_POOL[clave] = pool
    if ruta_pkl:
        try:
            with open(ruta_pkl, "wb") as fh:
                pickle.dump(pool, fh)
        except Exception:
            pass              # que no se caiga un experimento por no poder cachear

    if verbose:
        print(f"    [pool] {len(pool)} soluciones; mejor coste = {pool[0].coste:.2f} EUR")
    return pool


def coste_optimo_nivel1(inst_id: str, m_ref: Optional[str] = None) -> Optional[float]:
    """Coste optimo del Nivel 1, informativo.

    ATENCION: el Nivel 1 usa flujo DIRECTO planta-cliente, no ruteo, por lo que
    NO es una cota inferior valida del problema global. Se guarda unicamente como
    dato de contexto y NO se emplea para calcular ningun gap ni error.
    """
    try:
        pool = pool_nivel1(inst_id, pool_tipo="nogood", pool_n=1, m_ref=m_ref)
        return pool[0].coste
    except Exception:
        return None
