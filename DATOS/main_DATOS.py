"""
main_DATOS.py
=============
Orquesta la generacion de TODOS los datos del TFM de una sola vez:
  1) Geocodifica coordenadas (Nominatim)       -> Tablas/coords_cache.json
  2) Genera la trazabilidad                     -> Tablas/trazabilidad_coordenadas.csv
  3) Genera las instancias small/medium/large   -> Tablas/instancia_*.json
  4) Dibuja los nodos sobre la imagen de fondo  -> figuras/HV_D_MapaNodos.png
  5) Dibuja el perfil renovable solar vs eolica -> figuras/HV_D_PerfilRenovable.png

Idempotente: si un fichero ya existe, no se rehace. Usa --forzar para regenerar.

Estructura esperada:
    DATOS/
      catalogo_nodos.py, descargar_*.py, generar_*.py, main_DATOS.py
      Figuras/   (contiene la imagen de fondo del mapa de Espana)
      Tablas/    (se crea sola; aqui van instancias, cache y trazabilidad)

Uso:
    python main_DATOS.py --forzar
    python main_DATOS.py --forzar --mapa_fondo "Figuras/Mapa_ProvinciasEspana.png"
    python main_DATOS.py --forzar --extent -9.7 4.6 35.7 44.0   # ajuste fino del mapa
    python main_DATOS.py --offline                              # sin internet
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import defaultdict

# Paleta gráfica común del TFM
COLOR_VERDE_ABETO = "#0E6E4F"
COLOR_AZUL_PETROLEO = "#2E86AB"
COLOR_VERDE_AZULADO = "#4FB8A0"
COLOR_AMBAR = "#E0A72E"
COLOR_VERDE_SALVIA = "#8FBF6B"
COLOR_AZUL_PIZARRA = "#5B6C8F"
COLOR_GRAFITO = "#3A3A3A"

# Colores específicos de las fuentes renovables
COLOR_SOLAR = COLOR_VERDE_ABETO
COLOR_EOLICA = COLOR_AZUL_PETROLEO

# --- Rutas base (todo relativo a la carpeta DATOS donde vive este fichero) ---
AQUI = os.path.dirname(os.path.abspath(__file__))
CARPETA_TABLAS = os.path.join(AQUI, "Tablas")
CARPETA_FIGURAS = os.path.join(AQUI, "Figuras")

# Nombres de las figuras de salida.
FIG_MAPA = "HV_D_MapaNodos.png"
FIG_PERFIL = "HV_D_PerfilRenovable.png"

# Plantilla de fondo del mapa (dentro de figuras/) y su extent calibrado.
MAPA_FONDO_DEFECTO = "Mapa_ProvinciasEspana.png"
EXTENT_DEFECTO = [-9.55, 4.45, 35.85, 43.85]

from catalogo_nodos import CLIENTES, PLANTAS, consultas_nodos
from descargar_coordenadas import geocodificar_nodos
import generar_instancia as gi
import generar_trazabilidad as gt


# ----------------------------------------------------------------------------
# Utilidades comunes
# ----------------------------------------------------------------------------
def _nuevo_plot(figsize):
    """Crea una figura de matplotlib con backend no interactivo (Agg).
    Centraliza aqui el unico import de matplotlib para no repetirlo en cada paso."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt.subplots(figsize=figsize)


def _existe_salto(ruta, forzar):
    """True si el fichero ya existe y NO se fuerza (hay que saltar el paso)."""
    if os.path.exists(ruta) and not forzar:
        print(f"[=] {ruta} ya existe (salto).")
        return True
    return False


# ============================================================================
# Paso 1: coordenadas (cache)
# ============================================================================
def paso_coordenadas(offline, forzar):
    os.makedirs(CARPETA_TABLAS, exist_ok=True)
    cache_path = os.path.join(CARPETA_TABLAS, "coords_cache.json")
    if os.path.exists(cache_path) and not forzar:
        print(f"[=] Coordenadas ya cacheadas en {cache_path}.")
    else:
        print("[>] Geocodificando coordenadas de los nodos...")
    consultas = consultas_nodos(PLANTAS + CLIENTES)
    coords = geocodificar_nodos(consultas, fallback=gi.FALLBACK_COORDS,
                                cache_path=cache_path, usar_api=not offline)
    print(f"    {len(coords)} nodos disponibles.")
    return coords


