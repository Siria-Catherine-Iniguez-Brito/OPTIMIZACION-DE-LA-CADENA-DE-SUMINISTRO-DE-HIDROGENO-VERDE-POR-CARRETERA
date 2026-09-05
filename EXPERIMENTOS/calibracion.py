"""
calibracion.py
==============

Bucle principal de una campana de calibracion:

    para cada INSTANCIA
        para cada CONFIGURACION de la rejilla
            para cada SEMILLA del bloque comun
                ejecutar el GA  (runner.ejecutar_una)

y escritura de los CSV de salida (runs, convergencia, resumen, ranking).

Decisiones de diseno
--------------------
  - SEMILLAS PAREADAS: el orden de los bucles garantiza que todas las
    configuraciones se ejecuten con EXACTAMENTE las mismas semillas, en el mismo
    orden. Es lo que hace comparables PM=0.1 y PM=0.2: misma poblacion inicial.
  - ESCRITURA INCREMENTAL: cada fila se vuelca a runs.csv en cuanto termina. Si
    cortas la campana (o se cae la maquina) no pierdes lo ya calculado.
  - REANUDACION: con reanudar=True se leen las filas ya presentes en runs.csv y se
    saltan las combinaciones (instancia, id_config, semilla) ya hechas.
  - UNA EJECUCION QUE FALLA NO TUMBA LA CAMPANA: runner captura la excepcion y
    devuelve una fila con la columna 'error' rellena.
"""

from __future__ import annotations

import csv
import os
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

import _rutas
import agregacion
import config_experimentos as C
import instancias as ins
import rejillas
import runner


