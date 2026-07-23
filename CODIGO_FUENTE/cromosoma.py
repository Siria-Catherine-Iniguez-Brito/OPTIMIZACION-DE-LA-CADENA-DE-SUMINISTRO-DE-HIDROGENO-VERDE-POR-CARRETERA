"""
cromosoma.py
============

Representacion (codificacion) de una solucion del PROBLEMA GLOBAL del TFM
"Optimizacion de la Cadena de Suministro de Hidrogeno Verde por Carretera" y su
DECODIFICACION hacia las variables del modelo matematico de la memoria.

Codificacion estructurada por camion
------------------------------------
Un cromosoma es una lista de RUTAS, una por camion activo. Cada ruta guarda:

    Ruta(planta, modo, [clientes en orden de visita])

y representa el recorrido:  planta -> c_1 -> c_2 -> ... -> c_n -> planta.

Esta representacion hace ESTRUCTURALMENTE imposibles varias infactibilidades del
modelo (no hay que penalizarlas ni repararlas):

  * Retorno al deposito de origen        -> la ruta es un ciclo cerrado en 'planta'.
  * Un unico deposito por camion          -> cada ruta tiene una sola 'planta'.
  * Un unico modo por camion (w_km)       -> 'modo' es un atributo de la ruta.
  * Ausencia de sub-rutas (MTZ)           -> cada ruta es un ciclo simple.
  * Continuidad del flujo de vehiculos    -> arcos consecutivos de la secuencia.

Las infactibilidades que SI pueden aparecer (y que gestionan reparacion.py y
fitness.py con el enfoque hibrido acordado) son:

  * Capacidad de cisterna: sum de demandas de una ruta > CapV_m  -> reparar (split).
  * Visita unica: un cliente en 0 o >1 rutas                     -> reparar.
  * Nº de camiones usados > |K|                                  -> reparar/penalizar.
  * Coherencia cliente-planta z_pj                               -> se deriva de la ruta.
  * Capacidad de produccion de la planta                         -> penalizar si excede.

Decodificacion hacia el modelo
------------------------------
  y_i        = 1 si alguna ruta sale de i.
  z_pj       = 1 si el cliente j esta en una ruta con origen p.
  x_ijk^m    = 1 para cada arco consecutivo de la ruta del camion k con su modo m.
  f_ij^m     = flujo (kg) por el arco (i,j): carga que aun resta entregar aguas abajo.
  q_it       : produccion horaria; su total lo fija el balance de masa con perdidas
               sum_t q_it = sum_j sum_m f_ij^m / Efi_m (se calcula en fitness.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from modelo import Instancia


# ---------------------------------------------------------------------------
# Una ruta = un camion activo
# ---------------------------------------------------------------------------
@dataclass
class Ruta:
    """Ruta de un camion: sale de 'planta', visita 'clientes' en orden y regresa.

    Atributos:
        planta   : deposito de origen y retorno (p in P)
        modo     : modo de transporte del camion (m in M)  -> fija w_km
        clientes : lista ordenada de clientes visitados (subconjunto de J)
    """
    planta: str
    modo: str
    clientes: List[str] = field(default_factory=list)

    def copiar(self) -> "Ruta":
        return Ruta(self.planta, self.modo, list(self.clientes))

    def carga(self, inst: Instancia) -> float:
        """Carga total transportada por la ruta = suma de demandas de sus clientes."""
        return sum(inst.Dem[j] for j in self.clientes)

    def arcos(self) -> List[Tuple[str, str]]:
        """Arcos (i, j) del ciclo planta -> clientes -> planta."""
        if not self.clientes:
            return []
        secuencia = [self.planta] + list(self.clientes) + [self.planta]
        return [(secuencia[k], secuencia[k + 1]) for k in range(len(secuencia) - 1)]

    def vacia(self) -> bool:
        return len(self.clientes) == 0

    def __repr__(self) -> str:
        recorrido = " -> ".join([self.planta] + list(self.clientes) + [self.planta])
        return f"Ruta[{self.modo}]({recorrido})"


# ---------------------------------------------------------------------------
# Un cromosoma = conjunto de rutas (una solucion del problema global)
# ---------------------------------------------------------------------------
@dataclass
class Cromosoma:
    """Solucion completa del problema global: lista de rutas (camiones activos)."""
    rutas: List[Ruta] = field(default_factory=list)

    # ---- utilidades basicas ----
    def copiar(self) -> "Cromosoma":
        return Cromosoma([r.copiar() for r in self.rutas])

    def rutas_activas(self) -> List[Ruta]:
        """Rutas no vacias (camiones que realmente salen)."""
        return [r for r in self.rutas if not r.vacia()]

    def n_camiones(self) -> int:
        return len(self.rutas_activas())

    def clientes_visitados(self) -> List[str]:
        vis: List[str] = []
        for r in self.rutas:
            vis.extend(r.clientes)
        return vis

    def plantas_abiertas(self) -> List[str]:
        return sorted({r.planta for r in self.rutas_activas()})

    # ------------------------------------------------------------------
    # Comprobaciones de factibilidad (las usan reparacion.py y fitness.py)
    # ------------------------------------------------------------------
    def clientes_repetidos(self) -> List[str]:
        """Clientes visitados mas de una vez (violan visita unica)."""
        vis = self.clientes_visitados()
        return [j for j in set(vis) if vis.count(j) > 1]

    def clientes_sin_servir(self, inst: Instancia) -> List[str]:
        """Clientes de J que no aparecen en ninguna ruta."""
        vis = set(self.clientes_visitados())
        return [j for j in inst.J if j not in vis]

    def rutas_sobrecargadas(self, inst: Instancia) -> List[Ruta]:
        """Rutas cuya carga supera la capacidad de cisterna de su modo (CapV_m)."""
        return [r for r in self.rutas_activas()
                if r.carga(inst) > inst.modos[r.modo].CapV + 1e-6]

    def es_factible_ruteo(self, inst: Instancia) -> bool:
        """Factibilidad de la parte de ruteo (visita unica, capacidad, nº camiones)."""
        return (not self.clientes_repetidos()
                and not self.clientes_sin_servir(inst)
                and not self.rutas_sobrecargadas(inst)
                and self.n_camiones() <= len(inst.K))

    # ==================================================================
    # DECODIFICACION hacia las variables del modelo
    # ==================================================================
    def decodificar(self, inst: Instancia) -> dict:
        """Traduce el cromosoma a las variables del modelo matematico:
        y_i, z_pj, x_ijk^m, f_ij^m. La produccion q_it y el balance de masa
        (con el factor 1/Efi_m) se calculan en fitness.py, que es quien conoce
        el coste. Devuelve un diccionario con dichas estructuras.
        """
        activas = self.rutas_activas()

        # y_i: plantas de las que sale algun camion
        y = {i: 0 for i in inst.P}
        for r in activas:
            y[r.planta] = 1

        # z_pj: cliente j asignado a la planta de su ruta
        z = {(p, j): 0 for p in inst.P for j in inst.J}
        for r in activas:
            for j in r.clientes:
                z[(r.planta, j)] = 1

        # x_ijk^m y f_ij^m: recorremos cada ruta (= camion k) arco a arco.
        # El flujo por un arco es la carga que resta entregar aguas abajo, es decir,
        # la suma de demandas de los clientes que quedan por visitar desde ese arco.
        x: Dict[Tuple[str, str, int, str], int] = {}
        f: Dict[Tuple[str, str, str], float] = {}
        for k, r in enumerate(activas):
            m = r.modo
            secuencia = [r.planta] + list(r.clientes) + [r.planta]
            # carga que sale de la planta = demanda total de la ruta
            restante = r.carga(inst)
            for pos in range(len(secuencia) - 1):
                i, j = secuencia[pos], secuencia[pos + 1]
                x[(i, j, k, m)] = 1
                # flujo por el arco (i, j): lo que aun se lleva en el camion
                f[(i, j, m)] = f.get((i, j, m), 0.0) + restante
                # tras visitar j (si es cliente) se descarga su demanda
                if j in inst.Dem:
                    restante -= inst.Dem[j]

        return {"y": y, "z": z, "x": x, "f": f,
                "plantas_abiertas": self.plantas_abiertas(),
                "n_camiones": self.n_camiones()}

    def __repr__(self) -> str:
        return ("Cromosoma(\n  " +
                "\n  ".join(repr(r) for r in self.rutas_activas()) +
                "\n)")
