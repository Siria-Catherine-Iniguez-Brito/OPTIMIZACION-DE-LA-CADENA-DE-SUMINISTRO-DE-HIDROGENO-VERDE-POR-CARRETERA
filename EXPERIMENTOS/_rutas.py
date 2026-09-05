"""
_rutas.py
=========

Arranque de rutas de importacion. Permite que los modulos de EXPERIMENTOS/ importen
el nucleo del proyecto (modelo.py, ga_engine.py, fitness.py, ...) que vive en el
directorio PADRE, sin necesidad de instalar nada ni de tocar PYTHONPATH.

Se importa como primera linea de los modulos que necesitan el nucleo:

    import _rutas  # noqa: F401   (efecto lateral: prepara sys.path)

Ademas define DIR_RAIZ (raiz del proyecto) y DIR_RESULTADOS, de modo que los CSV y
las figuras se escriban siempre en el mismo sitio con independencia del directorio
desde el que se lance el script.
"""

from __future__ import annotations

import os
import sys

# Directorio de este paquete: .../TFM/EXPERIMENTOS
DIR_PAQUETE = os.path.dirname(os.path.abspath(__file__))

# Carpeta TFM (la que contiene, al mismo nivel, EXPERIMENTOS/, CODIGO_FUENTE/
# e INSTANCIAS/). EXPERIMENTOS/ NO esta dentro de CODIGO_FUENTE/, son
# carpetas HERMANAS, asi que la raiz del proyecto NO es el padre directo de
# este paquete tal cual se calcularia con os.path.dirname(DIR_PAQUETE) si
# EXPERIMENTOS fuera subcarpeta de CODIGO_FUENTE (no lo es en esta
# estructura). DIR_TFM es el padre comun de las tres carpetas.
DIR_TFM = os.path.dirname(DIR_PAQUETE)

# DIR_RAIZ: carpeta donde viven modelo.py, cromosoma.py, fitness.py,
# ga_engine.py, nivel1_exacto.py, etc. -> TFM/CODIGO_FUENTE
DIR_RAIZ = os.path.join(DIR_TFM, "CODIGO_FUENTE")

# Carpeta de instancias JSON (small/medium/large): TFM/DATOS/tablas
DIR_INSTANCIAS_TFM = os.path.join(DIR_TFM, "DATOS", "tablas")

# Salidas del marco experimental: dentro de EXPERIMENTOS/ (este paquete)
DIR_RESULTADOS = os.path.join(DIR_PAQUETE, "RESULTADOS")
DIR_CACHE = os.path.join(DIR_PAQUETE, ".cache")

for _d in (DIR_RAIZ, DIR_PAQUETE):
    if _d not in sys.path:
        sys.path.insert(0, _d)


def dir_experimento(exp_id: str) -> str:
    """Carpeta de salida de un experimento; la crea si no existe."""
    d = os.path.join(DIR_RESULTADOS, exp_id)
    os.makedirs(os.path.join(d, "Figuras"), exist_ok=True)
    return d


def ruta_salida(exp_id: str, sufijo: str, ext: str = "csv") -> str:
    """Ruta canonica de un fichero de salida: RESULTADOS/E01_PM/E01_PM_runs.csv"""
    return os.path.join(dir_experimento(exp_id), f"{exp_id}_{sufijo}.{ext}")


def ruta_figura(exp_id: str, nombre: str) -> str:
    return os.path.join(dir_experimento(exp_id), "Figuras", nombre)