# ============================================================================
# Paso 2: trazabilidad
# ============================================================================
def paso_trazabilidad(offline, forzar):
    salida = os.path.join(CARPETA_TABLAS, "trazabilidad_coordenadas.csv")
    if _existe_salto(salida, forzar):
        return
    print("[>] Generando trazabilidad de coordenadas...")
    sys.argv = ["generar_trazabilidad.py"] + (["--offline"] if offline else [])
    gt.main()


# ============================================================================
# Paso 3: instancias
# ============================================================================
def paso_instancias(offline, forzar):
    os.makedirs(CARPETA_TABLAS, exist_ok=True)
    dist = "haversine" if offline else "osrm"
    ren = "sintetico" if offline else "pvgis"
    for tam in ("small", "medium", "large"):
        salida = os.path.join(CARPETA_TABLAS, f"instancia_{tam}.json")
        if _existe_salto(salida, forzar):
            continue
        print(f"[>] Generando instancia_{tam} (dist={dist}, ren={ren})...")
        inst = gi.generar(tam, fuente_dist=dist, fuente_ren=ren, offline_coords=offline)
        gi.guardar(inst, salida)
        HTotal = sum(c["Dem"] for c in inst["clientes"].values())
        print(f"    -> {salida}  (HTotal={HTotal:.0f} kg/dia)")


# ============================================================================
# Paso 4: mapa de nodos sobre la imagen de fondo
# ============================================================================
def _resolver_fondo(mapa_fondo):
    """Devuelve la ruta de la imagen de fondo: la indicada, la plantilla por
    defecto, o la primera imagen de figuras/ (excluyendo las figuras de salida)."""
    if mapa_fondo is None:
        candidata = os.path.join(CARPETA_FIGURAS, MAPA_FONDO_DEFECTO)
        if os.path.exists(candidata):
            return candidata
        imgs = []
        for ext in ("png", "jpg", "jpeg"):
            imgs += glob.glob(os.path.join(CARPETA_FIGURAS, f"*.{ext}"))
        imgs = [c for c in imgs if os.path.basename(c) not in (FIG_MAPA, FIG_PERFIL)]
        return imgs[0] if imgs else None
    if not os.path.isabs(mapa_fondo) and not os.path.exists(mapa_fondo):
        alt = os.path.join(CARPETA_FIGURAS, os.path.basename(mapa_fondo))
        if os.path.exists(alt):
            return alt
    return mapa_fondo


