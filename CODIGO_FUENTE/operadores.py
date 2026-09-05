"""
operadores.py
=============

Operadores del algoritmo genetico, adaptados a la codificacion por rutas
(cromosoma.py) del problema global del TFM "Optimizacion de la Cadena de
Suministro de Hidrogeno Verde por Carretera".

Componentes:

  - SELECCION : torneo deterministico de tamano k (se eligen k individuos al azar
                y gana el de mejor fitness).
  - CRUCE     : cruce basado en rutas (route-based crossover, inspirado en VRP): el
                hijo hereda un subconjunto de rutas COMPLETAS de un progenitor y
                completa los clientes restantes segun el orden del otro; despues se
                REPARA.
  - MUTACION  : tres operadores elementales, cada uno con probabilidad PM:
                  (m1) reordenar dos clientes dentro de una misma ruta (intra-ruta).
                  (m2) mover un cliente de una ruta a otra (inter-ruta).
                  (m3) cambiar el modo de transporte de una ruta (explora w_km).
  - REEMPLAZO : elitismo (se conservan los mejores de padres + hijos).

Todos los operadores que crean descendencia devuelven cromosomas ya REPARADOS
(enfoque hibrido), de modo que la poblacion se mantiene mayoritariamente factible.
"""

from __future__ import annotations

import random
from typing import List, Optional, Tuple

from modelo import Instancia
from cromosoma import Cromosoma, Ruta
from fitness import EvaluadorFitness
from reparacion import Reparador


class OperadoresGA:
    def __init__(self, inst: Instancia, evaluador: EvaluadorFitness,
                 reparador: Reparador, semilla: Optional[int] = None):
        self.inst = inst
        self.ev = evaluador
        self.rep = reparador
        self.rng = random.Random(semilla)

    # ------------------------------------------------------------------
    # SELECCION: torneo deterministico
    # ------------------------------------------------------------------
    def seleccion_torneo(self, poblacion: List[Cromosoma],
                         fitness: List[float], k: int = 3) -> Cromosoma:
        """Elige k individuos al azar y devuelve una COPIA del de menor fitness."""
        idx = self.rng.sample(range(len(poblacion)), min(k, len(poblacion)))
        ganador = min(idx, key=lambda i: fitness[i])
        return poblacion[ganador].copiar()

    # ------------------------------------------------------------------
    # CRUCE basado en rutas
    # ------------------------------------------------------------------
    def cruce(self, padreA: Cromosoma, padreB: Cromosoma) -> Cromosoma:
        """El hijo hereda un subconjunto de rutas completas de A y completa los
        clientes que falten segun el orden en que aparecen en B; luego se repara."""
        inst = self.inst
        rutasA = padreA.rutas_activas()
        if not rutasA:
            return padreB.copiar()

        # Heredar una fraccion aleatoria de rutas completas de A
        n_hered = self.rng.randint(1, len(rutasA))
        heredadas = self.rng.sample(rutasA, n_hered)
        hijo = Cromosoma([r.copiar() for r in heredadas])
        ya = set(hijo.clientes_visitados())

        # Completar con los clientes que faltan, en el orden en que aparecen en B
        faltan = [j for r in padreB.rutas_activas() for j in r.clientes if j not in ya]
        faltan += [j for j in inst.J if j not in ya and j not in faltan]

        if faltan:
            planta = hijo.plantas_abiertas()[0] if hijo.plantas_abiertas() else inst.P[0]
            modo = heredadas[0].modo if heredadas else inst.M[0]
            hijo.rutas.append(Ruta(planta, modo, faltan))

        return self.rep.reparar(hijo)

    # ------------------------------------------------------------------
    # MUTACION: tres operadores elementales
    # ------------------------------------------------------------------
    def _m1_reordenar_intra(self, c: Cromosoma) -> None:
        """Intercambia dos clientes dentro de una misma ruta (mejora intra-ruta)."""
        candidatas = [r for r in c.rutas_activas() if len(r.clientes) >= 2]
        if not candidatas:
            return
        r = self.rng.choice(candidatas)
        i, j = self.rng.sample(range(len(r.clientes)), 2)
        r.clientes[i], r.clientes[j] = r.clientes[j], r.clientes[i]

    def _m2_mover_cliente(self, c: Cromosoma) -> None:
        """Mueve un cliente de una ruta a otra (redistribucion inter-ruta)."""
        activas = c.rutas_activas()
        if len(activas) < 2:
            return
        con_clientes = [r for r in activas if r.clientes]
        if not con_clientes:
            return
        origen = self.rng.choice(con_clientes)
        j = self.rng.choice(origen.clientes)
        destino = self.rng.choice([r for r in activas if r is not origen])
        origen.clientes.remove(j)
        pos = self.rng.randint(0, len(destino.clientes))
        destino.clientes.insert(pos, j)

    def _m3_cambiar_modo(self, c: Cromosoma) -> None:
        """Cambia el modo de transporte de una ruta (explora la asignacion w_km)."""
        if len(self.inst.M) < 2:
            return
        activas = c.rutas_activas()
        if not activas:
            return
        r = self.rng.choice(activas)
        r.modo = self.rng.choice([m for m in self.inst.M if m != r.modo])

    def mutar(self, cromo: Cromosoma, PM: float = 0.2) -> Cromosoma:
        """Aplica los tres operadores de mutacion, cada uno con probabilidad PM,
        y repara el resultado."""
        c = cromo.copiar()
        if self.rng.random() < PM:
            self._m1_reordenar_intra(c)
        if self.rng.random() < PM:
            self._m2_mover_cliente(c)
        if self.rng.random() < PM:
            self._m3_cambiar_modo(c)
        return self.rep.reparar(c)

    # ------------------------------------------------------------------
    # REEMPLAZO: elitismo
    # ------------------------------------------------------------------
    def reemplazo_elitista(self, poblacion: List[Cromosoma], fit_pob: List[float],
                           hijos: List[Cromosoma], fit_hijos: List[float]
                           ) -> Tuple[List[Cromosoma], List[float]]:
        """Combina padres e hijos y conserva los N mejores (N = tamano poblacion).
        Garantiza que el mejor individuo nunca se pierda entre generaciones."""
        combinado = list(zip(poblacion + hijos, fit_pob + fit_hijos))
        combinado.sort(key=lambda t: t[1])
        n = len(poblacion)
        nueva = [c for c, _ in combinado[:n]]
        nueva_fit = [f for _, f in combinado[:n]]
        return nueva, nueva_fit

