"""
generar_trazabilidad.py
=======================
Genera el fichero de trazabilidad de coordenadas 'trazabilidad_coordenadas.csv'.

Para cada nodo del catalogo (catalogo_nodos.py) registra:
  clase, id, nombre, provincia, consulta_nominatim, lat, lon, fuente, fecha.

Como funciona
-------------
1. Con INTERNET (recomendado): geocodifica cada 'consulta' con Nominatim
   (descargar_coordenadas.py), obteniendo coordenadas REALES y trazables, y las
   deja cacheadas en coords_cache.json. El CSV refleja esas coordenadas.
2. SIN internet: si Nominatim no responde, usa lo que haya en coords_cache.json
   (si ya se descargó antes) o, en su defecto, las coordenadas de respaldo
   'FALLBACK' de este fichero, e indica la fuente correspondiente en el CSV.

Uso
---
    python generar_trazabilidad.py                # geocodifica todo el catalogo
    python generar_trazabilidad.py --offline      # no llama a la API (cache/fallback)
    python generar_trazabilidad.py --salida mi.csv
"""

from __future__ import annotations

import argparse
import csv
import datetime
import os

from catalogo_nodos import CLIENTES, PLANTAS, consultas_nodos
from descargar_coordenadas import geocodificar_nodos

# Carpeta de salida (dentro de DATOS/), junto a las instancias y la cache.
CARPETA_TABLAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Tablas")

# Coordenadas de respaldo por si no hay internet NI cache.
FALLBACK = {
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


def main():
    ap = argparse.ArgumentParser(description="Genera la tabla de trazabilidad de coordenadas.")
    ap.add_argument("--offline", action="store_true",
                    help="no llama a Nominatim; usa cache/fallback")
    ap.add_argument("--salida", default=None,
                    help="ruta del CSV (por defecto: tablas/trazabilidad_coordenadas.csv)")
    args = ap.parse_args()

    salida = args.salida or os.path.join(CARPETA_TABLAS, "trazabilidad_coordenadas.csv")

    todos = PLANTAS + CLIENTES
    consultas = consultas_nodos(todos)          # [(id, consulta), ...]

    # Geocodifica (o recupera de cache/fallback). Devuelve coords[id] = [lat, lon].
    coords = geocodificar_nodos(consultas, fallback=FALLBACK,
                                usar_api=not args.offline)

    fecha = datetime.date.today().isoformat()
    fuente = "Nominatim / OpenStreetMap" if not args.offline else "cache/fallback local"

    filas = []
    for t in PLANTAS:
        nid, nombre, zona, prov, consulta = t
        la, lo = coords.get(nid, ["", ""])
        filas.append(["planta", nid, nombre, prov, consulta, la, lo, fuente, fecha])
    for t in CLIENTES:
        nid, nombre, tipo, prov, consulta = t
        la, lo = coords.get(nid, ["", ""])
        filas.append(["cliente", nid, nombre, prov, consulta, la, lo, fuente, fecha])

    os.makedirs(CARPETA_TABLAS, exist_ok=True)
    with open(salida, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["clase", "id", "nombre", "provincia", "consulta_nominatim",
                    "lat", "lon", "fuente", "fecha_consulta"])
        w.writerows(filas)

    print(f"Trazabilidad generada -> {os.path.abspath(salida)}")
    print(f"  {len(PLANTAS)} plantas + {len(CLIENTES)} clientes = {len(filas)} nodos")


if __name__ == "__main__":
    main()
