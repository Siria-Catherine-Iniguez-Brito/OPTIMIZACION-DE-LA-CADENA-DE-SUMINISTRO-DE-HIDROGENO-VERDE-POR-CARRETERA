"""
generar_instancia.py
====================
Ensambla una INSTANCIA COMPLETA del problema en el formato JSON que lee modelo.py.

Dos vias de generacion:

  1) DATOS REALISTAS  ->  generar(tam, ...)
     Combina los nodos reales del catalogo (catalogo_nodos.py), las distancias
     reales por carretera (descargar_distancias.py, OSRM/OpenStreetMap), el perfil
     renovable horario (descargar_pvgis.py, PVGIS) y los parametros
     tecnico-economicos de literatura sectorial. Produce las instancias de tamano
     creciente (small / medium / large), todas con los tres modos de transporte.
     Es la via que se usa para RESOLVER el problema del TFM.

  2) DATOS DE PRUEBA  ->  generar_instancia_prueba(n_plantas, n_clientes, ...)
     Genera un dataset PEQUENO sintetico con la MISMA estructura que el realista,
     util para validar el algoritmo con casos manejables. No depende de nombres
     fijos: sirve para cualquier tamano y produce plantas/clientes genericos.

Uso por linea de comandos:
    # instancia realista
    python generar_instancia.py --tam small  --dist osrm --ren pvgis
    # instancia de prueba pequena
    python generar_instancia.py --prueba --n_plantas 3 --n_clientes 5 --salida instancia_prueba.json
"""

from __future__ import annotations

import json
import math
import os
import random
from typing import Dict, List, Optional

from catalogo_nodos import clientes, plantas
from descargar_distancias import construir_matriz
from descargar_pvgis import construir_perfil

# ----------------------------------------------------------------------------
# PARAMETROS TECNICO-ECONOMICOS (rangos de literatura; ver datos_fuente/FUENTES.md)
# ----------------------------------------------------------------------------
# Demanda diaria (kg H2/dia) por tipo de consumidor industrial.
DEMANDA_POR_TIPO = {
    "refineria":    2800.0,   # grandes consumidores (~70% del H2 nacional)
    "quimica":      1200.0,
    "fertilizante": 1800.0,   # sintesis de amoniaco
    "siderurgia":   2200.0,   # H2-DRI (demanda emergente)
}

# Capacidad del electrolizador (kg/h) por zona de recurso. Calibrada para dar
# holgura de produccion incluso con el modo menos eficiente (amoniaco, Efi=0.72).
CAP_POR_ZONA = {"solar_alto": 1300.0, "solar_medio": 1100.0, "eolico": 1200.0, "mixto": 1250.0}
# CAPEX anualizado (EUR/dia) y OPEX (EUR/kg) por zona (mejor recurso -> menor coste).
FIJO_POR_ZONA = {"solar_alto": 5200.0, "solar_medio": 6000.0, "eolico": 5800.0, "mixto": 5500.0}
OPEX_POR_ZONA = {"solar_alto": 2.6, "solar_medio": 3.1, "eolico": 2.9, "mixto": 2.8}

# Los tres MODOS de transporte del hidrogeno:
#   CapV        : capacidad de carga de la cisterna (kg) -> crece con la densidad.
#   Efi         : eficiencia de acondicionamiento (fraccion entregada tras el proceso).
#   coste_por_km: coste por km del modo (EUR/km).
MODOS = {
    "comprimido": {"CapV": 1100.0, "Efi": 0.94, "coste_por_km": 1.05},  # GH2 350-500 bar
    "liquido":    {"CapV": 3500.0, "Efi": 0.82, "coste_por_km": 1.85},  # LH2 criogenico
    "amoniaco":   {"CapV": 8000.0, "Efi": 0.72, "coste_por_km": 1.55},  # NH3 portador quimico
}

# Dimensiones de las instancias realistas (flota con holgura para el peor caso de modo).
TAMANOS = {
    "small":  {"n_plantas": 4,  "n_clientes": 8,  "n_camiones": 16},
    "medium": {"n_plantas": 8,  "n_clientes": 18, "n_camiones": 34},
    "large":  {"n_plantas": 12, "n_clientes": 30, "n_camiones": 55},
}


# ============================================================================
# 1) GENERACION DE DATOS REALISTAS
# ============================================================================
def generar(tam: str, fuente_dist: str = "osrm", fuente_ren: str = "pvgis",
            semilla: int = 0) -> dict:
    """Ensambla la instancia realista 'tam' como diccionario en el formato JSON."""
    cfg = TAMANOS[tam]
    plist = plantas(cfg["n_plantas"])
    clist = clientes(cfg["n_clientes"])
    nodos = plist + clist

    D = construir_matriz(nodos, fuente=fuente_dist)

    P = [p[0] for p in plist]
    J = [c[0] for c in clist]
    K = [f"k{i+1}" for i in range(cfg["n_camiones"])]
    M = list(MODOS.keys())

    plantas_json, coord = {}, {}
    for (pid, nombre, zona, prov, lat, lon) in plist:
        cap = CAP_POR_ZONA[zona]
        ren = construir_perfil(lat, lon, zona, cap_kg_h=cap, fuente=fuente_ren, semilla=semilla)
        plantas_json[pid] = {
            "nombre": nombre, "provincia": prov, "zona_recurso": zona,
            "Fijo": FIJO_POR_ZONA[zona], "CosteO": OPEX_POR_ZONA[zona],
            "Cap": cap, "Ren": ren,
        }
        coord[pid] = [lat, lon]

    clientes_json = {}
    for (cid, nombre, tipo, prov, lat, lon) in clist:
        clientes_json[cid] = {"nombre": nombre, "provincia": prov, "tipo": tipo,
                              "Dem": DEMANDA_POR_TIPO[tipo]}
        coord[cid] = [lat, lon]

    return _ensamblar(
        nombre=f"instancia_{tam}",
        descripcion=f"{cfg['n_plantas']} plantas, {cfg['n_clientes']} clientes, {len(M)} modos",
        P=P, J=J, K=K, M=M,
        plantas_json=plantas_json, clientes_json=clientes_json,
        coord=coord, D=D,
        fuente_distancias="matriz_real" if fuente_dist == "osrm" else "euclidea",
        fuente_ren=fuente_ren,
    )


