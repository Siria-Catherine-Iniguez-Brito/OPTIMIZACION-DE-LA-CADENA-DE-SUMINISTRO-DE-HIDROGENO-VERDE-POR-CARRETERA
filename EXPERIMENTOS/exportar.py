"""
exportar.py
===========

Exportacion de los resultados a formatos comodos para redactar la memoria:

    exportar_excel  ->  un .xlsx con las hojas runs / resumen / ranking / config
    tabla_latex     ->  tabla LaTeX (tabular) lista para pegar, con la fila
                        ganadora en negrita
    exportar_todo   ->  ambas cosas

La hoja 'config' documenta la rejilla exacta, las semillas y los parametros fijos
de la campana: sin ella, dentro de unos meses no sabrias con que configuracion se
genero una tabla concreta.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import pandas as pd

import _rutas
import config_experimentos as C
import rejillas


# ---------------------------------------------------------------------------
# Columnas presentadas en las tablas de la memoria
# ---------------------------------------------------------------------------
COLS_TABLA: List[str] = [
    "instancia", "id_config", "n_factibles", "n_ejec",
    "lcoh_media", "lcoh_std", "lcoh_mejor", "lcoh_peor", "tiempo_medio_s",
]

CABECERAS = {
    "instancia":      "Instancia",
    "id_config":      "Configuración",
    "factibles":      "Factibles",
    "lcoh_media":     "LCOH medio",
    "lcoh_std":       "Desv. típica",
    "lcoh_mejor":     "LCOH mejor",
    "lcoh_peor":      "LCOH peor",
    "tiempo_medio_s": "t medio (s)",
    "fitness_media":  "Fitness medio",
}


def _fmt_num(v: Any, dec: int = 4) -> str:
    """Formato español (coma decimal) y celda vacia para los valores ausentes."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "--"
    if isinstance(v, float):
        return f"{v:.{dec}f}".replace(".", ",")
    return str(v)


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------
def _hoja_config(exp_id: str, instancias_ids: List[str],
                 semillas: List[int]) -> pd.DataFrame:
    """Documenta la campana: rejilla, semillas y parametros fijos."""
    d = C.experimento(exp_id)
    cfg = C.config_base_efectiva(exp_id)
    filas: List[Dict[str, Any]] = [
        {"clave": "exp_id", "valor": exp_id},
        {"clave": "nombre", "valor": d.get("nombre", "")},
        {"clave": "instancias", "valor": ", ".join(instancias_ids)},
        {"clave": "semillas", "valor": ", ".join(str(s) for s in semillas)},
        {"clave": "n_semillas", "valor": len(semillas)},
        {"clave": "", "valor": ""},
        {"clave": "--- REJILLA BARRIDA ---", "valor": ""},
    ]
    for k, v in d["rejilla"].items():
        filas.append({"clave": k, "valor": ", ".join(str(x) for x in v)})
    filas.append({"clave": "", "valor": ""})
    filas.append({"clave": "--- PARAMETROS FIJOS ---", "valor": ""})
    for k, v in cfg.items():
        if k not in d["rejilla"]:
            filas.append({"clave": k, "valor": str(v)})
    filas.append({"clave": "", "valor": ""})
    filas.append({"clave": "--- CALIBRADO vigente ---", "valor": ""})
    for k, v in C.CALIBRADO.items():
        filas.append({"clave": k, "valor": "(sin fijar)" if v is None else str(v)})
    return pd.DataFrame(filas)


def exportar_excel(exp_id: str, runs: pd.DataFrame, res: pd.DataFrame,
                   ranking: Optional[pd.DataFrame] = None,
                   instancias_ids: Optional[List[str]] = None,
                   semillas: Optional[List[int]] = None,
                   verbose: bool = True) -> Optional[str]:
    """Escribe un .xlsx con todas las hojas. Los CSV siguen siendo el formato
    primario; el Excel es la copia comoda de consultar."""
    ruta = _rutas.ruta_salida(exp_id, "resultados", ext="xlsx")
    try:
        with pd.ExcelWriter(ruta, engine="openpyxl") as xls:
            _hoja_config(exp_id, instancias_ids or C.INSTANCIAS,
                         semillas or C.SEMILLAS).to_excel(
                xls, sheet_name="config", index=False)
            res.to_excel(xls, sheet_name="resumen", index=False)
            if ranking is not None and not ranking.empty:
                ranking.to_excel(xls, sheet_name="ranking", index=False)
            runs.to_excel(xls, sheet_name="runs", index=False)
        if verbose:
            print(f"  excel    -> {ruta}")
        return ruta
    except Exception as exc:
        if verbose:
            print(f"  [aviso] no se pudo escribir el Excel ({exc}). Los CSV si estan.")
        return None


