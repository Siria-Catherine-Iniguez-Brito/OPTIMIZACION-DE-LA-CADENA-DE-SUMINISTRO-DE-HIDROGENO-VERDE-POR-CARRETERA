"""
generar_instancia.py
====================
Ensambla una INSTANCIA COMPLETA del problema en el formato JSON que lee modelo.py.

Las COORDENADAS  se obtienen por GEOCODIFICACION con
Nominatim/OpenStreetMap (descargar_coordenadas.py), de forma trazable y cacheada,
igual que las distancias se obtienen con OSRM y el perfil renovable con PVGIS.

Dos vias de generacion:

  1) DATOS REALISTAS  ->  generar(tam, ...)
     Combina los nodos reales del catalogo (catalogo_nodos.py), sus coordenadas
     geocodificadas (Nominatim), las distancias reales por carretera (OSRM), el
     perfil renovable horario (PVGIS) y los parametros tecnico-economicos de
     literatura. Es la via que se usa para RESOLVER el problema del TFM.

  2) DATOS DE PRUEBA  ->  generar_instancia_prueba(n_plantas, n_clientes, ...)
     Genera un dataset PEQUENO sintetico con la MISMA estructura, con coordenadas
     aleatorias y distancias haversine (offline), para validar el algoritmo.

Uso por linea de comandos:
    python generar_instancia.py --tam small  --dist osrm --ren pvgis
    python generar_instancia.py --tam small  --dist osrm --ren pvgis --offline_coords
    python generar_instancia.py --prueba --n_plantas 3 --n_clientes 5 --salida instancia_prueba.json
"""

from __future__ import annotations

import json
import math
import os
import random
from typing import Dict, List, Optional

from catalogo_nodos import clientes, plantas, consultas_nodos
from descargar_distancias import construir_matriz
from descargar_pvgis import construir_perfil
from descargar_coordenadas import geocodificar_nodos

# ----------------------------------------------------------------------------
# PARAMETROS TECNICO-ECONOMICOS 
# ----------------------------------------------------------------------------
DEMANDA_POR_TIPO = {
    "refineria":    2800.0,
    "quimica":      1200.0,
    "fertilizante": 1800.0,
    "siderurgia":   2200.0,
}
CAP_POR_ZONA = {"solar_alto": 1300.0, "solar_medio": 1100.0, "eolico": 1200.0, "mixto": 1250.0}
FIJO_POR_ZONA = {"solar_alto": 5200.0, "solar_medio": 6000.0, "eolico": 5800.0, "mixto": 5500.0}
OPEX_POR_ZONA = {"solar_alto": 2.6, "solar_medio": 3.1, "eolico": 2.9, "mixto": 2.8}

MODOS = {
    "comprimido": {"CapV": 1100.0, "Efi": 0.94, "coste_por_km": 1.05},
    "liquido":    {"CapV": 3500.0, "Efi": 0.82, "coste_por_km": 1.85},
    "amoniaco":   {"CapV": 8000.0, "Efi": 0.72, "coste_por_km": 1.55},
}

TAMANOS = {
    "small":  {"n_plantas": 4,  "n_clientes": 8,  "n_camiones": 16},
    "medium": {"n_plantas": 8,  "n_clientes": 18, "n_camiones": 34},
    "large":  {"n_plantas": 12, "n_clientes": 30, "n_camiones": 55},
}

# Carpeta de salida para las instancias y ficheros derivados (dentro de DATOS/).
CARPETA_TABLAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tablas")

