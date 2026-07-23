"""
utils.py
========

Utilidades transversales del proyecto: gestion de semillas, temporizador, guardado
de tablas/figuras y helpers para el registro de resultados. No contiene logica del
modelo; solo herramientas de apoyo reutilizadas por los experimentos.
"""

from __future__ import annotations

import json
import os
import random
import time
from contextlib import contextmanager
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Reproducibilidad
# ---------------------------------------------------------------------------
def fijar_semilla(semilla: Optional[int]) -> None:
    """Fija la semilla global de 'random'. Si numpy esta disponible, tambien la suya.
    Centraliza la reproducibilidad para todo el experimento."""
    if semilla is None:
        return
    random.seed(semilla)
    try:
        import numpy as np
        np.random.seed(semilla)
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Temporizador de contexto
# ---------------------------------------------------------------------------
@contextmanager
def cronometro(etiqueta: str = "", silencioso: bool = True):
    """Mide el tiempo de un bloque. Uso:  with cronometro('GA') as c: ...
    y despues c['t'] contiene los segundos transcurridos."""
    reloj = {"t": 0.0}
    t0 = time.perf_counter()
    try:
        yield reloj
    finally:
        reloj["t"] = time.perf_counter() - t0
        if not silencioso:
            print(f"[cronometro] {etiqueta}: {reloj['t']:.3f} s")


# ---------------------------------------------------------------------------
# Estadistica descriptiva simple (sin dependencias)
# ---------------------------------------------------------------------------
def media(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def desviacion(xs: List[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mu = media(xs)
    return (sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def resumen_estadistico(xs: List[float]) -> Dict[str, float]:
    """min, media, desviacion, max de una lista de valores."""
    return {"min": min(xs), "media": media(xs), "std": desviacion(xs), "max": max(xs)}


# ---------------------------------------------------------------------------
# Guardado de resultados
# ---------------------------------------------------------------------------
def asegurar_directorio(ruta: str) -> str:
    os.makedirs(ruta, exist_ok=True)
    return ruta


def guardar_json(obj, ruta: str) -> None:
    asegurar_directorio(os.path.dirname(ruta))
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)


def guardar_csv(filas: List[Dict], ruta: str, columnas: Optional[List[str]] = None) -> None:
    """Guarda una lista de dicts como CSV (sin pandas, para no acoplar)."""
    import csv
    if not filas:
        return
    asegurar_directorio(os.path.dirname(ruta))
    columnas = columnas or list(filas[0].keys())
    with open(ruta, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columnas)
        w.writeheader()
        for f in filas:
            w.writerow({c: f.get(c, "") for c in columnas})


def gap_relativo(valor: float, referencia: float) -> float:
    """Gap relativo (%) de 'valor' respecto de una 'referencia' (p.ej. optimo N1).
    gap = 100 * (valor - referencia) / referencia."""
    if referencia == 0:
        return float("nan")
    return 100.0 * (valor - referencia) / referencia
