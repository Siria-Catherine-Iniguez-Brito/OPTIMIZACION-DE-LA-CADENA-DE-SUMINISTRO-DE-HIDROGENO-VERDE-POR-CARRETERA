"""
nivel1_exacto.py
================

Solver EXACTO del NIVEL 1 de la estrategia de resolucion encadenada del TFM
"Optimizacion de la Cadena de Suministro de Hidrogeno Verde por Carretera".

El Nivel 1 es un modelo SIMPLIFICADO del problema global: resuelve solo la parte
de LOCALIZACION de plantas y un TRANSPORTE de FLUJO DIRECTO planta -> cliente,
SIN rutas, SIN camiones y SIN eliminacion de sub-rutas. Es un problema lineal
entero mixto (MILP) pequeno que CBC resuelve en fracciones de segundo, incluso
para instancias grandes, porque su numero de variables crece linealmente (P + P*J)
y no de forma combinatoria como el problema global (que se aborda con el genetico).

Su proposito es doble:
  1. Servir de REFERENCIA / cota inferior de la parte de localizacion + produccion
     para validar la calidad del algoritmo genetico.
  2. Generar un POOL de soluciones factibles buenas y diversas que sirvan de
     SEMILLA (warm start) para la inicializacion tipo B/C del genetico. De cada
     solucion se deduce:
        - y_i  : que plantas se abren.
        - z_pj : que planta abastece a cada cliente (deducido de los flujos
                 f_ij > 0 del Nivel 1).

Modelo del Nivel 1 (variables: y_i binaria, f_ij >= 0 flujo directo, q_it >= 0)
------------------------------------------------------------------------------
  min  sum_i Fijo_i * y_i                                (CAPEX)
     + sum_i sum_t CosteO_i * q_it                       (OPEX produccion)
     + sum_i sum_j costo_directo_ij * f_ij               (transporte directo)

  s.a.
    (D1) sum_i f_ij = Dem_j                 para todo j   (satisfacer demanda)
    (D2) sum_j f_ij <= Cap_i * y_i          para todo i   (capacidad / apertura)
    (D3) q_it <= Cap_i * y_i                para todo i,t (capacidad electrolizador)
    (D4) q_it <= Ren_it                     para todo i,t (energia renovable)
    (D5) sum_t q_it = sum_j f_ij / Efi_ref  para todo i   (balance de masa con
                                                            perdidas de acondicionamiento)
         y_i in {0,1},  f_ij, q_it >= 0

Notas de modelizacion
---------------------
- El Nivel 1 NO decide el modo de transporte m (eso es del Nivel 2). Para el coste
  y las perdidas se usa un modo de REFERENCIA (por defecto el mas eficiente,
  Efi mas alta, y su coste_por_km), de forma que el balance de masa (D5) ya
  contemple perdidas de acondicionamiento de forma aproximada. El modo de
  referencia es configurable.
- El coste de transporte directo del arco (i, j) es
        costo_directo_ij = coste_por_km[m_ref] * D[i][j].
- Al deducir z_pj se asigna cada cliente a la planta que le envia MAYOR flujo
  (regla de mayoria), garantizando z_pj binaria y coherente (una planta por cliente).

Dependencias
------------
PuLP (con el solver CBC incluido). Ver requirements.txt.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pulp

from modelo import Instancia


# ---------------------------------------------------------------------------
# Estructura de una solucion del Nivel 1
# ---------------------------------------------------------------------------
@dataclass
class SolucionNivel1:
    """Una solucion factible del Nivel 1.

    Atributos:
        y       : dict i -> 0/1   (plantas abiertas)
        f       : dict (i, j) -> flujo directo en kg
        q       : dict (i, t) -> produccion horaria en kg
        z       : dict (p, j) -> 0/1  asignacion cliente-planta deducida de f
        coste   : valor de la funcion objetivo del Nivel 1 (numerador del LCOH)
        abiertas: lista de plantas con y_i = 1
        asignacion: dict j -> p  (planta que abastece a cada cliente)
    """
    y: Dict[str, int]
    f: Dict[Tuple[str, str], float]
    q: Dict[Tuple[str, int], float]
    z: Dict[Tuple[str, str], int]
    coste: float
    abiertas: List[str] = field(default_factory=list)
    asignacion: Dict[str, str] = field(default_factory=dict)

    def resumen(self) -> str:
        clusters: Dict[str, List[str]] = {}
        for j, p in self.asignacion.items():
            clusters.setdefault(p, []).append(j)
        partes = [f"{p}:[{','.join(sorted(cs))}]" for p, cs in sorted(clusters.items())]
        return (f"coste={self.coste:.2f} EUR | abiertas={sorted(self.abiertas)} | "
                f"clusters {{{'; '.join(partes)}}}")


# ---------------------------------------------------------------------------
# Solver principal del Nivel 1
# ---------------------------------------------------------------------------
class SolverNivel1:
    """Construye y resuelve el modelo MILP del Nivel 1 con PuLP + CBC."""

    def __init__(self, inst: Instancia, modo_referencia: Optional[str] = None,
                 solver_msg: bool = False):
        self.inst = inst
        # Modo de referencia para coste/perdidas: por defecto el mas eficiente.
        if modo_referencia is None:
            modo_referencia = max(inst.M, key=lambda m: inst.modos[m].Efi)
        self.m_ref = modo_referencia
        self.Efi_ref = inst.modos[self.m_ref].Efi
        self.solver_msg = solver_msg

    # ------------------------------------------------------------------
    # Construccion del modelo (opcionalmente con costes perturbados)
    # ------------------------------------------------------------------
    def _construir(self, fijo_pert: Optional[Dict[str, float]] = None,
                   op_pert: Optional[Dict[str, float]] = None) -> Tuple[pulp.LpProblem, dict]:
        inst = self.inst
        Fijo = fijo_pert if fijo_pert is not None else inst.Fijo
        CosteO = op_pert if op_pert is not None else inst.CosteO

        prob = pulp.LpProblem("Nivel1_localizacion_flujo", pulp.LpMinimize)

        # --- Variables ---
        y = {i: pulp.LpVariable(f"y_{i}", cat="Binary") for i in inst.P}
        f = {(i, j): pulp.LpVariable(f"f_{i}_{j}", lowBound=0)
             for i in inst.P for j in inst.J}
        q = {(i, t): pulp.LpVariable(f"q_{i}_{t}", lowBound=0)
             for i in inst.P for t in range(inst.T)}

        # --- Objetivo: CAPEX + OPEX + transporte directo ---
        capex = pulp.lpSum(Fijo[i] * y[i] for i in inst.P)
        opex = pulp.lpSum(CosteO[i] * q[(i, t)] for i in inst.P for t in range(inst.T))
        cpk = inst.modos[self.m_ref].coste_por_km
        transp = pulp.lpSum(cpk * inst.D[i][j] * f[(i, j)]
                            for i in inst.P for j in inst.J)
        prob += capex + opex + transp, "coste_total_nivel1"

        # --- (D1) Satisfaccion de la demanda ---
        for j in inst.J:
            prob += pulp.lpSum(f[(i, j)] for i in inst.P) == inst.Dem[j], f"demanda_{j}"

        # --- (D2) Capacidad de planta / apertura ---
        # La produccion diaria maxima es sum_t min(Cap_i, Ren_it), no Cap_i (que es horaria).
        for i in inst.P:
            prod_diaria_max = sum(min(inst.Cap[i], inst.Ren[i][t]) for t in range(inst.T))
            prob += pulp.lpSum(f[(i, j)] for j in inst.J) <= prod_diaria_max * y[i], f"cap_{i}"


        # --- (D3) Capacidad del electrolizador ---
        for i in inst.P:
            for t in range(inst.T):
                prob += q[(i, t)] <= inst.Cap[i] * y[i], f"electro_{i}_{t}"

        # --- (D4) Energia renovable disponible ---
        for i in inst.P:
            for t in range(inst.T):
                prob += q[(i, t)] <= inst.Ren[i][t], f"renov_{i}_{t}"

        # --- (D5) Balance de masa con perdidas (modo de referencia) ---
        for i in inst.P:
            prob += (pulp.lpSum(q[(i, t)] for t in range(inst.T))
                     == pulp.lpSum(f[(i, j)] for j in inst.J) / self.Efi_ref), f"balance_{i}"

        return prob, {"y": y, "f": f, "q": q}

    # ------------------------------------------------------------------
    # Resolver una vez y extraer la solucion
    # ------------------------------------------------------------------
    def _resolver(self, prob: pulp.LpProblem, vars_: dict,
                  extra_no_good: Optional[List[pulp.LpConstraint]] = None) -> Optional[SolucionNivel1]:
        if extra_no_good:
            for k, c in enumerate(extra_no_good):
                prob += c, f"nogood_{k}_{id(c)}"
        solver = pulp.PULP_CBC_CMD(msg=1 if self.solver_msg else 0)
        prob.solve(solver)
        if pulp.LpStatus[prob.status] != "Optimal":
            return None
        return self._extraer(vars_)

    # ------------------------------------------------------------------
    # Extraer la solucion y deducir z_pj y la asignacion cliente-planta
    # ------------------------------------------------------------------
    def _extraer(self, vars_: dict) -> SolucionNivel1:
        inst = self.inst
        y = {i: int(round(vars_["y"][i].value() or 0)) for i in inst.P}
        f = {(i, j): float(vars_["f"][(i, j)].value() or 0.0)
             for i in inst.P for j in inst.J}
        q = {(i, t): float(vars_["q"][(i, t)].value() or 0.0)
             for i in inst.P for t in range(inst.T)}

        # Coste real (con parametros originales, no perturbados)
        cpk = inst.modos[self.m_ref].coste_por_km
        coste = (sum(inst.Fijo[i] * y[i] for i in inst.P)
                 + sum(inst.CosteO[i] * q[(i, t)] for i in inst.P for t in range(inst.T))
                 + sum(cpk * inst.D[i][j] * f[(i, j)] for i in inst.P for j in inst.J))

        abiertas = [i for i in inst.P if y[i] == 1]

        # Deduccion de z_pj: cada cliente se asigna a la planta que le manda mas flujo
        asignacion: Dict[str, str] = {}
        for j in inst.J:
            flujos = {i: f[(i, j)] for i in inst.P if f[(i, j)] > 1e-6}
            planta = max(flujos, key=flujos.get) if flujos else (abiertas[0] if abiertas else inst.P[0])
            asignacion[j] = planta
        z = {(p, j): (1 if asignacion[j] == p else 0) for p in inst.P for j in inst.J}

        return SolucionNivel1(y=y, f=f, q=q, z=z, coste=coste,
                              abiertas=abiertas, asignacion=asignacion)

    # ==================================================================
    # API PUBLICA
    # ==================================================================
    def resolver_optimo(self) -> SolucionNivel1:
        """Resuelve el Nivel 1 a optimalidad (referencia y cota inferior)."""
        prob, vars_ = self._construir()
        sol = self._resolver(prob, vars_)
        if sol is None:
            raise RuntimeError("El Nivel 1 resulto infactible o no se pudo resolver.")
        return sol

    def pool_perturbacion(self, n: int, sigma: float = 0.15,
                          semilla: Optional[int] = None) -> List[SolucionNivel1]:
        """POOL por PERTURBACION de costes (estrategia por defecto).

        Resuelve el optimo y, ademas, n-1 veces mas perturbando aleatoriamente
        Fijo_i y CosteO_i con ruido multiplicativo (1 +/- sigma). Cada resolucion
        da una solucion distinta, factible y de bajo coste. Barato: cada MILP del
        Nivel 1 es trivial para CBC. Devuelve soluciones unicas ordenadas por coste.
        """
        rng = random.Random(semilla)
        soluciones: List[SolucionNivel1] = [self.resolver_optimo()]
        vistas = {tuple(soluciones[0].abiertas)}

        intentos = 0
        while len(soluciones) < n and intentos < 10 * n:
            intentos += 1
            fp = {i: self.inst.Fijo[i] * (1 + rng.uniform(-sigma, sigma)) for i in self.inst.P}
            op = {i: self.inst.CosteO[i] * (1 + rng.uniform(-sigma, sigma)) for i in self.inst.P}
            prob, vars_ = self._construir(fijo_pert=fp, op_pert=op)
            sol = self._resolver(prob, vars_)
            if sol is None:
                continue
            clave = tuple(sorted(sol.abiertas)) + tuple(sorted(sol.asignacion.items()))
            if clave not in vistas:
                vistas.add(clave)
                soluciones.append(sol)
        soluciones.sort(key=lambda s: s.coste)
        return soluciones

    def pool_kbest(self, K: int) -> List[SolucionNivel1]:
        """POOL por K-BEST con cortes 'no-good' (estrategia activable).

        Obtiene las K mejores CONFIGURACIONES DE APERTURA distintas. Tras cada
        resolucion anade un corte que prohibe repetir el mismo vector y_i, de modo
        que la siguiente resolucion devuelve la mejor solucion con apertura distinta.
        Como el Nivel 1 es pequeno, K pequeno (5-10) es barato.
        """
        soluciones: List[SolucionNivel1] = []
        prob, vars_ = self._construir()
        cortes: List[pulp.LpConstraint] = []

        for _ in range(K):
            # Reconstruimos limpio cada vez y re-aplicamos todos los cortes.
            prob, vars_ = self._construir()
            sol = self._resolver(prob, vars_, extra_no_good=list(cortes))
            if sol is None:
                break
            soluciones.append(sol)
            # Corte no-good sobre y_i: prohibir exactamente este patron de apertura.
            y = vars_["y"]
            abiertas = [i for i in self.inst.P if sol.y[i] == 1]
            cerradas = [i for i in self.inst.P if sol.y[i] == 0]
            # sum_{abiertas}(1 - y) + sum_{cerradas} y >= 1
            corte = (pulp.lpSum(1 - y[i] for i in abiertas)
                     + pulp.lpSum(y[i] for i in cerradas) >= 1)
            cortes.append(corte)

        soluciones.sort(key=lambda s: s.coste)
        return soluciones

