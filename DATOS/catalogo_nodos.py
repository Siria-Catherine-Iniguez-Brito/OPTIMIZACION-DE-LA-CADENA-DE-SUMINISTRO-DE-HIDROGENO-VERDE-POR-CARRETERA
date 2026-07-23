"""
catalogo_nodos.py
=================
Catalogo de NODOS REALES de la cadena de suministro de hidrogeno verde en Espana.

CLIENTES (nodos de demanda industrial): grandes consumidores reales de hidrogeno.
  - Refinerias (las 8 refinerias reales de Espana) -> ~70% del consumo nacional de H2.
  - Complejos quimicos / petroquimicos y fertilizantes (amoniaco) -> ~25-30%.
  - Siderurgia (demanda emergente via H2-DRI para descarbonizar el acero).
  Coordenadas (lat, lon) de la instalacion, de fuentes oficiales/publicas
  (IGN, nomenclator y ubicaciones publicas de las plantas).

PLANTAS CANDIDATAS (ubicaciones de produccion): emplazamientos con buen recurso
  renovable, proximos a nudos industriales/logisticos y coherentes con los valles
  de hidrogeno de la Hoja de Ruta del Hidrogeno de Espana (MITECO).

Formato de cada nodo:
  CLIENTES: (id, nombre, tipo, provincia, lat, lon)
  PLANTAS : (id, nombre, zona_recurso, provincia, lat, lon)
Las coordenadas se usan (a) para las llamadas a OSRM y PVGIS y (b) para los mapas.
"""

# --- CLIENTES: consumidores industriales reales ---
CLIENTES = [
    # id            nombre                          tipo            provincia       lat       lon
    ("ref_corunya", "Refineria A Coruna (Repsol)",   "refineria",   "A Coruna",    43.3200,  -8.3800),
    ("ref_bilbao",  "Refineria Petronor (Muskiz)",   "refineria",   "Vizcaya",     43.3300,  -3.1000),
    ("ref_tarrag",  "Refineria Tarragona (Repsol)",  "refineria",   "Tarragona",   41.1100,   1.1900),
    ("ref_castell", "Refineria Castellon (BP)",      "refineria",   "Castellon",   39.9700,  -0.0300),
    ("ref_cartag",  "Refineria Cartagena (Repsol)",  "refineria",   "Murcia",      37.6000,  -0.9800),
    ("ref_huelva",  "Refineria La Rabida (Moeve)",   "refineria",   "Huelva",      37.1900,  -6.9500),
    ("ref_algecir", "Refineria San Roque (Moeve)",   "refineria",   "Cadiz",       36.2300,  -5.3800),
    ("ref_puertoll","Refineria Puertollano (Repsol)","refineria",   "Ciudad Real", 38.6900,  -4.1100),
    # Petroquimica / quimica / fertilizantes
    ("qui_tarrag",  "Petroquimica Tarragona",        "quimica",     "Tarragona",   41.1200,   1.2100),
    ("qui_huelva",  "Polo quimico Huelva",           "quimica",     "Huelva",      37.2400,  -6.9200),
    ("qui_puertoll","Complejo quimico Puertollano",  "quimica",     "Ciudad Real", 38.6800,  -4.0900),
    ("fer_palos",   "Fertilizantes Palos (Huelva)",  "fertilizante","Huelva",      37.2200,  -6.8900),
    ("fer_sagunto", "Fertilizantes Sagunto",         "fertilizante","Valencia",    39.6800,  -0.2400),
    # Siderurgia (H2-DRI, demanda emergente)
    ("sid_gijon",   "Siderurgia Gijon-Verina",       "siderurgia",  "Asturias",    43.5300,  -5.7000),
    ("sid_sagunto", "Siderurgia Sagunto",            "siderurgia",  "Valencia",    39.6400,  -0.2300),
    ("sid_bilbao",  "Siderurgia Sestao (Bizkaia)",   "siderurgia",  "Vizcaya",     43.3100,  -3.0100),
    # Otros consumidores industriales relevantes
    ("qui_cartag",  "Quimica Escombreras Cartagena", "quimica",     "Murcia",      37.5800,  -0.9700),
    ("qui_tarrag2", "Quimica Sur Tarragona",         "quimica",     "Tarragona",   41.0700,   1.1700),
    ("ind_valencia","Industria Valencia",            "quimica",     "Valencia",    39.4500,  -0.3300),
    ("ind_barna",   "Industria Barcelona (Zona F.)", "quimica",     "Barcelona",   41.3300,   2.1400),
    ("ind_zaragoza","Industria Zaragoza",            "quimica",     "Zaragoza",    41.6500,  -0.9300),
    ("ind_sevilla", "Industria Sevilla",             "quimica",     "Sevilla",     37.3600,  -6.0000),
    ("ind_madrid",  "Industria Madrid (Sur)",        "quimica",     "Madrid",      40.3300,  -3.6800),
    ("ind_valladol","Industria Valladolid",          "quimica",     "Valladolid",  41.6300,  -4.7500),
    ("ind_gijon",   "Industria Aviles (Asturias)",   "quimica",     "Asturias",    43.5500,  -5.9200),
    ("ind_cadiz",   "Industria Bahia de Cadiz",      "quimica",     "Cadiz",       36.5300,  -6.2000),
    ("ind_almeria", "Industria Almeria",             "quimica",     "Almeria",     36.8400,  -2.4600),
    ("ind_murcia",  "Industria Murcia",              "quimica",     "Murcia",      37.9800,  -1.1300),
    ("ind_alicante","Industria Alicante",            "quimica",     "Alicante",    38.3500,  -0.4800),
    ("ind_leon",    "Industria Leon",                "quimica",     "Leon",        42.6000,  -5.5700),
]