# ---------------------------------------------------------------------------
# Escritura incremental de CSV
# ---------------------------------------------------------------------------
class EscritorCSV:
    """Escribe filas de dict a un CSV, creando la cabecera la primera vez.

    Mantiene el fichero abierto y hace flush tras cada fila: si la campana se
    interrumpe, lo escrito hasta ese momento es un CSV valido.
    """

    def __init__(self, ruta: str, columnas: List[str], anadir: bool = False):
        self.ruta = ruta
        self.columnas = columnas
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        existe = os.path.isfile(ruta) and os.path.getsize(ruta) > 0
        modo = "a" if (anadir and existe) else "w"
        self._fh = open(ruta, modo, newline="", encoding="utf-8")
        self._w = csv.DictWriter(self._fh, fieldnames=columnas, extrasaction="ignore")
        if modo == "w" or not existe:
            self._w.writeheader()
            self._fh.flush()

    def escribir(self, fila: Dict[str, Any]) -> None:
        self._w.writerow({c: _celda(fila.get(c)) for c in self.columnas})
        self._fh.flush()

    def escribir_muchas(self, filas: List[Dict[str, Any]]) -> None:
        for f in filas:
            self._w.writerow({c: _celda(f.get(c)) for c in self.columnas})
        self._fh.flush()

    def cerrar(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass


def _celda(v: Any) -> Any:
    """None -> celda VACIA (nunca 0). Critico para el LCOH de los infactibles:
    un 0 se colaria en las medias y falsearia la calibracion."""
    return "" if v is None else v


# ---------------------------------------------------------------------------
# Reanudacion
# ---------------------------------------------------------------------------
def _ya_hechas(ruta_runs: str) -> Set[Tuple[str, str, int]]:
    """Combinaciones (instancia, id_config, semilla) ya presentes en runs.csv."""
    if not os.path.isfile(ruta_runs) or os.path.getsize(ruta_runs) == 0:
        return set()
    try:
        df = pd.read_csv(ruta_runs)
        return {(str(r["instancia"]), str(r["id_config"]), int(r["semilla"]))
                for _, r in df.iterrows()}
    except Exception:
        return set()


# ---------------------------------------------------------------------------
# Campana de calibracion
# ---------------------------------------------------------------------------
def ejecutar_calibracion(exp_id: str,
                         instancias_ids: Optional[List[str]] = None,
                         semillas: Optional[List[int]] = None,
                         n_semillas: Optional[int] = None,
                         guardar_convergencia: bool = True,
                         cada_gen: int = 1,
                         reanudar: bool = False,
                         con_ranking: bool = True,
                         verbose: bool = True) -> Dict[str, Any]:
    """Lanza el experimento 'exp_id' completo y devuelve las rutas y los DataFrames.

    Parametros
    ----------
    instancias_ids : lista de alias ('small') o rutas a JSON. Por defecto,
                     config_experimentos.INSTANCIAS.
    semillas       : bloque de semillas. Por defecto, config_experimentos.SEMILLAS.
    n_semillas     : atajo para usar solo las 'n' primeras del bloque (pruebas rapidas).
    cada_gen       : submuestreo del historico de convergencia (1 = todas las
                     generaciones). Con instancias grandes y muchas generaciones,
                     usar 5 o 10 evita un CSV innecesariamente enorme.
    reanudar       : salta las combinaciones ya presentes en runs.csv.
    """
    definicion = C.experimento(exp_id)
    rejilla = definicion["rejilla"]
    irrelevantes = definicion.get("irrelevantes")
    nombre_exp = definicion.get("nombre", exp_id)

    instancias_ids = instancias_ids or C.INSTANCIAS
    semillas = list(semillas or C.SEMILLAS)
    if n_semillas:
        semillas = semillas[:n_semillas]

    cfg_base = C.config_base_efectiva(exp_id)
    combos = rejillas.expandir(rejilla, irrelevantes)
    cols_rejilla = rejillas.columnas_rejilla(rejilla)

    ruta_runs = _rutas.ruta_salida(exp_id, "runs")
    ruta_conv = _rutas.ruta_salida(exp_id, "convergencia")

    hechas = _ya_hechas(ruta_runs) if reanudar else set()

    # Columnas de runs: las estandar mas las de la rejilla (para leer la tabla
    # sin tener que descifrar el id_config).
    cols_runs = list(runner.COLS_RUNS)
    for c in cols_rejilla:
        if c not in cols_runs:
            cols_runs.insert(cols_runs.index("semilla"), c)

    cols_conv = ["exp_id", "instancia", "id_config", "semilla", "generacion",
                 "evaluaciones", "best_fitness", "media_fitness", "best_lcoh",
                 "factible_best"]

    total = len(instancias_ids) * len(combos) * len(semillas)
    if verbose:
        print("=" * 72)
        print(f"{exp_id}  |  {nombre_exp}")
        print("=" * 72)
        print(f"  Instancias      : {', '.join(ins.etiqueta(i) for i in instancias_ids)}")
        print(f"  Configuraciones : {len(combos)}  ({', '.join(t[0] for t in combos[:6])}"
              f"{' ...' if len(combos) > 6 else ''})")
        print(f"  Semillas        : {len(semillas)}  {semillas}")
        print(f"  Ejecuciones     : {total}"
              + (f"  ({len(hechas)} ya hechas, se saltan)" if hechas else ""))
        print(f"  Parametros fijos: N={cfg_base['tam_poblacion']}, "
              f"G={cfg_base['n_generaciones']}, PC={cfg_base['prob_cruce']}, "
              f"PM={cfg_base['prob_mutacion']}, k={cfg_base['k_torneo']}, "
              f"init={cfg_base['tipo_init']}")
        print()

    esc_runs = EscritorCSV(ruta_runs, cols_runs, anadir=reanudar)
    esc_conv = (EscritorCSV(ruta_conv, cols_conv, anadir=reanudar)
                if guardar_convergencia else None)

    hecho = 0
    t_ini = time.perf_counter()

    try:
        for inst_id in instancias_ids:
            etiq = ins.etiqueta(inst_id)
            if verbose:
                inst = ins.cargar(inst_id)
                print(f"[{etiq}]  |P|={len(inst.P)} |J|={len(inst.J)} "
                      f"|K|={len(inst.K)} HTotal={inst.HTotal:.0f} kg/dia")

            for id_cfg, valores, params in combos:
                cfg = dict(cfg_base)
                cfg.update(params)

                lcoh_ok, n_ok = [], 0
                for rep, sem in enumerate(semillas):
                    if (etiq, id_cfg, int(sem)) in hechas:
                        hecho += 1
                        continue

                    fila, filas_conv = runner.ejecutar_una(
                        exp_id=exp_id, calibracion=nombre_exp, inst_id=inst_id,
                        cfg=cfg, semilla=sem, id_config=id_cfg, rep=rep,
                        guardar_convergencia=guardar_convergencia,
                        cada_gen=cada_gen, verbose=verbose,
                    )
                    # Las columnas de la rejilla, explicitas en el CSV.
                    for c in cols_rejilla:
                        if c in valores:
                            fila[c] = rejillas._fmt(valores[c]) if isinstance(
                                valores[c], (list, tuple)) else valores[c]

                    esc_runs.escribir(fila)
                    if esc_conv and filas_conv:
                        esc_conv.escribir_muchas(filas_conv)

                    if fila.get("factible") and fila.get("lcoh") is not None:
                        lcoh_ok.append(float(fila["lcoh"]))
                        n_ok += 1
                    hecho += 1

                if verbose:
                    n_tot = len([s for s in semillas if (etiq, id_cfg, int(s)) not in hechas])
                    if n_tot:
                        med = f"{sum(lcoh_ok)/len(lcoh_ok):.4f}" if lcoh_ok else "sin factibles"
                        pct = 100.0 * hecho / total if total else 100.0
                        print(f"   {id_cfg:<28} fact={n_ok}/{n_tot}  "
                              f"LCOH medio={med:<14}  [{pct:5.1f}%]")
            if verbose:
                print()
    finally:
        esc_runs.cerrar()
        if esc_conv:
            esc_conv.cerrar()

    # ------------------------------------------------------------------
    # Agregacion
    # ------------------------------------------------------------------
    runs = pd.read_csv(ruta_runs)
    res = agregacion.construir_resumen(runs, cols_rejilla)
    ruta_res = _rutas.ruta_salida(exp_id, "resumen")
    res.to_csv(ruta_res, index=False)

    rk, ruta_rk = None, None
    if con_ranking and res["instancia"].nunique() >= 1:
        rk = agregacion.construir_ranking(res)
        ruta_rk = _rutas.ruta_salida(exp_id, "ranking")
        rk.to_csv(ruta_rk, index=False)

    if verbose:
        print(f"Completado en {time.perf_counter() - t_ini:.1f} s")
        print(f"  runs     -> {ruta_runs}")
        print(f"  resumen  -> {ruta_res}")
        if ruta_rk:
            print(f"  ranking  -> {ruta_rk}")
        if guardar_convergencia:
            print(f"  converg. -> {ruta_conv}")
        agregacion.imprimir_sugerencias(res, cols_rejilla, C.CALIBRADO)

    return {
        "exp_id": exp_id, "nombre": nombre_exp,
        "runs": runs, "resumen": res, "ranking": rk,
        "cols_rejilla": cols_rejilla,
        "ruta_runs": ruta_runs, "ruta_resumen": ruta_res,
        "ruta_ranking": ruta_rk, "ruta_convergencia": ruta_conv,
    }


def reagregar(exp_id: str, con_ranking: bool = True) -> Dict[str, Any]:
    """Recalcula resumen y ranking a partir de un runs.csv ya existente, sin
    volver a ejecutar el GA. Util si cambias un criterio de agregacion."""
    ruta_runs = _rutas.ruta_salida(exp_id, "runs")
    if not os.path.isfile(ruta_runs):
        raise FileNotFoundError(f"No existe {ruta_runs}. Ejecuta antes el experimento.")
    runs = pd.read_csv(ruta_runs)
    cols_rejilla = rejillas.columnas_rejilla(C.experimento(exp_id)["rejilla"])
    res = agregacion.construir_resumen(runs, cols_rejilla)
    res.to_csv(_rutas.ruta_salida(exp_id, "resumen"), index=False)
    rk = None
    if con_ranking:
        rk = agregacion.construir_ranking(res)
        rk.to_csv(_rutas.ruta_salida(exp_id, "ranking"), index=False)
    return {"exp_id": exp_id, "runs": runs, "resumen": res, "ranking": rk,
            "cols_rejilla": cols_rejilla}