# ============================================================================
# 2) GENERACION DE UN DATASET DE PRUEBA PEQUENO (parametrizable, sin nombres fijos)
# ============================================================================
def generar_instancia_prueba(n_plantas: int = 3, n_clientes: int = 5,
                             n_camiones: Optional[int] = None,
                             semilla: int = 0,
                             area_lat=(37.0, 43.0), area_lon=(-7.0, 1.0)) -> dict:
    """Genera un dataset PEQUENO sintetico con la MISMA estructura que el realista.

    Crea 'n_plantas' plantas y 'n_clientes' clientes genericos con coordenadas
    aleatorias dentro de un area (por defecto, la Peninsula), asignando a cada nodo
    un tipo/zona del mismo catalogo de parametros que las instancias reales. Las
    distancias se calculan con haversine (no requiere internet) y el perfil
    renovable con el generador sintetico. Sirve para validar el algoritmo con casos
    manejables sin depender de ninguna instancia concreta.

    El numero de camiones, si no se indica, se dimensiona con holgura para el peor
    modo (amoniaco), de forma que la instancia sea factible.
    """
    rng = random.Random(semilla)
    zonas = list(CAP_POR_ZONA.keys())
    tipos = list(DEMANDA_POR_TIPO.keys())

    def _coord():
        return [round(rng.uniform(*area_lat), 4), round(rng.uniform(*area_lon), 4)]

    # Plantas genericas
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

    # Clientes genericos
    J, clientes_json = [], {}
    for k in range(n_clientes):
        cid = f"cliente_{k+1}"
        tipo = tipos[k % len(tipos)]
        lat, lon = _coord()
        clientes_json[cid] = {"nombre": f"Cliente de prueba {k+1}", "provincia": "-",
                              "tipo": tipo, "Dem": DEMANDA_POR_TIPO[tipo]}
        coord[cid] = [lat, lon]
        J.append(cid)

    # Flota con holgura: suficientes camiones para el peor modo (amoniaco).
    if n_camiones is None:
        cisterna_min = min(m["CapV"] for m in MODOS.values())
        dem_total = sum(clientes_json[j]["Dem"] for j in J)
        n_camiones = max(n_clientes, math.ceil(dem_total / cisterna_min) + n_clientes)
    K = [f"k{i+1}" for i in range(n_camiones)]
    M = list(MODOS.keys())

    # Distancias haversine (offline)
    nodos = [(pid, "", plantas_json[pid]["zona_recurso"], "-",
              coord[pid][0], coord[pid][1]) for pid in P]
    nodos += [(cid, "", clientes_json[cid]["tipo"], "-",
               coord[cid][0], coord[cid][1]) for cid in J]
    D = construir_matriz(nodos, fuente="haversine")

    return _ensamblar(
        nombre="instancia_prueba",
        descripcion=f"PRUEBA: {n_plantas} plantas, {n_clientes} clientes, {len(M)} modos",
        P=P, J=J, K=K, M=M,
        plantas_json=plantas_json, clientes_json=clientes_json,
        coord=coord, D=D,
        fuente_distancias="euclidea", fuente_ren="sintetico",
    )


# ============================================================================
# Ensamblado comun del diccionario de instancia
# ============================================================================
def _ensamblar(nombre, descripcion, P, J, K, M, plantas_json, clientes_json,
               coord, D, fuente_distancias, fuente_ren) -> dict:
    return {
        "meta": {
            "nombre": nombre,
            "descripcion": descripcion,
            "T": 24,
            "fuente_distancias": fuente_distancias,
            "fuentes": {
                "coordenadas": "IGN / ubicaciones publicas de instalaciones",
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
    ap.add_argument("--n_plantas", type=int, default=3, help="(modo --prueba) numero de plantas")
    ap.add_argument("--n_clientes", type=int, default=5, help="(modo --prueba) numero de clientes")
    ap.add_argument("--semilla", type=int, default=0)
    ap.add_argument("--salida", default=None)
    args = ap.parse_args()

    if args.prueba:
        inst = generar_instancia_prueba(n_plantas=args.n_plantas, n_clientes=args.n_clientes,
                                        semilla=args.semilla)
        salida = args.salida or os.path.join(os.path.dirname(__file__), "instancia_prueba.json")
    else:
        inst = generar(args.tam, fuente_dist=args.dist, fuente_ren=args.ren, semilla=args.semilla)
        salida = args.salida or os.path.join(os.path.dirname(__file__), f"instancia_{args.tam}.json")

    guardar(inst, os.path.abspath(salida))
    HTotal = sum(c["Dem"] for c in inst["clientes"].values())
    print(f"Instancia '{inst['meta']['nombre']}' generada -> {os.path.abspath(salida)}")
    print(f"  |P|={len(inst['conjuntos']['P'])} |J|={len(inst['conjuntos']['J'])} "
          f"|K|={len(inst['conjuntos']['K'])} |M|={len(inst['conjuntos']['M'])}")
    print(f"  HTotal = {HTotal:.0f} kg/dia  |  fuente_distancias={inst['meta']['fuente_distancias']}")
