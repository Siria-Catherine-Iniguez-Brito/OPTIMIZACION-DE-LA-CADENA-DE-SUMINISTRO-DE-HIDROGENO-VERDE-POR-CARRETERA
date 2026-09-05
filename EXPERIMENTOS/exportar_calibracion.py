"""
exportar_calibracion.py
========================

Complemento a exportar.py: gestiona UN libro Excel por TIPO DE CALIBRACION
(un fichero .xlsx por cada exp_id: E01_PM.xlsx, E02_PC.xlsx, E03_PMPC.xlsx,
E04_N.xlsx, E05_G.xlsx, E06_NG.xlsx, ...), donde CADA HOJA corresponde a una
INSTANCIA (small / medium / large, o cualquier otro alias/etiqueta).

-------------------------------------------------------
  - Un libro (.xlsx) DISTINTO por cada tipo de calibracion (exp_id).
  - Dentro de cada libro, una hoja por instancia.
  - Si esa instancia YA tiene una hoja con datos de una tanda anterior, se
    REESCRIBE por completo (no se acumulan filas duplicadas ni se anexa).
  - Las demas hojas (otras instancias) NO se tocan.
  - Se anade tambien una hoja "TODAS" (vista combinada de las instancias que
    ya tengan datos) y una hoja "config" con metadatos de la ULTIMA tanda
    ejecutada para cada instancia (semillas usadas, fecha, tiempo total).

Este modulo NO ejecuta el GA ni conoce nada de ConfigGA: solo recibe el
DataFrame de resumen (agregacion.construir_resumen) ya filtrado a UNA
instancia, y lo guarda/actualiza en el libro correspondiente.
"""

from __future__ import annotations

import os
import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

import _rutas


# ---------------------------------------------------------------------------
# Columnas mostradas en cada hoja de instancia (orden fijo y legible)
# ---------------------------------------------------------------------------
COLS_HOJA_INSTANCIA: List[str] = [
    "id_config",
    # columnas de parametros (se anaden dinamicamente las que existan)
    "n_ejec", "n_factibles", "tasa_factibilidad",
    "lcoh_media", "lcoh_std", "lcoh_mejor", "lcoh_mediana", "lcoh_peor",
    "fitness_media", "fitness_std",
    "tiempo_medio_s", "tiempo_std_s",
    "gen_mejor_media", "gen_estancamiento_media",
    "rank_en_instancia", "es_mejor_en_instancia",
    "semillas",
]


def _ruta_libro(exp_id: str) -> str:
    """Un .xlsx por tipo de calibracion, junto al resto de salidas de ese exp_id."""
    return os.path.join(_rutas.dir_experimento(exp_id), f"{exp_id}_por_instancia.xlsx")


def _leer_hojas_existentes(ruta: str) -> Dict[str, pd.DataFrame]:
    """Devuelve {nombre_hoja: DataFrame} del libro si ya existe; {} si no."""
    if not os.path.isfile(ruta):
        return {}
    try:
        return pd.read_excel(ruta, sheet_name=None, engine="openpyxl")
    except Exception:
        return {}


def _preparar_hoja_instancia(res_instancia: pd.DataFrame,
                              cols_rejilla: Optional[List[str]] = None) -> pd.DataFrame:
    """Selecciona y ordena las columnas de la hoja de UNA instancia."""
    if res_instancia.empty:
        return res_instancia

    cols_rejilla = cols_rejilla or []
    cols = ["id_config"] + [c for c in cols_rejilla if c in res_instancia.columns]
    cols += [c for c in COLS_HOJA_INSTANCIA if c in res_instancia.columns and c not in cols]
    cols = [c for c in cols if c in res_instancia.columns]

    out = res_instancia[cols].copy()
    out.insert(0, "actualizado", datetime.datetime.now().isoformat(timespec="seconds"))
    return out


def _hoja_config_metadatos(hojas: Dict[str, pd.DataFrame], exp_id: str,
                            nombre_exp: Optional[str],
                            instancia_etiqueta: str, semillas: List[int],
                            tiempo_total_s: float) -> pd.DataFrame:
    """Actualiza (o crea) la hoja 'config': una fila por instancia, con la
    metadata de la ULTIMA tanda ejecutada para esa instancia."""
    prev = hojas.get("config")
    filas: List[Dict[str, Any]] = []
    if prev is not None and not prev.empty:
        filas = prev[prev["instancia"] != instancia_etiqueta].to_dict("records")

    filas.append({
        "exp_id": exp_id,
        "nombre": nombre_exp or exp_id,
        "instancia": instancia_etiqueta,
        "n_semillas": len(semillas),
        "semillas": ", ".join(str(s) for s in semillas),
        "tiempo_total_fase_s": round(tiempo_total_s, 2),
        "tiempo_total_fase_min": round(tiempo_total_s / 60.0, 2),
        "fecha": datetime.datetime.now().isoformat(timespec="seconds"),
    })
    return pd.DataFrame(filas)


def _hoja_todas(hojas: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Concatena las hojas de instancia (excluye 'config' y 'TODAS')."""
    partes = []
    for nombre, df in hojas.items():
        if nombre in ("config", "TODAS") or df is None or df.empty:
            continue
        d = df.copy()
        if "instancia" not in d.columns:
            d.insert(0, "instancia", nombre)
        partes.append(d)
    if not partes:
        return pd.DataFrame()
    return pd.concat(partes, ignore_index=True, sort=False)


# ---------------------------------------------------------------------------
# API principal
# ---------------------------------------------------------------------------
def actualizar_libro_calibracion(exp_id: str, instancia_etiqueta: str,
                                  res_instancia: pd.DataFrame,
                                  cols_rejilla: Optional[List[str]] = None,
                                  nombre_exp: Optional[str] = None,
                                  semillas: Optional[List[int]] = None,
                                  tiempo_total_s: float = 0.0,
                                  verbose: bool = True) -> str:
    """Escribe/actualiza el libro .xlsx del experimento 'exp_id', reescribiendo
    UNICAMENTE la hoja de 'instancia_etiqueta'. El resto de hojas (otras
    instancias) se conservan tal cual estaban.

    Parametros
    ----------
    res_instancia : DataFrame de resumen (agregacion.construir_resumen) ya
                    filtrado a una sola instancia (una fila por id_config).
    semillas      : lista de semillas usadas en esta tanda (para la hoja config).
    tiempo_total_s: tiempo total (segundos) de esta tanda, para control de
                    presupuesto computacional.
    """
    ruta = _ruta_libro(exp_id)
    hojas = _leer_hojas_existentes(ruta)

    hojas[instancia_etiqueta] = _preparar_hoja_instancia(res_instancia, cols_rejilla)
    hojas["config"] = _hoja_config_metadatos(
        hojas, exp_id, nombre_exp, instancia_etiqueta,
        semillas or [], tiempo_total_s,
    )
    hojas["TODAS"] = _hoja_todas(hojas)

    # Orden de hojas: config, TODAS, y luego las instancias por orden alfabetico.
    orden = ["config", "TODAS"] + sorted(
        k for k in hojas if k not in ("config", "TODAS")
    )

    with pd.ExcelWriter(ruta, engine="openpyxl") as xls:
        for nombre in orden:
            df = hojas.get(nombre)
            if df is None:
                continue
            hoja_segura = nombre[:31]  # limite de Excel para nombres de hoja
            df.to_excel(xls, sheet_name=hoja_segura, index=False)

    if verbose:
        print(f"  libro por instancia -> {ruta}  (hoja '{instancia_etiqueta}' actualizada)")
    return ruta