# ---------------------------------------------------------------------------
# LaTeX
# ---------------------------------------------------------------------------
def tabla_latex(res: pd.DataFrame, exp_id: str, nombre_exp: Optional[str] = None,
                cols: Optional[List[str]] = None,
                etiqueta_param: str = "Configuración",
                guardar: bool = True) -> str:
    """Genera la tabla LaTeX del resumen, con la fila ganadora en negrita.

    Une 'n_factibles' y 'n_ejec' en una sola columna 'Factibles' del tipo 9/10,
    que es la forma compacta de acompanar cada media de su fiabilidad.
    """
    if res.empty:
        return ""

    res = res.copy()
    res["factibles"] = (res["n_factibles"].astype(str) + "/"
                        + res["n_ejec"].astype(str))
    cols = cols or ["instancia", "id_config", "factibles", "lcoh_media",
                    "lcoh_std", "lcoh_mejor", "tiempo_medio_s"]

    alineacion = "l" * 3 + "r" * (len(cols) - 3)
    cabecera = " & ".join(
        f"\\textbf{{{CABECERAS.get(c, c)}}}" for c in cols) + r" \\"

    lineas = [
        r"\begin{table}[H]",
        r"    \centering",
        r"    \small",
        r"    \renewcommand{\arraystretch}{1.25}",
        f"    \\begin{{tabular}}{{{alineacion}}}",
        r"        \hline",
        "        " + cabecera,
        r"        \hline",
    ]

    inst_previa = None
    for _, r in res.iterrows():
        if inst_previa is not None and r["instancia"] != inst_previa:
            lineas.append(r"        \hline")
        inst_previa = r["instancia"]

        celdas = []
        for c in cols:
            v = r.get(c)
            if c in ("lcoh_media", "lcoh_std", "lcoh_mejor", "lcoh_peor"):
                txt = _fmt_num(v, 4)
            elif c == "tiempo_medio_s":
                txt = _fmt_num(v, 1)
            elif c == "id_config":
                txt = str(v).replace("_", r"\_")
            else:
                txt = "--" if pd.isna(v) else str(v)
            celdas.append(txt)

        # La configuracion ganadora de cada instancia, en negrita.
        if bool(r.get("es_mejor_en_instancia", False)):
            celdas = [f"\\textbf{{{c}}}" for c in celdas]
        lineas.append("        " + " & ".join(celdas) + r" \\")

    titulo = nombre_exp or exp_id
    lineas += [
        r"        \hline",
        r"    \end{tabular}",
        f"    \\caption{{Resultados de la {titulo.lower()}. El LCOH medio se calcula "
        r"sobre las ejecuciones factibles; la columna \textbf{Factibles} indica "
        r"cuántas de las ejecuciones totales alcanzaron una solución factible. "
        r"En negrita, la mejor configuración de cada instancia.}",
        f"    \\label{{tab:calib_{exp_id.lower()}}}",
        r"\end{table}",
    ]
    tex = "\n".join(lineas)

    if guardar:
        ruta = os.path.join(_rutas.dir_experimento(exp_id), f"{exp_id}_tabla.tex")
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write(tex + "\n")
    return tex


def exportar_todo(exp_id: str, runs: pd.DataFrame, res: pd.DataFrame,
                  ranking: Optional[pd.DataFrame] = None,
                  nombre_exp: Optional[str] = None,
                  instancias_ids: Optional[List[str]] = None,
                  semillas: Optional[List[int]] = None,
                  verbose: bool = True) -> Dict[str, Optional[str]]:
    """Excel + tabla LaTeX de una sola llamada."""
    ruta_xlsx = exportar_excel(exp_id, runs, res, ranking,
                               instancias_ids, semillas, verbose)
    tabla_latex(res, exp_id, nombre_exp)
    ruta_tex = os.path.join(_rutas.dir_experimento(exp_id), f"{exp_id}_tabla.tex")
    if verbose:
        print(f"  latex    -> {ruta_tex}")
    return {"xlsx": ruta_xlsx, "tex": ruta_tex}
