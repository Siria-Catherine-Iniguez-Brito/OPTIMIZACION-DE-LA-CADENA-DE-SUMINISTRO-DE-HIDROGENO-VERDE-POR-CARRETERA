"""
descargar_coordenadas.py
========================
Obtiene las COORDENADAS (lat, lon) de los nodos de la cadena de suministro
mediante GEOCODIFICACION por nombre/lugar, usando el servicio Nominatim de
OpenStreetMap.

Fuente : Nominatim (c) colaboradores de OpenStreetMap (ODbL).
Endpoint: https://nominatim.openstreetmap.org/search
"""

from __future__ import annotations

import json
import os
import time
from typing import Dict, List, Optional, Tuple

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "TFM-H2-supply-chain/1.0 (siinigue@ucm.es)"
PAUSA_S = 1.1          # >= 1 s entre peticiones (politica de uso de Nominatim)
# La cache se guarda en la carpeta 'Tablas/' junto a las instancias.
CACHE_POR_DEFECTO = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "Tablas", "coords_cache.json")


# ----------------------------------------------------------------------------
# Cache en disco (hace las instancias reproducibles y evita repetir consultas)
# ----------------------------------------------------------------------------
def _cargar_cache(ruta: str) -> Dict[str, List[float]]:
    if os.path.exists(ruta):
        with open(ruta, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def _guardar_cache(cache: Dict[str, List[float]], ruta: str) -> None:
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, indent=2, ensure_ascii=False)


# ----------------------------------------------------------------------------
# Consulta unitaria a Nominatim
# ----------------------------------------------------------------------------
def geocodificar_lugar(texto: str) -> Tuple[float, float]:
    """Devuelve (lat, lon) del primer resultado de Nominatim para 'texto'.
    Requiere 'requests' e internet. Lanza excepcion si no hay resultado."""
    import requests

    params = {"q": texto, "format": "json", "limit": 1, "countrycodes": "es"}
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data:
        raise RuntimeError(f"Nominatim no devolvio resultado para: {texto!r}")
    return round(float(data[0]["lat"]), 4), round(float(data[0]["lon"]), 4)


# ----------------------------------------------------------------------------
# Punto de entrada: geocodificar una lista de nodos con cache y fallback
# ----------------------------------------------------------------------------
def geocodificar_nodos(nodos: List[Tuple[str, str]],
                       fallback: Optional[Dict[str, List[float]]] = None,
                       cache_path: str = CACHE_POR_DEFECTO,
                       usar_api: bool = True) -> Dict[str, List[float]]:
    """Geocodifica una lista de nodos.

    nodos    : lista de tuplas (id, texto_a_geocodificar).
    fallback : dict id -> [lat, lon] de respaldo si la API y la cache fallan.
    cache_path: fichero JSON donde se guardan/leen las coordenadas ya obtenidas.
    usar_api : True = consulta Nominatim; False = solo cache + fallback (offline).
    """
    fallback = fallback or {}
    cache = _cargar_cache(cache_path)
    coords: Dict[str, List[float]] = {}
    nuevos = False

    for nid, texto in nodos:
        # 1) Si ya esta en cache, se reutiliza (no se vuelve a llamar a la API).
        if nid in cache:
            coords[nid] = cache[nid]
            continue
        # 2) Si no, se intenta la API (salvo modo offline).
        if usar_api:
            try:
                lat, lon = geocodificar_lugar(texto)
                coords[nid] = [lat, lon]
                cache[nid] = [lat, lon]
                nuevos = True
                time.sleep(PAUSA_S)      
                continue
            except Exception as e:
                print(f"[aviso] Nominatim fallo para {nid} ({texto!r}): {e}")
        # 3) Ultimo recurso: coordenadas de respaldo escritas a mano.
        if nid in fallback:
            print(f"[aviso] Usando coordenada de respaldo para {nid}.")
            coords[nid] = fallback[nid]
        else:
            raise RuntimeError(
                f"No se pudo geocodificar {nid} y no hay fallback definido.")

    if nuevos:
        _guardar_cache(cache, cache_path)
    return coords


if __name__ == "__main__":
    demo = [
        ("ref_huelva", "Refineria La Rabida, Palos de la Frontera, Huelva, Espana"),
        ("pl_extrem",  "Badajoz, Espana"),
    ]
    print(geocodificar_nodos(demo))