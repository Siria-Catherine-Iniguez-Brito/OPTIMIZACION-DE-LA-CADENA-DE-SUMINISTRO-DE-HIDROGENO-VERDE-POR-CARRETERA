"""
inicializadores.py
==================

Los TRES modos de generacion de la poblacion inicial del algoritmo genetico,
nucleo de la comparacion del TFM "Optimizacion de la Cadena de Suministro de
Hidrogeno Verde por Carretera":

  (A) ALEATORIA
      Individuos generados al azar y reparados para garantizar factibilidad.
      Arranque "sin informacion", que sirve de linea base de comparacion.

  (B) SEMILLA NIVEL 1  (warm start)
      Individuos construidos a partir del POOL de soluciones exactas del Nivel 1.
      Cada solucion del Nivel 1 fija:
        - y_i  : que plantas se abren.
        - z_pj : que planta abastece a cada cliente (deducido de los flujos
                 f_ij > 0 del Nivel 1).
      Sobre esa asignacion, se AGRUPAN los clientes por la planta que los abastece
      y se construyen rutas iniciales; la reparacion las trocea para respetar la
      capacidad de cisterna CapV_m que el Nivel 1 no contemplaba. De este modo la
      solucion del Nivel 1 no se copia literalmente (podria ser infactible al
      anadir las restricciones de ruteo), sino que ORIENTA la busqueda.

  (C) MIXTA
      Una proporcion 'frac_semilla' de individuos tipo B y el resto tipo A, para
      combinar la explotacion de la semilla (B) con la diversidad del azar (A).

Desacoplamiento de PuLP
-----------------------
Este modulo NO importa el solver. Recibe el pool del Nivel 1 como una lista de
objetos con dos atributos:
    .abiertas   -> List[str]         (plantas abiertas, y_i = 1)
    .asignacion -> Dict[str, str]    (cliente j -> planta p, deducido de z_pj)
Asi funciona tanto con los objetos SolucionNivel1 de nivel1_exacto.py como con
cualquier estructura equivalente, y puede probarse de forma aislada.
"""

from __future__ import annotations

import random
from typing import Dict, List, Optional

from modelo import Instancia
from cromosoma import Cromosoma, Ruta
from reparacion import Reparador


class Inicializador:
    def __init__(self, inst: Instancia, reparador: Reparador,
                 semilla: Optional[int] = None):
        self.inst = inst
        self.rep = reparador
        self.rng = random.Random(semilla)

    # ------------------------------------------------------------------
    # (A) Un individuo aleatorio factible
    # ------------------------------------------------------------------
    def _individuo_aleatorio(self) -> Cromosoma:
        """Abre un subconjunto no vacio de plantas al azar, reparte los clientes
        aleatoriamente entre ellas y deja que el reparador garantice factibilidad
        (troceo por capacidad, limite de camiones, etc.)."""
        inst = self.inst
        n_abrir = self.rng.randint(1, len(inst.P))
        abiertas = self.rng.sample(inst.P, n_abrir)

        clientes = list(inst.J)
        self.rng.shuffle(clientes)
        asign: Dict[str, List[str]] = {p: [] for p in abiertas}
        for j in clientes:
            asign[self.rng.choice(abiertas)].append(j)

        rutas: List[Ruta] = []
        for p, cs in asign.items():
            if cs:
                modo = self.rng.choice(inst.M)
                rutas.append(Ruta(p, modo, cs))
        return self.rep.reparar(Cromosoma(rutas))

    # ------------------------------------------------------------------
    # (B) Un individuo a partir de una solucion del Nivel 1
    # ------------------------------------------------------------------
    def _individuo_desde_n1(self, sol, perturbar_orden: bool = True) -> Cromosoma:
        """Construye un cromosoma agrupando los clientes por la planta que los
        abastece segun la solucion del Nivel 1 (su asignacion z_pj). El modo
        inicial es el mas barato por km; la reparacion parte los grupos que
        excedan CapV_m. Si 'perturbar_orden', baraja el orden de visita para
        diversificar la poblacion manteniendo y_i y z_pj."""
        inst = self.inst
        clusters: Dict[str, List[str]] = {}
        for j, p in sol.asignacion.items():
            clusters.setdefault(p, []).append(j)

        rutas: List[Ruta] = []
        for p, cs in clusters.items():
            orden = list(cs)
            if perturbar_orden:
                self.rng.shuffle(orden)
            # Modo inicial: el mas barato por km que ADMITA al cliente mas grande
            # del grupo.
            dem_max = max(inst.Dem[j] for j in cs)
            modos_validos = [m for m in inst.M if inst.modos[m].CapV >= dem_max]
            modo = min(modos_validos or inst.M,
                   key=lambda m: inst.modos[m].coste_por_km)
            rutas.append(Ruta(p, modo, orden))
        return self.rep.reparar(Cromosoma(rutas))

    # ==================================================================
    # API publica
    # ==================================================================
    def poblacion_aleatoria(self, tam: int) -> List[Cromosoma]:
        """(A) Poblacion de 'tam' individuos aleatorios factibles."""
        return [self._individuo_aleatorio() for _ in range(tam)]

    def poblacion_semilla(self, tam: int, pool_n1: List) -> List[Cromosoma]:
        """(B) Poblacion de 'tam' individuos a partir del pool del Nivel 1.

        Se rota por el pool; el primer paso por cada solucion respeta el orden
        (warm start fiel) y los siguientes perturban el orden de visita para
        aportar diversidad conservando la localizacion y la asignacion del Nivel 1.
        """
        if not pool_n1:
            raise ValueError("poblacion_semilla requiere un pool del Nivel 1 no vacio.")
        pob: List[Cromosoma] = []
        for k in range(tam):
            sol = pool_n1[k % len(pool_n1)]
            pob.append(self._individuo_desde_n1(sol, perturbar_orden=(k >= len(pool_n1))))
        return pob

    def poblacion_mixta(self, tam: int, pool_n1: List,
                        frac_semilla: float = 0.5) -> List[Cromosoma]:
        """(C) Poblacion mixta: 'frac_semilla' de tipo B y el resto de tipo A."""
        n_sem = int(round(tam * frac_semilla))
        n_ale = tam - n_sem
        pob = self.poblacion_semilla(n_sem, pool_n1) if n_sem > 0 else []
        pob += self.poblacion_aleatoria(n_ale)
        self.rng.shuffle(pob)
        return pob

    def generar(self, tipo: str, tam: int, pool_n1: Optional[List] = None,
                frac_semilla: float = 0.5) -> List[Cromosoma]:
        """Punto de entrada unico, seleccionable por parametro: 'A' | 'B' | 'C'."""
        t = tipo.upper()
        if t == "A":
            return self.poblacion_aleatoria(tam)
        if t == "B":
            return self.poblacion_semilla(tam, pool_n1)
        if t == "C":
            return self.poblacion_mixta(tam, pool_n1, frac_semilla)
        raise ValueError(f"tipo de inicializacion '{tipo}' no valido (use A, B o C).")

