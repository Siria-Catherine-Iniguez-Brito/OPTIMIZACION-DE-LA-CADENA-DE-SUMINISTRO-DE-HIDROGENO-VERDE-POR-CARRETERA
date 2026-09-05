"""
catalogo_nodos.py
=================
Catalogo de NODOS de la cadena de suministro de hidrogeno verde en Espana.

Cada nodo lleva una CADENA DE BUSQUEDA ('consulta') que se envia al servicio de
geocodificacion Nominatim (OpenStreetMap) para obtener sus coordenadas de forma
TRAZABLE y REPRODUCIBLE (ver descargar_coordenadas.py). Asi, el dato de partida
justificable es el LUGAR (instalacion real o zona candidata elegida por criterio
experto), y la coordenada es el resultado citable de geocodificar ese lugar.

CLIENTES (nodos de demanda industrial): grandes consumidores REALES de hidrogeno.
  - Refinerias (las 8 refinerias reales de Espana)
  - Complejos quimicos / petroquimicos y fertilizantes (amoniaco) 
  - Siderurgia (demanda emergente via H2-DRI).
  Al ser instalaciones reales, la consulta apunta al nombre/localidad de la planta.

PLANTAS CANDIDATAS (ubicaciones de produccion): emplazamientos con buen recurso
  renovable, coherentes con los valles de hidrogeno de la Hoja de Ruta (MITECO).
  NO son instalaciones existentes: la coordenada es el punto REPRESENTATIVO de la
  provincia/localidad de la zona candidata, por lo que la consulta apunta a esa
  provincia (p. ej. "Badajoz, Espana").

Formato de cada nodo:
  CLIENTES: (id, nombre, tipo,         provincia, consulta)
  PLANTAS : (id, nombre, zona_recurso, provincia, consulta)
donde 'consulta' es el texto que se geocodifica con Nominatim.
"""

# --- CLIENTES: consumidores industriales reales ---
# (id, nombre, tipo, provincia, consulta_nominatim)
CLIENTES = [
    ("ref_corunya", "Refineria A Coruna (Repsol)",   "refineria",    "A Coruna",    "A Coruna, Espana"),
    ("ref_bilbao",  "Refineria Petronor (Muskiz)",   "refineria",    "Vizcaya",     "Muskiz, Vizcaya, Espana"),
    ("ref_tarrag",  "Refineria Tarragona (Repsol)",  "refineria",    "Tarragona",   "Tarragona, Espana"),
    ("ref_castell", "Refineria Castellon (BP)",      "refineria",    "Castellon",   "Castellon de la Plana, Espana"),
    ("ref_cartag",  "Refineria Cartagena (Repsol)",  "refineria",    "Murcia",      "Cartagena, Murcia, Espana"),
    ("ref_huelva",  "Refineria La Rabida (Moeve)",   "refineria",    "Huelva",      "Palos de la Frontera, Huelva, Espana"),
    ("ref_algecir", "Refineria San Roque (Moeve)",   "refineria",    "Cadiz",       "San Roque, Cadiz, Espana"),
    ("ref_puertoll","Refineria Puertollano (Repsol)","refineria",    "Ciudad Real", "Puertollano, Ciudad Real, Espana"),
    # Petroquimica / quimica / fertilizantes
    ("qui_tarrag",  "Petroquimica Tarragona",        "quimica",      "Tarragona",   "Tarragona, Espana"),
    ("qui_huelva",  "Polo quimico Huelva",           "quimica",      "Huelva",      "Palos de la Frontera, Huelva, Espana"),
    ("qui_puertoll","Complejo quimico Puertollano",  "quimica",      "Ciudad Real", "Puertollano, Ciudad Real, Espana"),
    ("fer_palos",   "Fertilizantes Palos (Huelva)",  "fertilizante", "Huelva",      "Palos de la Frontera, Huelva, Espana"),
    ("fer_sagunto", "Fertilizantes Sagunto",         "fertilizante", "Valencia",    "Sagunto, Valencia, Espana"),
    # Siderurgia (H2-DRI, demanda emergente)
    ("sid_gijon",   "Siderurgia Gijon-Verina",       "siderurgia",   "Asturias",    "Gijon, Asturias, Espana"),
    ("sid_sagunto", "Siderurgia Sagunto",            "siderurgia",   "Valencia",    "Sagunto, Valencia, Espana"),
    ("sid_bilbao",  "Siderurgia Sestao (Bizkaia)",   "siderurgia",   "Vizcaya",     "Sestao, Vizcaya, Espana"),
    # Otros consumidores industriales relevantes
    ("qui_cartag",  "Quimica Escombreras Cartagena", "quimica",      "Murcia",      "Cartagena, Murcia, Espana"),
    ("qui_tarrag2", "Quimica Sur Tarragona",         "quimica",      "Tarragona",   "Vila-seca, Tarragona, Espana"),
    ("ind_valencia","Industria Valencia",            "quimica",      "Valencia",    "Valencia, Espana"),
    ("ind_barna",   "Industria Barcelona (Zona F.)", "quimica",      "Barcelona",   "Barcelona, Espana"),
    ("ind_zaragoza","Industria Zaragoza",            "quimica",      "Zaragoza",    "Zaragoza, Espana"),
    ("ind_sevilla", "Industria Sevilla",             "quimica",      "Sevilla",     "Sevilla, Espana"),
    ("ind_madrid",  "Industria Madrid (Sur)",        "quimica",      "Madrid",      "Getafe, Madrid, Espana"),
    ("ind_valladol","Industria Valladolid",          "quimica",      "Valladolid",  "Valladolid, Espana"),
    ("ind_gijon",   "Industria Aviles (Asturias)",   "quimica",      "Asturias",    "Aviles, Asturias, Espana"),
    ("ind_cadiz",   "Industria Bahia de Cadiz",      "quimica",      "Cadiz",       "Puerto Real, Cadiz, Espana"),
    ("ind_almeria", "Industria Almeria",             "quimica",      "Almeria",     "Almeria, Espana"),
    ("ind_murcia",  "Industria Murcia",              "quimica",      "Murcia",      "Murcia, Espana"),
    ("ind_alicante","Industria Alicante",            "quimica",      "Alicante",    "Alicante, Espana"),
    ("ind_leon",    "Industria Leon",                "quimica",      "Leon",        "Leon, Espana"),
]