def paso_mapa(coords, mapa_fondo, extent, forzar):
    os.makedirs(CARPETA_FIGURAS, exist_ok=True)
    salida = os.path.join(CARPETA_FIGURAS, FIG_MAPA)
    if _existe_salto(salida, forzar):
        return
    print("[>] Dibujando mapa de nodos geocodificados...")

    mapa_fondo = _resolver_fondo(mapa_fondo)
    ids_pl = [p[0] for p in PLANTAS if p[0] in coords]
    ids_cl = [c[0] for c in CLIENTES if c[0] in coords]

    fig, ax = _nuevo_plot((13, 11))   # figura ancha para que respire

    if mapa_fondo and os.path.exists(mapa_fondo):
        import matplotlib.pyplot as plt
        ax.imshow(plt.imread(mapa_fondo), extent=extent, aspect="auto", zorder=0, alpha=0.9)
        print(f"    fondo: {mapa_fondo}  extent={extent}")
    else:
        print("    [aviso] No se encontro imagen de fondo en figuras/; se dibuja sin mapa.")
    ax.scatter(
        [coords[i][1] for i in ids_cl],
        [coords[i][0] for i in ids_cl],
        c=COLOR_AZUL_PIZARRA,
        label="Clientes",
        s=55,
        zorder=3,
        edgecolors="white",
        linewidths=0.8
    )

    ax.scatter(
        [coords[i][1] for i in ids_pl],
        [coords[i][0] for i in ids_pl],
        c=COLOR_VERDE_ABETO,
        marker="^",
        label="Plantas candidatas",
        s=120,
        zorder=4,
        edgecolors="white",
        linewidths=0.8
    )
    # Nodos que comparten coordenada EXACTA -> una sola etiqueta combinada.
    grupos = defaultdict(list)
    for i in ids_pl + ids_cl:
        la, lo = coords[i]
        grupos[(round(la, 4), round(lo, 4))].append(i)

    textos = []
    for (la, lo), ids in grupos.items():
        ids_ord = sorted(ids)
        etiqueta = " / ".join(ids_ord) if len(ids_ord) <= 2 else f"{ids_ord[0]} (+{len(ids_ord) - 1})"
        textos.append(ax.text(lo, la, etiqueta, fontsize=8, zorder=5,
                              bbox=dict(boxstyle="round,pad=0.15", fc="white",
                                        ec="none", alpha=0.7)))

    # Separacion automatica de etiquetas; si no esta, offset simple.
    try:
        from adjustText import adjust_text
        adjust_text(textos, ax=ax,
                    expand_points=(1.6, 1.8), expand_text=(1.4, 1.6),
                    force_text=(0.5, 0.8), force_points=(0.4, 0.6),
                    arrowprops=dict(arrowstyle="-", color="gray", lw=0.6))
        print("    etiquetas separadas con adjustText.")
    except ImportError:
        print("    [aviso] adjustText no instalado; aplico un offset simple.")
        for t in textos:
            x, y = t.get_position()
            t.set_position((x + 0.06, y + 0.06))

    ax.set_xlim(extent[0], extent[1]); ax.set_ylim(extent[2], extent[3])
    ax.set_xlabel("Longitud"); ax.set_ylabel("Latitud")
    ax.set_title("Nodos geocodificados sobre el mapa de provincias (Nominatim/OSM)")
    ax.legend(loc="lower left", framealpha=0.9)   # abajo-izq: no tapa Cataluna
    ax.grid(alpha=0.25)
    _guardar_fig(fig, salida)


