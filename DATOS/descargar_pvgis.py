"""
descargar_pvgis.py
==================
Construye el PERFIL RENOVABLE HORARIO Ren_{i,t} (kg de H2 producibles por hora)
de cada planta a partir de datos de radiacion solar de PVGIS.

Fuente: PVGIS (Photovoltaic Geographical Information System), Joint Research
Centre (JRC), Comision Europea. Radiacion horaria de satelite (base PVGIS-SARAH).
API publica: https://re.jrc.ec.europa.eu/api/

Conversion radiacion -> hidrogeno
---------------------------------
1. PVGIS devuelve la potencia FV horaria P(t) [W] de un sistema de potencia pico
   'pico_kwp' con perdidas 'perdidas_pct'.
2. La energia horaria es E(t) = P(t)/1000 [kWh].
3. El hidrogeno producible es H(t) = E(t) / CONSUMO_KWH_POR_KG [kg], con un consumo
   electrico especifico del electrolizador ~ 52 kWh/kg (valor tipico PEM).
El perfil se promedia a un dia tipo de 24 horas y se escala a la capacidad de la
planta.

Si no hay conexion (o falla PVGIS) se usa un FALLBACK SINTETICO que reproduce una
curva diaria realista por zona de recurso (solar / eolico / mixto).
"""

from __future__ import annotations

import math
from typing import List

PVGIS_API = "https://re.jrc.ec.europa.eu/api/v5_2/seriescalc"
CONSUMO_KWH_POR_KG = 52.0   # consumo electrico especifico del electrolizador (kWh/kg H2)


def perfil_pvgis(lat: float, lon: float, pico_kwp: float = 1000.0,
                 perdidas_pct: float = 14.0, anio: int = 2020) -> List[float]:
    """Perfil de 24 valores (kg H2/h) promediando un dia tipo del anio en PVGIS.
    Requiere 'requests' e internet."""
    import requests
    params = {
        "lat": lat, "lon": lon, "startyear": anio, "endyear": anio,
        "pvcalculation": 1, "peakpower": pico_kwp, "loss": perdidas_pct,
        "outputformat": "json", "mountingplace": "free",
    }
    r = requests.get(PVGIS_API, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()
    horas = data["outputs"]["hourly"]          # registros con 'time' (YYYYMMDD:HHMM) y 'P' (W)
    acum = [0.0] * 24
    cont = [0] * 24
    for reg in horas:
        hh = int(reg["time"][9:11])
        acum[hh] += reg["P"] / 1000.0          # kWh de esa hora
        cont[hh] += 1
    kg = []
    for h in range(24):
        e_kwh = (acum[h] / cont[h]) if cont[h] else 0.0
        kg.append(round(e_kwh / CONSUMO_KWH_POR_KG, 4))
    return kg


def perfil_sintetico(zona: str, cap_kg_h: float, semilla: int = 0) -> List[float]:
    """Fallback: curva diaria realista de 24 h (kg H2/h) parametrizada por zona.
      - solar : campana centrada en el mediodia solar, cero por la noche.
      - eolico: base mas plana con repunte tarde-noche.
      - mixto : combinacion de ambas.
    El pico se escala a una fraccion de la capacidad cap_kg_h de la planta."""
    import random
    rng = random.Random(semilla)
    perfil = []
    for t in range(24):
        if zona.startswith("solar"):
            base = max(0.0, math.sin(math.pi * (t - 6) / 14)) if 6 <= t <= 20 else 0.0
            factor = 0.95 if zona == "solar_alto" else 0.75
        elif zona == "eolico":
            base = max(0.0, 0.45 + 0.35 * math.sin(math.pi * (t - 2) / 12))
            factor = 0.8
        else:  # mixto
            solar = max(0.0, math.sin(math.pi * (t - 6) / 14)) if 6 <= t <= 20 else 0.0
            eol = max(0.0, 0.4 + 0.3 * math.sin(math.pi * (t - 2) / 12))
            base = 0.6 * solar + 0.4 * eol
            factor = 0.85
        ruido = 1.0 + rng.uniform(-0.06, 0.06)
        perfil.append(round(cap_kg_h * factor * base * ruido, 4))
    return perfil


def construir_perfil(lat: float, lon: float, zona: str, cap_kg_h: float,
                     fuente: str = "pvgis", semilla: int = 0) -> List[float]:
    """Punto de entrada: fuente = 'pvgis' (real) | 'sintetico' (fallback).
    Con PVGIS, el perfil se reescala para que el pico coincida con la capacidad
    instalada de la planta. Si PVGIS falla, cae al fallback sintetico."""
    if fuente == "pvgis":
        try:
            perfil = perfil_pvgis(lat, lon)
            pico = max(perfil) or 1.0
            return [round(v / pico * cap_kg_h, 4) for v in perfil]
        except Exception as e:
            print(f"[aviso] PVGIS no disponible ({e}). Se usa fallback sintetico.")
            return perfil_sintetico(zona, cap_kg_h, semilla)
    return perfil_sintetico(zona, cap_kg_h, semilla)


if __name__ == "__main__":
    for zona in ["solar_alto", "eolico", "mixto"]:
        p = construir_perfil(37.4, -5.98, zona, cap_kg_h=200.0, fuente="pvgis", semilla=1)
        print(f"{zona:>10}: pico={max(p):6.1f} kg/h  total_dia={sum(p):7.1f} kg  "
              f"perfil[9..15]={[round(x) for x in p[9:16]]}")