# --- PLANTAS CANDIDATAS: emplazamientos con buen recurso renovable ---
# (id, nombre, zona_recurso, provincia, consulta_nominatim)

PLANTAS = [
    ("pl_andalu",  "Planta H2 Andalucia (solar)",     "solar_alto",  "Sevilla",     "Sevilla, Espana"),
    ("pl_extrem",  "Planta H2 Extremadura (solar)",   "solar_alto",  "Badajoz",     "Badajoz, Espana"),
    ("pl_castlm",  "Planta H2 Castilla-LM (solar)",   "solar_alto",  "Ciudad Real", "Ciudad Real, Espana"),
    ("pl_aragon",  "Planta H2 Aragon (eolico/solar)", "mixto",       "Zaragoza",    "Zaragoza, Espana"),
    ("pl_murcia",  "Planta H2 Murcia (solar)",        "solar_alto",  "Murcia",      "Lorca, Murcia, Espana"),
    ("pl_cataluna","Planta H2 Tarragona (mixto)",     "mixto",       "Tarragona",   "Reus, Tarragona, Espana"),
    ("pl_valencia","Planta H2 C. Valenciana (solar)", "solar_medio", "Valencia",    "Requena, Valencia, Espana"),
    ("pl_castleon","Planta H2 Castilla-Leon (eolico)","eolico",      "Palencia",    "Palencia, Espana"),
    ("pl_navarra", "Planta H2 Navarra (eolico)",      "eolico",      "Navarra",     "Tudela, Navarra, Espana"),
    ("pl_galicia", "Planta H2 Galicia (eolico)",      "eolico",      "A Coruna",    "Ordes, A Coruna, Espana"),
    ("pl_asturias","Planta H2 Asturias (eolico)",     "eolico",      "Asturias",    "Tineo, Asturias, Espana"),
    ("pl_cadiz",   "Planta H2 Cadiz (eolico/solar)",  "mixto",       "Cadiz",       "Jerez de la Frontera, Cadiz, Espana"),
    ("pl_huelva",  "Planta H2 Huelva (solar)",        "solar_alto",  "Huelva",      "Huelva, Espana"),
    ("pl_almeria", "Planta H2 Almeria (solar)",       "solar_alto",  "Almeria",     "Tabernas, Almeria, Espana"),
    ("pl_teruel",  "Planta H2 Teruel (solar/eolico)", "mixto",       "Teruel",      "Teruel, Espana"),
]


def clientes(n=None):
    """Devuelve los primeros n clientes del catalogo (o todos si n es None)."""
    return CLIENTES[:n] if n else CLIENTES


def plantas(n=None):
    """Devuelve las primeras n plantas del catalogo (o todas si n es None)."""
    return PLANTAS[:n] if n else PLANTAS


def consultas_nodos(nodos):
    """Extrae la lista [(id, consulta), ...] a partir de tuplas del catalogo.
    La 'consulta' es siempre el ultimo campo de cada tupla."""
    return [(t[0], t[-1]) for t in nodos]