# ============================================================================
# Paso 5: perfil renovable horario (solar vs eolica)
# ============================================================================
def paso_perfil(forzar):
    os.makedirs(CARPETA_FIGURAS, exist_ok=True)
    salida = os.path.join(CARPETA_FIGURAS, FIG_PERFIL)
    if _existe_salto(salida, forzar):
        return
    print("[>] Dibujando perfil renovable (solar vs eolica)...")

    # Lee los perfiles Ren reales de la instancia mas grande disponible.
    ruta_inst = next((p for tam in ("large", "medium", "small")
                      if os.path.exists(p := os.path.join(CARPETA_TABLAS, f"instancia_{tam}.json"))), None)
    if ruta_inst is None:
        print("    [aviso] No hay instancias en tablas/; ejecuta el paso 3 antes.")
        return
    with open(ruta_inst, encoding="utf-8") as f:
        plantas = json.load(f)["plantas"]

    # Elige automaticamente la primera planta SOLAR y la primera EOLICA.
    pid_solar = next((k for k, v in plantas.items() if v["zona_recurso"].startswith("solar")), None)
    pid_eol = next((k for k, v in plantas.items() if v["zona_recurso"] == "eolico"), None)
    if pid_solar is None or pid_eol is None:
        print("    [aviso] No hay a la vez planta solar y eolica en la instancia.")
        return

    solar = plantas[pid_solar]["Ren"]
    eol = plantas[pid_eol]["Ren"]
    horas = list(range(24))

    fig, ax = _nuevo_plot((9, 5))
    ax.plot(
        horas,
        solar,
        marker="o",
        ms=4,
        lw=2.4,
        linestyle="-",
        color=COLOR_SOLAR,
        markerfacecolor="white",
        markeredgecolor=COLOR_SOLAR,
        markeredgewidth=1.4,
        label=f"Planta solar ({pid_solar}, "
            f"{plantas[pid_solar]['provincia']})"
    )

    ax.plot(
        horas,
        eol,
        marker="s",
        ms=4,
        lw=2.4,
        linestyle="--",
        color=COLOR_EOLICA,
        markerfacecolor="white",
        markeredgecolor=COLOR_EOLICA,
        markeredgewidth=1.4,
        label=f"Planta eólica ({pid_eol}, "
            f"{plantas[pid_eol]['provincia']})"
    )
    ax.fill_between(
        horas,
        solar,
        alpha=0.16,
        color=COLOR_SOLAR
    )

    ax.fill_between(
        horas,
        eol,
        alpha=0.10,
        color=COLOR_EOLICA
    )
    ax.set_xlabel("Hora del dia (t)")
    ax.set_ylabel(r"$Ren_{i,t}$  (kg H$_2$/h)")
    ax.set_title("Perfil horario de produccion renovable (dia tipo, T=24)")
    ax.set_xticks(range(0, 24, 2)); ax.set_xlim(0, 23); ax.set_ylim(bottom=0)
    ax.tick_params(
        colors=COLOR_GRAFITO,
        labelcolor=COLOR_GRAFITO
    )

    for spine in ax.spines.values():
        spine.set_color("#B8C4BE")

    ax.set_facecolor("#F8FAF8")
    ax.legend(
        frameon=True,
        facecolor="white",
        edgecolor="#D5DDD8",
        framealpha=0.95
    )

    ax.grid(
        alpha=0.25,
        color=COLOR_AZUL_PIZARRA,
        linestyle=":"
    )
    _guardar_fig(fig, salida)
    print(f"    (solar={pid_solar}, eolica={pid_eol})")


def _guardar_fig(fig, salida):
    """Ajusta, guarda a 200 dpi y cierra la figura. Comun a los pasos 4 y 5."""
    import matplotlib.pyplot as plt
    fig.tight_layout()
    fig.savefig(salida, dpi=200)
    plt.close(fig)
    print(f"    -> {salida}")


# ============================================================================
def main():
    ap = argparse.ArgumentParser(description="Genera todos los datos del TFM de una vez.")
    ap.add_argument("--forzar", action="store_true", help="regenera todo aunque ya exista")
    ap.add_argument("--offline", action="store_true",
                    help="sin internet: cache/fallback + haversine + perfil sintetico")
    ap.add_argument("--mapa_fondo", default=None,
                    help=f"imagen de fondo (por defecto figuras/{MAPA_FONDO_DEFECTO})")
    ap.add_argument("--extent", nargs=4, type=float, default=EXTENT_DEFECTO,
                    metavar=("LONMIN", "LONMAX", "LATMIN", "LATMAX"),
                    help="coordenadas de la imagen de fondo (calibrado para la plantilla por defecto)")
    args = ap.parse_args()

    print("=" * 60)
    print("  GENERACION DE DATOS - TFM Hidrogeno Verde")
    print(f"  modo: {'OFFLINE' if args.offline else 'ONLINE (Nominatim/OSRM/PVGIS)'}"
          f"  |  forzar: {args.forzar}")
    print("=" * 60)

    coords = paso_coordenadas(args.offline, args.forzar)
    paso_trazabilidad(args.offline, args.forzar)
    paso_instancias(args.offline, args.forzar)
    paso_mapa(coords, args.mapa_fondo, args.extent, args.forzar)
    paso_perfil(args.forzar)

    print("=" * 60)
    print("  LISTO. Salidas en:")
    print(f"    - {CARPETA_TABLAS}  (instancias, cache, trazabilidad)")
    print(f"    - {CARPETA_FIGURAS} ({FIG_MAPA}, {FIG_PERFIL})")
    print("=" * 60)


if __name__ == "__main__":
    main()
