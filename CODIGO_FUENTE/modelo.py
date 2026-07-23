"""
modelo.py
=========

Modulo base del TFM "Optimizacion de la Cadena de Suministro de Hidrogeno Verde
por Carretera". Define la estructura de datos del modelo matematico global
(conjuntos, parametros y notacion) tal y como aparecen en la seccion
DESCRIPCION DEL PROBLEMA de la memoria.

Este modulo es la UNICA fuente que lee los datos del disco y los prepara para el
resto del programa. En concreto:

  - Carga la instancia desde un fichero JSON.
  - Construye la matriz de distancias reales por carretera D[i][j] (km) segun el
    campo meta.fuente_distancias:
        * "matriz_real" -> lee la matriz OSRM del fichero.
        * "euclidea"    -> la calcula al vuelo desde las coordenadas (haversine).
    Cambiar de un modo a otro es SOLO cambiar ese campo; ningun otro modulo
    necesita enterarse de como se obtuvieron las distancias.
  - Deriva el coste de transporte de cada arco y modo:
        CosteT[i][j][m] = coste_por_km[m] * D[i][j]
  - Deriva el parametro HTotal = sum_{j in J} Dem_j.
  - Valida que la instancia respete la notacion y los dominios del modelo.

Correspondencia con la notacion de la memoria
---------------------------------------------
Conjuntos:   P, J, N = P u J, K, T (=24), M
Parametros:  Fijo_i, CosteO_i, Cap_i, Ren_{i,t}, Dem_j,
             CapV_m, CosteT_{ij}^m, Efi_m, HTotal
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Utilidades geometricas (solo para el modo de prueba "euclidea")
# ---------------------------------------------------------------------------
def _haversine_km(coord_a: Tuple[float, float], coord_b: Tuple[float, float]) -> float:
    """Distancia haversine (gran circulo) en km entre dos puntos (lat, lon).

    Se emplea unicamente en el modo de prueba "euclidea" para aproximar
    distancias mientras no se dispone de la matriz real por carretera. Con datos
    definitivos se usara "matriz_real" y esta funcion no interviene.
    """
    radio_tierra_km = 6371.0088
    lat1, lon1 = math.radians(coord_a[0]), math.radians(coord_a[1])
    lat2, lon2 = math.radians(coord_b[0]), math.radians(coord_b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2.0) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0) ** 2
    return 2.0 * radio_tierra_km * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Estructura de un modo de transporte m in M
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Modo:
    """Modo de transporte del hidrogeno (comprimido, liquido, portador quimico).

    Atributos (notacion de la memoria):
        nombre       : etiqueta del modo m in M
        CapV         : CapV_m  -> capacidad de carga de la cisterna (kg)
        Efi          : Efi_m   -> eficiencia de acondicionamiento en (0, 1]
        coste_por_km : factor de coste por km propio del modo (EUR/km)
    """
    nombre: str
    CapV: float
    Efi: float
    coste_por_km: float


# ---------------------------------------------------------------------------
# Clase principal: una instancia completa del problema
# ---------------------------------------------------------------------------
@dataclass
class Instancia:
    """Representa una instancia del modelo global de la cadena de suministro.

    Toda la notacion del modelo esta disponible como atributos ya listos para
    usar por el resto de modulos (Nivel 1, cromosoma, fitness, GA...).
    """

    # --- Metadatos ---
    nombre: str
    descripcion: str
    fuente_distancias: str  # "matriz_real" | "euclidea"

    # --- Conjuntos ---
    P: List[str]                     # ubicaciones candidatas (depositos/plantas)
    J: List[str]                     # nodos de demanda (clientes)
    K: List[str]                     # camiones de la flota comun
    M: List[str]                     # modos de transporte
    T: int                           # numero de periodos horarios (= 24)

    # --- Parametros de plantas (indexados por i in P) ---
    Fijo: Dict[str, float]           # Fijo_i   (EUR/dia, CAPEX anualizado)
    CosteO: Dict[str, float]         # CosteO_i (EUR/kg, OPEX unitario)
    Cap: Dict[str, float]            # Cap_i    (kg/h, capacidad electrolizador)
    Ren: Dict[str, List[float]]      # Ren_{i,t} (kg/h) lista de longitud T

    # --- Parametros de clientes (indexados por j in J) ---
    Dem: Dict[str, float]            # Dem_j    (kg/dia)

    # --- Parametros de modos (indexados por m in M) ---
    modos: Dict[str, Modo]           # CapV_m, Efi_m, coste_por_km[m]

    # --- Geometria y logistica ---
    coordenadas: Dict[str, Tuple[float, float]]   # solo para mapas/figuras
    D: Dict[str, Dict[str, float]] = field(default_factory=dict)   # D[i][j] km

    # --- Parametros derivados ---
    HTotal: float = 0.0              # HTotal = sum_j Dem_j
    CosteT: Dict[Tuple[str, str, str], float] = field(default_factory=dict)
    # CosteT[(i, j, m)] = coste_por_km[m] * D[i][j]

    # ------------------------------------------------------------------
    # Conjunto derivado N = P u J
    # ------------------------------------------------------------------
    @property
    def N(self) -> List[str]:
        """Todos los nodos de la red logistica: N = P u J."""
        return list(self.P) + list(self.J)

    @property
    def CapV_max(self) -> float:
        """Cota superior CapV_barra = max_{m in M} CapV_m usada en las
        restricciones de eliminacion de sub-rutas (MTZ) del modelo global."""
        return max(self.modos[m].CapV for m in self.M)

    # ------------------------------------------------------------------
    # Carga desde JSON
    # ------------------------------------------------------------------
    @classmethod
    def desde_json(cls, ruta: str) -> "Instancia":
        """Construye una Instancia a partir de un fichero JSON con el esquema
        acordado. Realiza la carga, el calculo de distancias/costes derivados y
        la validacion completa antes de devolver el objeto."""
        with open(ruta, "r", encoding="utf-8") as fh:
            raw = json.load(fh)

        meta = raw["meta"]
        conjuntos = raw["conjuntos"]

        # --- Modos ---
        modos: Dict[str, Modo] = {}
        for m_nombre, m_data in raw["modos"].items():
            modos[m_nombre] = Modo(
                nombre=m_nombre,
                CapV=float(m_data["CapV"]),
                Efi=float(m_data["Efi"]),
                coste_por_km=float(m_data["coste_por_km"]),
            )

        # --- Plantas ---
        Fijo, CosteO, Cap, Ren = {}, {}, {}, {}
        for i, pd in raw["plantas"].items():
            Fijo[i] = float(pd["Fijo"])
            CosteO[i] = float(pd["CosteO"])
            Cap[i] = float(pd["Cap"])
            Ren[i] = [float(v) for v in pd["Ren"]]

        # --- Clientes ---
        Dem = {j: float(cd["Dem"]) for j, cd in raw["clientes"].items()}

        # --- Coordenadas (ignoramos claves auxiliares que empiezan por "_") ---
        coordenadas = {
            k: (float(v[0]), float(v[1]))
            for k, v in raw.get("coordenadas", {}).items()
            if not k.startswith("_")
        }

        inst = cls(
            nombre=meta["nombre"],
            descripcion=meta.get("descripcion", ""),
            fuente_distancias=meta["fuente_distancias"],
            P=list(conjuntos["P"]),
            J=list(conjuntos["J"]),
            K=list(conjuntos["K"]),
            M=list(conjuntos["M"]),
            T=int(meta.get("T", 24)),
            Fijo=Fijo, CosteO=CosteO, Cap=Cap, Ren=Ren,
            Dem=Dem, modos=modos, coordenadas=coordenadas,
        )

        # Distancias -> costes -> derivados
        inst.D = inst._construir_distancias(raw.get("matriz_distancias", {}))
        inst.CosteT = inst._construir_costes_transporte()
        inst.HTotal = sum(inst.Dem[j] for j in inst.J)

        inst.validar()
        return inst

    # ------------------------------------------------------------------
    # Construccion de la matriz de distancias D[i][j] (km)
    # ------------------------------------------------------------------
    def _construir_distancias(self, bloque_matriz: dict) -> Dict[str, Dict[str, float]]:
        """Devuelve D[i][j] en km segun el conmutador fuente_distancias.

        El resultado es SIEMPRE la misma estructura, sea cual sea el origen; asi
        el resto del programa nunca depende de como se obtuvieron las distancias.
        """
        nodos = self.N
        D: Dict[str, Dict[str, float]] = {i: {} for i in nodos}

        if self.fuente_distancias == "matriz_real":
            valores = bloque_matriz.get("valores", {})
            if not valores:
                raise ValueError(
                    "fuente_distancias='matriz_real' pero 'matriz_distancias.valores' "
                    "esta vacia. Rellena la matriz OSRM o usa fuente_distancias='euclidea'."
                )
            for i in nodos:
                for j in nodos:
                    if i == j:
                        D[i][j] = 0.0
                    else:
                        # Se admite matriz asimetrica (rutas de ida != vuelta);
                        # si falta un sentido se toma el simetrico como respaldo.
                        if j in valores.get(i, {}):
                            D[i][j] = float(valores[i][j])
                        elif i in valores.get(j, {}):
                            D[i][j] = float(valores[j][i])
                        else:
                            raise ValueError(
                                f"Falta la distancia real por carretera del arco ({i}, {j})."
                            )

        elif self.fuente_distancias == "euclidea":
            # Modo de PRUEBA: distancia haversine desde coordenadas.
            for i in nodos:
                for j in nodos:
                    if i == j:
                        D[i][j] = 0.0
                    else:
                        D[i][j] = _haversine_km(self.coordenadas[i], self.coordenadas[j])
        else:
            raise ValueError(
                f"fuente_distancias='{self.fuente_distancias}' no valido. "
                "Use 'matriz_real' o 'euclidea'."
            )

        return D

    # ------------------------------------------------------------------
    # Construccion de los costes de transporte CosteT[(i, j, m)]
    # ------------------------------------------------------------------
    def _construir_costes_transporte(self) -> Dict[Tuple[str, str, str], float]:
        """CosteT_{ij}^m = coste_por_km[m] * D[i][j] para todo arco y modo."""
        costes: Dict[Tuple[str, str, str], float] = {}
        for m in self.M:
            cpk = self.modos[m].coste_por_km
            for i in self.N:
                for j in self.N:
                    if i != j:
                        costes[(i, j, m)] = cpk * self.D[i][j]
        return costes

    # ------------------------------------------------------------------
    # Validacion de la instancia frente a la notacion del modelo
    # ------------------------------------------------------------------
    def validar(self) -> None:
        """Comprueba dominios y coherencia. Lanza ValueError con mensaje claro
        si algo no casa con el modelo (estilo "mensaje de error que dice que
        paso y como arreglarlo")."""
        errores: List[str] = []

        # Conjuntos no vacios y sin solapamiento P n J
        if not self.P:
            errores.append("El conjunto P (plantas candidatas) esta vacio.")
        if not self.J:
            errores.append("El conjunto J (clientes) esta vacio.")
        if not self.K:
            errores.append("El conjunto K (camiones) esta vacio.")
        if not self.M:
            errores.append("El conjunto M (modos) esta vacio.")
        solapan = set(self.P) & set(self.J)
        if solapan:
            errores.append(f"P y J comparten nodos {sorted(solapan)}; deben ser disjuntos.")

        # Horizonte temporal
        if self.T <= 0:
            errores.append(f"T debe ser positivo (recibido {self.T}).")

        # Parametros de plantas
        for i in self.P:
            if i not in self.Fijo:
                errores.append(f"Falta Fijo_i para la planta '{i}'.")
            if self.Cap.get(i, 0) <= 0:
                errores.append(f"Cap_i de '{i}' debe ser > 0.")
            ren = self.Ren.get(i, [])
            if len(ren) != self.T:
                errores.append(
                    f"Ren_(i,t) de '{i}' tiene {len(ren)} valores; se esperaban T={self.T}."
                )
            if any(v < 0 for v in ren):
                errores.append(f"Ren_(i,t) de '{i}' contiene valores negativos.")

        # Parametros de clientes
        for j in self.J:
            if self.Dem.get(j, 0) <= 0:
                errores.append(f"Dem_j de '{j}' debe ser > 0.")

        # Parametros de modos: Efi_m in (0, 1], CapV_m > 0, coste_por_km >= 0
        for m in self.M:
            if m not in self.modos:
                errores.append(f"Falta la definicion del modo '{m}'.")
                continue
            mod = self.modos[m]
            if not (0.0 < mod.Efi <= 1.0):
                errores.append(f"Efi_m de '{m}' = {mod.Efi} fuera de (0, 1].")
            if mod.CapV <= 0:
                errores.append(f"CapV_m de '{m}' debe ser > 0.")
            if mod.coste_por_km < 0:
                errores.append(f"coste_por_km de '{m}' no puede ser negativo.")

        # Factibilidad de capacidad agregada: la demanda de un cliente no puede
        # exceder la mayor cisterna disponible (ningun camion podria servirlo).
        for j in self.J:
            if self.Dem[j] > self.CapV_max + 1e-9:
                errores.append(
                    f"Dem_j de '{j}' = {self.Dem[j]} supera la mayor cisterna "
                    f"CapV_max = {self.CapV_max}; ese cliente seria inservible."
                )

        # Coordenadas presentes si se usa el modo euclideo
        if self.fuente_distancias == "euclidea":
            faltan = [n for n in self.N if n not in self.coordenadas]
            if faltan:
                errores.append(
                    f"fuente_distancias='euclidea' pero faltan coordenadas de {faltan}."
                )

        if errores:
            raise ValueError(
                "La instancia no supera la validacion:\n  - " + "\n  - ".join(errores)
            )

    # ------------------------------------------------------------------
    # Resumen legible
    # ------------------------------------------------------------------
    def resumen(self) -> str:
        return (
            f"Instancia '{self.nombre}'  ({self.descripcion})\n"
            f"  |P|={len(self.P)}  |J|={len(self.J)}  |K|={len(self.K)}  "
            f"|M|={len(self.M)}  T={self.T}\n"
            f"  fuente_distancias = {self.fuente_distancias}\n"
            f"  HTotal = {self.HTotal:.1f} kg/dia   CapV_max = {self.CapV_max:.1f} kg"
        )