# --- PLANTAS CANDIDATAS: emplazamientos con buen recurso renovable ---
PLANTAS = [
    # id           nombre                             zona_recurso   provincia      lat       lon
    ("pl_andalu",  "Planta H2 Andalucia (solar)",     "solar_alto",  "Sevilla",     37.4000,  -5.9800),
    ("pl_extrem",  "Planta H2 Extremadura (solar)",   "solar_alto",  "Badajoz",     38.8800,  -6.9700),
    ("pl_castlm",  "Planta H2 Castilla-LM (solar)",   "solar_alto",  "Ciudad Real", 38.9900,  -3.9300),
    ("pl_aragon",  "Planta H2 Aragon (eolico/solar)", "mixto",       "Zaragoza",    41.5000,  -1.0000),
    ("pl_murcia",  "Planta H2 Murcia (solar)",        "solar_alto",  "Murcia",      37.9800,  -1.5000),
    ("pl_cataluna","Planta H2 Tarragona (mixto)",     "mixto",       "Tarragona",   41.1500,   0.9000),
    ("pl_valencia","Planta H2 C. Valenciana (solar)", "solar_medio", "Valencia",    39.4000,  -0.7000),
    ("pl_castleon","Planta H2 Castilla-Leon (eolico)","eolico",      "Palencia",    42.0100,  -4.5300),
    ("pl_navarra", "Planta H2 Navarra (eolico)",      "eolico",      "Navarra",     42.5000,  -1.6500),
    ("pl_galicia", "Planta H2 Galicia (eolico)",      "eolico",      "A Coruna",    43.1000,  -8.0000),
    ("pl_asturias","Planta H2 Asturias (eolico)",     "eolico",      "Asturias",    43.4000,  -5.8500),
    ("pl_cadiz",   "Planta H2 Cadiz (eolico/solar)",  "mixto",       "Cadiz",       36.4000,  -5.9000),
    ("pl_huelva",  "Planta H2 Huelva (solar)",        "solar_alto",  "Huelva",      37.3000,  -6.9000),
    ("pl_almeria", "Planta H2 Almeria (solar)",       "solar_alto",  "Almeria",     37.0000,  -2.4000),
    ("pl_teruel",  "Planta H2 Teruel (solar/eolico)", "mixto",       "Teruel",      40.7000,  -1.0000),
]


def clientes(n=None):
    """Devuelve los primeros n clientes del catalogo (o todos si n es None)."""
    return CLIENTES[:n] if n else CLIENTES


def plantas(n=None):
    """Devuelve las primeras n plantas del catalogo (o todas si n es None)."""
    return PLANTAS[:n] if n else PLANTAS


