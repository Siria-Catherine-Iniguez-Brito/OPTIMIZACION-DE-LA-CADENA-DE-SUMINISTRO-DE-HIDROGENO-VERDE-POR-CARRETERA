"""
graficas.py
===========

Figuras del marco experimental. Todas leen los CSV ya generados (no re-ejecutan el
GA), de modo que puedes rehacer las figuras sin repetir la campana.

Catalogo
--------
    fig_convergencia         curva de convergencia por configuracion (mediana + IQR)
    fig_convergencia_init    variante para el estudio A/B/C de inicializacion
    fig_boxplot              distribucion del LCOH final sobre las semillas
    fig_barras_lcoh          LCOH medio +/- std por configuracion, un panel por instancia
    fig_factibilidad         tasa de factibilidad por configuracion e instancia
    fig_heatmap              matriz de LCOH medio para calibraciones combinadas
    fig_pareto               LCOH medio frente a tiempo medio, con frontera no dominada

Tratamiento de los infactibles en las figuras
---------------------------------------------
Las curvas y barras de LCOH solo representan ejecuciones factibles. Cuando una
configuracion no tiene ninguna, NO se dibuja un cero (seria enganoso): se omite y
se anota en la figura. La figura de factibilidad es la que da esa informacion, y por
eso conviene mirarla siempre junto a las de LCOH.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

import _rutas
import estilo


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------
def _orden_configs(df: pd.DataFrame) -> List[str]:
    """Orden de aparicion de las configuraciones (= orden de la rejilla)."""
    return list(dict.fromkeys(df["id_config"].tolist()))


def _num(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _titulo(exp_id: str, nombre: Optional[str], sufijo: str) -> str:
    return sufijo or (nombre or exp_id)


# ---------------------------------------------------------------------------
# 1. Convergencia
# ---------------------------------------------------------------------------
def fig_convergencia(conv: pd.DataFrame, exp_id: str, instancia: str,
                     metrica: str = "best_fitness", eje_x: str = "generacion",
                     nombre_exp: Optional[str] = None,
                     banda: bool = True) -> Optional[str]:
    """Convergencia por configuracion: MEDIANA sobre semillas y banda intercuartilica.

    Se usa la mediana y no la media porque una sola ejecucion infactible, con su
    penalizacion de varios ordenes de magnitud, desplazaria la media y aplastaria
    la escala de la figura. La banda IQR muestra la dispersion entre semillas.

    'eje_x' puede ser 'generacion' o 'evaluaciones'. Lo segundo es lo correcto
    cuando se comparan tamanos de poblacion distintos (experimento E11).
    """
    sub = conv[conv["instancia"] == instancia]
    if sub.empty:
        return None

    estilo.aplicar_estilo()
    fig, ax = plt.subplots(figsize=(7.2, 4.4))

    configs = _orden_configs(sub)
    for i, idc in enumerate(configs):
        d = sub[sub["id_config"] == idc]
        if d.empty:
            continue
        piv = d.pivot_table(index=eje_x, columns="semilla",
                            values=metrica, aggfunc="first").sort_index()
        if piv.empty:
            continue
        med = piv.median(axis=1, skipna=True)
        ax.plot(med.index, med.values, label=idc,
                color=estilo.color(i), linestyle=estilo.linea(i),
                marker=estilo.marcador(i), markevery=max(1, len(med) // 12))
        if banda and piv.shape[1] > 2:
            q1 = piv.quantile(0.25, axis=1)
            q3 = piv.quantile(0.75, axis=1)
            ax.fill_between(piv.index, q1.values, q3.values,
                            color=estilo.color(i), alpha=0.13, linewidth=0)

    es_lcoh = metrica == "best_lcoh"
    ax.set_xlabel("Generación" if eje_x == "generacion" else "Evaluaciones de fitness")
    ax.set_ylabel(estilo.etiqueta_eje_lcoh() if es_lcoh else estilo.etiqueta_eje_fitness())
    if not es_lcoh:
        # La penalizacion domina las primeras generaciones: en escala logaritmica
        # se ve tanto la caida inicial como el ajuste fino del final.
        ax.set_yscale("log")
    ax.set_title(_titulo(exp_id, nombre_exp, f"Convergencia · instancia {instancia}"))
    ax.legend(title="Configuración", ncol=2 if len(configs) > 5 else 1)

    ruta = _rutas.ruta_figura(exp_id, f"convergencia_{instancia}_{metrica}_{eje_x}.png")
    return estilo.guardar(fig, ruta)


def fig_convergencia_init(conv: pd.DataFrame, exp_id: str, instancia: str,
                          nombre_exp: Optional[str] = None) -> Optional[str]:
    """Convergencia agrupada por estrategia de inicializacion (A / B / C).

    Es la figura central del estudio de inicializacion: responde si arrancar desde
    la solucion del Nivel 1 (B) parte de un fitness mas bajo y converge antes que
    el arranque aleatorio (A), o si la ventaja se diluye al cabo de unas
    generaciones. El primer punto de cada curva es la calidad de la POBLACION
    INICIAL, antes de evolucionar: ahi se ve el efecto del warm start.
    """
    sub = conv[conv["instancia"] == instancia].copy()
    if sub.empty:
        return None

    def grupo(idc: str) -> str:
        for t in ("A", "B", "C"):
            if f"init={t}" in idc:
                return t
        return idc
    sub["grupo"] = sub["id_config"].map(grupo)

    etiquetas = {"A": "A · aleatoria", "B": "B · semilla Nivel 1",
                 "C": "C · mixta"}

    estilo.aplicar_estilo()
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    for i, g in enumerate(sorted(sub["grupo"].unique())):
        d = sub[sub["grupo"] == g]
        piv = d.pivot_table(index="generacion", columns=["id_config", "semilla"],
                            values="best_fitness", aggfunc="first").sort_index()
        if piv.empty:
            continue
        med = piv.median(axis=1, skipna=True)
        ax.plot(med.index, med.values, label=etiquetas.get(g, g),
                color=estilo.color(i), linestyle=estilo.linea(i),
                marker=estilo.marcador(i), markevery=max(1, len(med) // 12))
        if piv.shape[1] > 2:
            ax.fill_between(piv.index, piv.quantile(0.25, axis=1).values,
                            piv.quantile(0.75, axis=1).values,
                            color=estilo.color(i), alpha=0.13, linewidth=0)

    ax.set_yscale("log")
    ax.set_xlabel("Generación")
    ax.set_ylabel(estilo.etiqueta_eje_fitness())
    ax.set_title(_titulo(exp_id, nombre_exp, f"Inicialización de la población · {instancia}"))
    ax.legend(title="Población inicial")
    ruta = _rutas.ruta_figura(exp_id, f"convergencia_init_{instancia}.png")
    return estilo.guardar(fig, ruta)


# ---------------------------------------------------------------------------
# 2. Distribucion del resultado final
# ---------------------------------------------------------------------------
def fig_boxplot(runs: pd.DataFrame, exp_id: str, instancia: str,
                nombre_exp: Optional[str] = None) -> Optional[str]:
    """Distribucion del LCOH final por configuracion (una caja por configuracion).

    Complementa a la media del resumen: dos configuraciones con medias parecidas
    pueden tener dispersiones muy distintas, y conviene preferir la estable.
    Los puntos individuales (una por semilla) se superponen a la caja.
    """
    sub = runs[(runs["instancia"] == instancia)].copy()
    sub["factible"] = sub["factible"].astype(str).str.lower().isin(["true", "1"])
    sub = sub[sub["factible"]]
    sub["lcoh"] = _num(sub["lcoh"])
    sub = sub.dropna(subset=["lcoh"])
    if sub.empty:
        return None

    configs = [c for c in _orden_configs(runs[runs["instancia"] == instancia])
               if c in set(sub["id_config"])]
    datos = [sub[sub["id_config"] == c]["lcoh"].values for c in configs]
    n_sin = runs[runs["instancia"] == instancia]["id_config"].nunique() - len(configs)

    estilo.aplicar_estilo()
    fig, ax = plt.subplots(figsize=(max(6.4, 1.15 * len(configs) + 2), 4.4))
    bp = ax.boxplot(datos, labels=configs, patch_artist=True, widths=0.6,
                    medianprops=dict(color="black", linewidth=1.4),
                    flierprops=dict(marker="o", markersize=3, alpha=0.6))
    for i, caja in enumerate(bp["boxes"]):
        caja.set_facecolor(estilo.color(i))
        caja.set_alpha(0.35)
        caja.set_edgecolor(estilo.color(i))

    rng = np.random.default_rng(0)         # dispersion horizontal reproducible
    for i, vals in enumerate(datos, start=1):
        ax.scatter(i + rng.uniform(-0.11, 0.11, len(vals)), vals,
                   s=14, color=estilo.color(i - 1), alpha=0.85, zorder=3,
                   edgecolors="white", linewidths=0.4)

    ax.set_ylabel(estilo.etiqueta_eje_lcoh())
    ax.set_xlabel("Configuración")
    ax.set_title(_titulo(exp_id, nombre_exp, f"Distribución del LCOH final · {instancia}"))

    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    estilo.nota_infactibles(ax, n_sin)
    ruta = _rutas.ruta_figura(exp_id, f"boxplot_{instancia}.png")
    return estilo.guardar(fig, ruta)


def fig_barras_lcoh(res: pd.DataFrame, exp_id: str,
                    nombre_exp: Optional[str] = None) -> Optional[str]:
    """LCOH medio +/- desviacion tipica por configuracion, un panel por instancia.

    Es la version grafica de resumen.csv: la barra mas baja de cada panel es la
    configuracion ganadora en esa instancia, y se resalta. Las barras de error
    (una desviacion tipica) avisan de las configuraciones inestables.
    """
    res = res.copy()
    res["lcoh_media"] = _num(res["lcoh_media"])
    if res["lcoh_media"].notna().sum() == 0:
        return None

    instancias = list(dict.fromkeys(res["instancia"].tolist()))
    configs = _orden_configs(res)

    estilo.aplicar_estilo()
    fig, axes = plt.subplots(1, len(instancias), sharey=False,
                             figsize=(max(5.2, 3.6 * len(instancias)), 4.2))
    if len(instancias) == 1:
        axes = [axes]

    for ax, inst in zip(axes, instancias):
        d = res[res["instancia"] == inst].set_index("id_config").reindex(configs)
        medias = d["lcoh_media"].values
        errs = _num(d["lcoh_std"]).fillna(0.0).values
        validos = ~pd.isna(medias)

        colores = [estilo.COLOR_GANADOR if bool(g) else estilo.COLOR_NEUTRO
                   for g in d["es_mejor_en_instancia"].fillna(False)]
        ax.bar(range(len(configs)), np.where(validos, medias, 0),
               yerr=np.where(validos, errs, 0), color=colores, alpha=0.9,
               capsize=3, error_kw=dict(lw=1, ecolor="#444444"))

        ax.set_xticks(range(len(configs)))
        ax.set_xticklabels(configs, rotation=35, ha="right", fontsize=8)
        ax.set_title(f"{inst}")
        if ax is axes[0]:
            ax.set_ylabel(estilo.etiqueta_eje_lcoh())
        # Escala centrada en el rango util: si empieza en 0 las diferencias
        # relevantes entre configuraciones resultan invisibles.
        vals = medias[validos]
        if len(vals):
            lo, hi = float(np.min(vals - errs[validos])), float(np.max(vals + errs[validos]))
            margen = max((hi - lo) * 0.25, hi * 0.01)
            ax.set_ylim(max(0, lo - margen), hi + margen)
        estilo.nota_infactibles(ax, int((~validos).sum()))

    fig.suptitle(_titulo(exp_id, nombre_exp, "LCOH medio por configuración"), y=1.02)

    ruta = _rutas.ruta_figura(exp_id, "barras_lcoh_medio.png")
    return estilo.guardar(fig, ruta)


# ---------------------------------------------------------------------------
# 3. Factibilidad
# ---------------------------------------------------------------------------
def fig_factibilidad(res: pd.DataFrame, exp_id: str,
                     nombre_exp: Optional[str] = None) -> Optional[str]:
    """Tasa de factibilidad por configuracion e instancia (barras agrupadas).

    Imprescindible junto a cualquier figura de LCOH: una media excelente calculada
    sobre 3 de 10 ejecuciones no es un buen resultado, y esta figura lo delata.
    """
    if res.empty:
        return None
    instancias = list(dict.fromkeys(res["instancia"].tolist()))
    configs = _orden_configs(res)

    estilo.aplicar_estilo()
    fig, ax = plt.subplots(figsize=(max(6.4, 1.0 * len(configs) + 2), 4.0))
    ancho = 0.8 / max(1, len(instancias))

    for i, inst in enumerate(instancias):
        d = res[res["instancia"] == inst].set_index("id_config").reindex(configs)
        vals = _num(d["tasa_factibilidad"]).fillna(0.0).values * 100
        pos = np.arange(len(configs)) + i * ancho - 0.4 + ancho / 2
        ax.bar(pos, vals, width=ancho, label=inst, color=estilo.color(i), alpha=0.9)

    ax.axhline(100, color=estilo.COLOR_FACTIBLE, linestyle="--", linewidth=1,
               label="100 % factible")
    ax.set_xticks(range(len(configs)))
    ax.set_xticklabels(configs, rotation=35, ha="right", fontsize=8)
    ax.set_ylabel("Ejecuciones factibles (%)")
    ax.set_ylim(0, 108)
    ax.set_title(_titulo(exp_id, nombre_exp, "Tasa de factibilidad por configuración"))
    ax.legend(ncol=len(instancias) + 1)
    ruta = _rutas.ruta_figura(exp_id, "factibilidad.png")
    return estilo.guardar(fig, ruta)


# ---------------------------------------------------------------------------
# 4. Calibraciones combinadas: mapa de calor
# ---------------------------------------------------------------------------
def fig_heatmap(res: pd.DataFrame, exp_id: str, param_x: str, param_y: str,
                instancia: str, nombre_exp: Optional[str] = None,
                valor: str = "lcoh_media") -> Optional[str]:
    """Matriz de LCOH medio para una calibracion combinada (PM x PC, N x G).

    Las celdas sin ninguna ejecucion factible quedan en blanco y rotuladas 'n.f.',
    en lugar de con un cero que distorsionaria la escala de color.
    """
    sub = res[res["instancia"] == instancia]
    if sub.empty or param_x not in sub.columns or param_y not in sub.columns:
        return None

    piv = sub.pivot_table(index=param_y, columns=param_x, values=valor,
                          aggfunc="mean")
    if piv.empty:
        return None

    estilo.aplicar_estilo()
    fig, ax = plt.subplots(figsize=(1.15 * len(piv.columns) + 3,
                                    0.85 * len(piv.index) + 2.6))
    datos = piv.values.astype(float)
    im = ax.imshow(datos, cmap=estilo.CMAP_CALOR, aspect="auto")
    ax.set_xticks(range(len(piv.columns)), [f"{c:g}" if isinstance(c, (int, float))
                                           else str(c) for c in piv.columns])
    ax.set_yticks(range(len(piv.index)), [f"{r:g}" if isinstance(r, (int, float))
                                          else str(r) for r in piv.index])
    ax.set_xlabel(param_x)
    ax.set_ylabel(param_y)
    ax.grid(False)

    mejor = np.nanmin(datos) if np.isfinite(datos).any() else None
    for a in range(datos.shape[0]):
        for b in range(datos.shape[1]):
            v = datos[a, b]
            if np.isnan(v):
                ax.text(b, a, "n.f.", ha="center", va="center",
                        fontsize=8, color="#666666", style="italic")
                continue
            es_mejor = mejor is not None and abs(v - mejor) < 1e-12
            ax.text(b, a, f"{v:.3f}", ha="center", va="center", fontsize=8.5,
                    color="white" if v > np.nanmedian(datos) else "black",
                    fontweight="bold" if es_mejor else "normal")
            if es_mejor:
                ax.add_patch(plt.Rectangle((b - 0.5, a - 0.5), 1, 1, fill=False,
                                           edgecolor="#D55E00", linewidth=2.5))

    fig.colorbar(im, ax=ax, label=estilo.etiqueta_eje_lcoh(), shrink=0.85)
    ax.set_title(_titulo(exp_id, nombre_exp, f"LCOH medio · instancia {instancia}"))

    ruta = _rutas.ruta_figura(exp_id, f"heatmap_{param_x}_{param_y}_{instancia}.png")
    return estilo.guardar(fig, ruta)


# ---------------------------------------------------------------------------
# 5. Compromiso calidad / tiempo
# ---------------------------------------------------------------------------
def fig_pareto(res: pd.DataFrame, exp_id: str, instancia: str,
               nombre_exp: Optional[str] = None) -> Optional[str]:
    """LCOH medio frente a tiempo medio, con la frontera no dominada resaltada.

    Justifica elecciones del tipo 'N=80 mejora tan poco sobre N=40 que no compensa
    duplicar el tiempo', que es exactamente el razonamiento que se espera en la
    calibracion del tamano de poblacion y del numero de generaciones.
    """
    sub = res[res["instancia"] == instancia].copy()
    sub["lcoh_media"] = _num(sub["lcoh_media"])
    sub["tiempo_medio_s"] = _num(sub["tiempo_medio_s"])
    sub = sub.dropna(subset=["lcoh_media", "tiempo_medio_s"])
    if sub.empty:
        return None

    estilo.aplicar_estilo()
    fig, ax = plt.subplots(figsize=(6.8, 4.6))

    # Frontera de Pareto: minimizar tiempo y LCOH a la vez.
    puntos = sub.sort_values("tiempo_medio_s")
    frontera, mejor = [], np.inf
    for _, r in puntos.iterrows():
        if r["lcoh_media"] < mejor - 1e-12:
            frontera.append((r["tiempo_medio_s"], r["lcoh_media"]))
            mejor = r["lcoh_media"]
    if frontera:
        fx, fy = zip(*frontera)
        ax.plot(fx, fy, color=estilo.COLOR_NEUTRO, linestyle="--", linewidth=1.2,
                zorder=1, label="Frontera no dominada")

    for i, (_, r) in enumerate(sub.iterrows()):
        ax.scatter(r["tiempo_medio_s"], r["lcoh_media"], s=70,
                   color=estilo.color(i), marker=estilo.marcador(i),
                   edgecolors="white", linewidths=0.6, zorder=3)
        ax.annotate(r["id_config"], (r["tiempo_medio_s"], r["lcoh_media"]),
                    textcoords="offset points", xytext=(7, 4), fontsize=8)

    ax.set_xlabel("Tiempo medio de ejecución (s)")
    ax.set_ylabel(estilo.etiqueta_eje_lcoh())
    ax.set_title(_titulo(exp_id, nombre_exp, f"Compromiso calidad–tiempo · {instancia}"))

    ax.legend()
    ruta = _rutas.ruta_figura(exp_id, f"pareto_{instancia}.png")
    return estilo.guardar(fig, ruta)


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------
def generar_todas(exp_id: str, res: pd.DataFrame, runs: pd.DataFrame,
                  conv: Optional[pd.DataFrame] = None,
                  cols_rejilla: Optional[List[str]] = None,
                  nombre_exp: Optional[str] = None,
                  presupuesto_cte: bool = False,
                  verbose: bool = True) -> List[str]:
    """Genera todas las figuras que tengan sentido para este experimento."""
    generadas: List[str] = []
    cols_rejilla = cols_rejilla or []
    instancias = list(dict.fromkeys(res["instancia"].tolist())) if not res.empty else []

    def _reg(ruta: Optional[str]) -> None:
        if ruta:
            generadas.append(ruta)
            if verbose:
                print(f"    figura -> {os.path.basename(ruta)}")

    _reg(fig_factibilidad(res, exp_id, nombre_exp))
    _reg(fig_barras_lcoh(res, exp_id, nombre_exp))

    for inst in instancias:
        _reg(fig_boxplot(runs, exp_id, inst, nombre_exp))
        _reg(fig_pareto(res, exp_id, inst, nombre_exp))

        if conv is not None and not conv.empty:
            eje = "evaluaciones" if presupuesto_cte else "generacion"
            _reg(fig_convergencia(conv, exp_id, inst, "best_fitness", eje, nombre_exp))
            _reg(fig_convergencia(conv, exp_id, inst, "best_lcoh", eje, nombre_exp))
            if "tipo_init" in cols_rejilla:
                _reg(fig_convergencia_init(conv, exp_id, inst, nombre_exp))

    # Mapa de calor solo si la rejilla es de dos parametros numericos.
    if len(cols_rejilla) == 2:
        px, py = cols_rejilla
        for inst in instancias:
            _reg(fig_heatmap(res, exp_id, px, py, inst, nombre_exp))

    return generadas