# Coordenadas de respaldo (por si Nominatim no responde y no hay cache).
FALLBACK_COORDS = {
    "ref_corunya": [43.32, -8.38], "ref_bilbao": [43.33, -3.10], "ref_tarrag": [41.11, 1.19],
    "ref_castell": [39.97, -0.03], "ref_cartag": [37.60, -0.98], "ref_huelva": [37.19, -6.95],
    "ref_algecir": [36.23, -5.38], "ref_puertoll": [38.69, -4.11], "qui_tarrag": [41.12, 1.21],
    "qui_huelva": [37.24, -6.92], "qui_puertoll": [38.68, -4.09], "fer_palos": [37.22, -6.89],
    "fer_sagunto": [39.68, -0.24], "sid_gijon": [43.53, -5.70], "sid_sagunto": [39.64, -0.23],
    "sid_bilbao": [43.31, -3.01], "qui_cartag": [37.58, -0.97], "qui_tarrag2": [41.07, 1.17],
    "ind_valencia": [39.45, -0.33], "ind_barna": [41.33, 2.14], "ind_zaragoza": [41.65, -0.93],
    "ind_sevilla": [37.36, -6.00], "ind_madrid": [40.33, -3.68], "ind_valladol": [41.63, -4.75],
    "ind_gijon": [43.55, -5.92], "ind_cadiz": [36.53, -6.20], "ind_almeria": [36.84, -2.46],
    "ind_murcia": [37.98, -1.13], "ind_alicante": [38.35, -0.48], "ind_leon": [42.60, -5.57],
    "pl_andalu": [37.40, -5.98], "pl_extrem": [38.88, -6.97], "pl_castlm": [38.99, -3.93],
    "pl_aragon": [41.50, -1.00], "pl_murcia": [37.98, -1.50], "pl_cataluna": [41.15, 0.90],
    "pl_valencia": [39.40, -0.70], "pl_castleon": [42.01, -4.53], "pl_navarra": [42.50, -1.65],
    "pl_galicia": [43.10, -8.00], "pl_asturias": [43.40, -5.85], "pl_cadiz": [36.40, -5.90],
    "pl_huelva": [37.30, -6.90], "pl_almeria": [37.00, -2.40], "pl_teruel": [40.70, -1.00],
}


# ============================================================================
# 1) GENERACION DE DATOS REALISTAS
# ============================================================================
def generar(tam: str, fuente_dist: str = "osrm", fuente_ren: str = "pvgis",
            semilla: int = 0, offline_coords: bool = False) -> dict:
    """Ensambla la instancia realista 'tam' como diccionario en el formato JSON.

    Las coordenadas se geocodifican con Nominatim (o cache/fallback si
    offline_coords=True o la API falla).
    """
    cfg = TAMANOS[tam]
    plist = plantas(cfg["n_plantas"])
    clist = clientes(cfg["n_clientes"])
    todos = plist + clist

    # (a) Coordenadas por geocodificacion (Nominatim), con cache y fallback.
    consultas = consultas_nodos(todos)              # [(id, texto), ...]
    coord = geocodificar_nodos(consultas, fallback=FALLBACK_COORDS,
                               usar_api=not offline_coords)

    # (b) Nodos para OSRM: (id, lat, lon) -> tuplas con [-2]=lat, [-1]=lon.
    nodos_dist = [(nid, coord[nid][0], coord[nid][1]) for nid, _ in consultas]
    D = construir_matriz(nodos_dist, fuente=fuente_dist)

    P = [p[0] for p in plist]
    J = [c[0] for c in clist]
    K = [f"k{i+1}" for i in range(cfg["n_camiones"])]
    M = list(MODOS.keys())

    # (c) Plantas: parametros por zona + perfil renovable (PVGIS/sintetico).
    plantas_json = {}
    for (pid, nombre, zona, prov, _consulta) in plist:
        cap = CAP_POR_ZONA[zona]
        lat, lon = coord[pid]
        ren = construir_perfil(lat, lon, zona, cap_kg_h=cap, fuente=fuente_ren, semilla=semilla)
        plantas_json[pid] = {
            "nombre": nombre, "provincia": prov, "zona_recurso": zona,
            "Fijo": FIJO_POR_ZONA[zona], "CosteO": OPEX_POR_ZONA[zona],
            "Cap": cap, "Ren": ren,
        }

    # (d) Clientes: demanda por tipo.
    clientes_json = {}
    for (cid, nombre, tipo, prov, _consulta) in clist:
        clientes_json[cid] = {"nombre": nombre, "provincia": prov, "tipo": tipo,
                              "Dem": DEMANDA_POR_TIPO[tipo]}

    return _ensamblar(
        nombre=f"instancia_{tam}",
        descripcion=f"{cfg['n_plantas']} plantas, {cfg['n_clientes']} clientes, {len(M)} modos",
        P=P, J=J, K=K, M=M,
        plantas_json=plantas_json, clientes_json=clientes_json,
        coord={nid: coord[nid] for nid, _ in consultas}, D=D,
        fuente_distancias="matriz_real" if fuente_dist == "osrm" else "euclidea",
        fuente_ren=fuente_ren,
        fuente_coords="nominatim" if not offline_coords else "cache/fallback",
    )


