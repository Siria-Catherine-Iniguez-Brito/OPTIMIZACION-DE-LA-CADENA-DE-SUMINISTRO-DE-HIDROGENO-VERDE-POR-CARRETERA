"""
descargar_distancias.py
=======================
Construye la MATRIZ DE DISTANCIAS REALES POR CARRETERA (km) entre un conjunto de
nodos, usando el servicio OSRM (Open Source Routing Machine) sobre la red de
carreteras de OpenStreetMap.

Fuente de la red vial : OpenStreetMap (c) colaboradores de OpenStreetMap (ODbL).
Motor de enrutamiento  : OSRM, API publica http://router.project-osrm.org

Uso (en un equipo CON internet):
    from catalogo_nodos import clientes, plantas
    nodos = plantas(4) + clientes(8)     # [(id, nombre, ..., lat, lon), ...]
    D = construir_matriz(nodos, fuente="osrm")   # dict D[i][j] en km

Si no hay conexion (o falla OSRM) se usa el fallback haversine:
    D = construir_matriz(nodos, fuente="haversine")
que NO son distancias por carretera y solo debe emplearse para pruebas rapidas.

El resultado D[i][j] encaja directamente en el bloque "matriz_distancias" del JSON
de instancia que lee modelo.py.
"""

from __future__ import annotations

import math
import time
from typing import Dict, List, Tuple

# Cada nodo es una tupla cuyo [0] es el id, [-2] la latitud y [-1] la longitud.
Nodo = Tuple

OSRM_BASE = "http://router.project-osrm.org"


def matriz_haversine(nodos: List[Nodo]) -> Dict[str, Dict[str, float]]:
    """Distancia haversine (km) en linea recta. Fallback SOLO para pruebas."""
    R = 6371.0088

    def hav(a, b):
        la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
        h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
        return 2 * R * math.asin(math.sqrt(h))

    D = {}
    for ni in nodos:
        idi, lati, loni = ni[0], ni[-2], ni[-1]
        D[idi] = {}
        for nj in nodos:
            idj, latj, lonj = nj[0], nj[-2], nj[-1]
            D[idi][idj] = 0.0 if idi == idj else round(hav((lati, loni), (latj, lonj)), 3)
    return D


def matriz_osrm(nodos: List[Nodo], usar_table: bool = True,
                pausa: float = 1.0) -> Dict[str, Dict[str, float]]:
    """Matriz de distancias REALES por carretera (km) via OSRM.

    Requiere 'requests' e internet.
      - usar_table=True : una sola llamada al servicio /table para toda la matriz.
      - usar_table=False: llamadas par a par al servicio /route (mas lento, mas
        robusto frente a limites de tamano del /table).
    OSRM espera las coordenadas como 'lon,lat'.
    """
    import requests

    ids = [n[0] for n in nodos]
    coords = ";".join(f"{n[-1]},{n[-2]}" for n in nodos)  # lon,lat

    if usar_table:
        url = f"{OSRM_BASE}/table/v1/driving/{coords}?annotations=distance"
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        data = r.json()
        if "distances" not in data:
            raise RuntimeError("OSRM /table no devolvio 'distances'. Reintenta o usa /route.")
        dist_m = data["distances"]
        D = {}
        for a, idi in enumerate(ids):
            D[idi] = {}
            for b, idj in enumerate(ids):
                metros = dist_m[a][b]
                D[idi][idj] = 0.0 if idi == idj else round((metros or 0.0) / 1000.0, 3)
        return D

    # Alternativa par a par con /route
    D = {i: {} for i in ids}
    for ni in nodos:
        for nj in nodos:
            if ni[0] == nj[0]:
                D[ni[0]][nj[0]] = 0.0
                continue
            url = (f"{OSRM_BASE}/route/v1/driving/"
                   f"{ni[-1]},{ni[-2]};{nj[-1]},{nj[-2]}?overview=false")
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            data = r.json()
            D[ni[0]][nj[0]] = round(data["routes"][0]["distance"] / 1000.0, 3)
            time.sleep(pausa)  # cortesia con la API publica
    return D


def construir_matriz(nodos: List[Nodo], fuente: str = "osrm") -> Dict[str, Dict[str, float]]:
    """Punto de entrada: fuente = 'osrm' (real) | 'haversine' (fallback pruebas).
    Si OSRM falla, cae automaticamente al fallback haversine e informa por consola."""
    if fuente == "osrm":
        try:
            return matriz_osrm(nodos)
        except Exception as e:
            print(f"[aviso] OSRM no disponible ({e}). Se usa fallback haversine.")
            return matriz_haversine(nodos)
    return matriz_haversine(nodos)