# ============================================================================
# 2) GENERACION DE UN DATASET DE PRUEBA PEQUENO
# ============================================================================
def generar_instancia_prueba(n_plantas: int = 3, n_clientes: int = 5,
                             n_camiones: Optional[int] = None,
                             semilla: int = 0,
                             area_lat=(37.0, 43.0), area_lon=(-7.0, 1.0)) -> dict:
    """Genera un dataset PEQUENO sintetico con la MISMA estructura que el realista.
    Coordenadas aleatorias, distancias haversine y perfil sintetico (offline)."""
    rng = random.Random(semilla)
    zonas = list(CAP_POR_ZONA.keys())
    tipos = list(DEMANDA_POR_TIPO.keys())

    def _coord():
        return [round(rng.uniform(*area_lat), 4), round(rng.uniform(*area_lon), 4)]

    P, plantas_json, coord = [], {}, {}
    for k in range(n_plantas):
        pid = f"planta_{k+1}"
        zona = zonas[k % len(zonas)]
        lat, lon = _coord()
        cap = CAP_POR_ZONA[zona]
        ren = construir_perfil(lat, lon, zona, cap_kg_h=cap, fuente="sintetico", semilla=semilla + k)
        plantas_json[pid] = {
            "nombre": f"Planta de prueba {k+1}", "provincia": "-", "zona_recurso": zona,
            "Fijo": FIJO_POR_ZONA[zona], "CosteO": OPEX_POR_ZONA[zona], "Cap": cap, "Ren": ren,
        }
        coord[pid] = [lat, lon]
        P.append(pid)

    J, clientes_json = [], {}
    for k in range(n_clientes):
        cid = f"cliente_{k+1}"
        tipo = tipos[k % len(tipos)]
        lat, lon = _coord()
        clientes_json[cid] = {"nombre": f"Cliente de prueba {k+1}", "provincia": "-",
                              "tipo": tipo, "Dem": DEMANDA_POR_TIPO[tipo]}
        coord[cid] = [lat, lon]
        J.append(cid)

    if n_camiones is None:
        cisterna_min = min(m["CapV"] for m in MODOS.values())
        dem_total = sum(clientes_json[j]["Dem"] for j in J)
        n_camiones = max(n_clientes, math.ceil(dem_total / cisterna_min) + n_clientes)
    K = [f"k{i+1}" for i in range(n_camiones)]
    M = list(MODOS.keys())

    nodos = [(pid, coord[pid][0], coord[pid][1]) for pid in P]
    nodos += [(cid, coord[cid][0], coord[cid][1]) for cid in J]
    D = construir_matriz(nodos, fuente="haversine")

    return _ensamblar(
        nombre="instancia_prueba",
        descripcion=f"PRUEBA: {n_plantas} plantas, {n_clientes} clientes, {len(M)} modos",
        P=P, J=J, K=K, M=M,
        plantas_json=plantas_json, clientes_json=clientes_json,
        coord=coord, D=D,
        fuente_distancias="euclidea", fuente_ren="sintetico", fuente_coords="aleatoria",
    )


# ============================================================================
# Ensamblado comun del diccionario de instancia
# ============================================================================
def _ensamblar(nombre, descripcion, P, J, K, M, plantas_json, clientes_json,
               coord, D, fuente_distancias, fuente_ren, fuente_coords) -> dict:
    return {
        "meta": {
            "nombre": nombre,
            "descripcion": descripcion,
            "T": 24,
            "fuente_distancias": fuente_distancias,
            "fuentes": {
                "coordenadas": "Nominatim / OpenStreetMap" if fuente_coords == "nominatim"
                               else ("aleatoria (prueba)" if fuente_coords == "aleatoria"
                                     else "cache/fallback local"),
                "distancias": "OSRM sobre OpenStreetMap" if fuente_distancias == "matriz_real" else "haversine (prueba)",
                "renovable": "PVGIS (JRC, Comision Europea)" if fuente_ren == "pvgis" else "sintetico (prueba)",
                "demanda_y_costes": "Hoja de Ruta del Hidrogeno (MITECO) y literatura sectorial",
            },
        },
        "conjuntos": {"P": P, "J": J, "K": K, "M": M},
        "plantas": plantas_json,
        "clientes": clientes_json,
        "modos": MODOS,
        "coordenadas": coord,
        "matriz_distancias": {
            "_comentario": "km reales por carretera (OSRM/OSM) o haversine si es prueba.",
            "unidad": "km", "valores": D,
        },
    }


def guardar(inst: dict, ruta: str) -> None:
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(inst, fh, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Generador de instancias del problema.")
    ap.add_argument("--prueba", action="store_true",
                    help="genera un dataset de PRUEBA pequeno (en vez de una instancia realista)")
    ap.add_argument("--tam", choices=list(TAMANOS), default="small",
                    help="tamano de la instancia realista")
    ap.add_argument("--dist", choices=["osrm", "haversine"], default="osrm",
                    help="fuente de distancias (osrm=real; haversine=offline)")
    ap.add_argument("--ren", choices=["pvgis", "sintetico"], default="pvgis",
                    help="fuente del perfil renovable (pvgis=real; sintetico=offline)")
    ap.add_argument("--offline_coords", action="store_true",
                    help="no llamar a Nominatim; usar cache/fallback para coordenadas")
    ap.add_argument("--n_plantas", type=int, default=3, help="(modo --prueba) numero de plantas")
    ap.add_argument("--n_clientes", type=int, default=5, help="(modo --prueba) numero de clientes")
    ap.add_argument("--semilla", type=int, default=0)
    ap.add_argument("--salida", default=None)
    args = ap.parse_args()

    if args.prueba:
        inst = generar_instancia_prueba(n_plantas=args.n_plantas, n_clientes=args.n_clientes,
                                        semilla=args.semilla)
        salida = args.salida or os.path.join(CARPETA_TABLAS, "instancia_prueba.json")
    else:
        inst = generar(args.tam, fuente_dist=args.dist, fuente_ren=args.ren,
                       semilla=args.semilla, offline_coords=args.offline_coords)
        salida = args.salida or os.path.join(CARPETA_TABLAS, f"instancia_{args.tam}.json")

    guardar(inst, os.path.abspath(salida))
    HTotal = sum(c["Dem"] for c in inst["clientes"].values())
    print(f"Instancia '{inst['meta']['nombre']}' generada -> {os.path.abspath(salida)}")
    print(f"  |P|={len(inst['conjuntos']['P'])} |J|={len(inst['conjuntos']['J'])} "
          f"|K|={len(inst['conjuntos']['K'])} |M|={len(inst['conjuntos']['M'])}")
    print(f"  HTotal = {HTotal:.0f} kg/dia  |  coords={inst['meta']['fuentes']['coordenadas']}  "
          f"|  distancias={inst['meta']['fuente_distancias']}")
