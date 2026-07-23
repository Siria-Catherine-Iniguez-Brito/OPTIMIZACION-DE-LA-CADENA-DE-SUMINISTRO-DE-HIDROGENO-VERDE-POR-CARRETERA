"""
ga_engine.py
============

Motor del ALGORITMO GENETICO para el problema global del TFM "Optimizacion de la
Cadena de Suministro de Hidrogeno Verde por Carretera".

Orquesta las piezas de los modulos anteriores en un bucle evolutivo generacional
con reemplazo elitista:

    poblacion inicial (inicializadores, modo A/B/C)
        |
        v
    repetir hasta criterio de parada:
        evaluar            (fitness.py)
        seleccionar padres (operadores.py -> torneo)
        cruzar             (operadores.py + reparacion.py)
        mutar              (operadores.py + reparacion.py)
        reemplazar         (operadores.py -> elitismo)
        registrar convergencia
        |
        v
    devolver mejor solucion + historico de convergencia

Caracteristicas
---------------
  - Semilla aleatoria fijable en TODAS las fuentes de azar (reproducibilidad):
    reparador, operadores e inicializador comparten la misma semilla.
  - Dos criterios de parada, como en el TFG de referencia:
        * por numero de GENERACIONES (n_generaciones)
        * por TIEMPO limite en segundos (tiempo_max); si se indica, tiene prioridad.
  - Registro del historico de convergencia (mejor fitness, media y mejor LCOH por
    generacion), listo para dibujar las curvas de la memoria.
  - Elitismo: el mejor individuo nunca se pierde entre generaciones.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

from modelo import Instancia
from cromosoma import Cromosoma
from fitness import EvaluadorFitness
from reparacion import Reparador
from operadores import OperadoresGA
from inicializadores import Inicializador


@dataclass
class ConfigGA:
    """Hiperparametros y opciones de una ejecucion del GA."""
    tam_poblacion: int = 40
    n_generaciones: Optional[int] = 100      # criterio de parada por generaciones
    tiempo_max: Optional[float] = None        # criterio por tiempo (s); si se da, prima
    prob_cruce: float = 0.9
    prob_mutacion: float = 0.2
    k_torneo: int = 3
    elitismo: bool = True
    tipo_init: str = "A"                      # 'A' aleatoria | 'B' semilla N1 | 'C' mixta
    frac_semilla: float = 0.5                 # proporcion de tipo B en el modo 'C'
    semilla: Optional[int] = 42               # semilla global de reproducibilidad
    verbose: bool = False


@dataclass
class ResultadoGA:
    """Salida de una ejecucion: mejor solucion e historico de convergencia."""
    mejor: Cromosoma
    mejor_fitness: float
    mejor_lcoh: Optional[float]
    factible: bool
    generaciones: int
    tiempo_s: float
    hist_best_fitness: List[float] = field(default_factory=list)
    hist_media_fitness: List[float] = field(default_factory=list)
    hist_best_lcoh: List[Optional[float]] = field(default_factory=list)

    def resumen(self) -> str:
        lc = f"{self.mejor_lcoh:.4f} EUR/kg" if self.mejor_lcoh is not None else "-- (infactible)"
        return (f"GA: gens={self.generaciones}  t={self.tiempo_s:.2f}s  "
                f"best_fitness={self.mejor_fitness:.2f}  LCOH={lc}  factible={self.factible}")


class MotorGA:
    def __init__(self, inst: Instancia, cfg: ConfigGA, pool_n1: Optional[List] = None):
        self.inst = inst
        self.cfg = cfg
        self.pool_n1 = pool_n1
        # Todas las fuentes de azar cuelgan de la misma semilla -> reproducibilidad.
        self.reparador = Reparador(inst, semilla=cfg.semilla)
        self.evaluador = EvaluadorFitness(inst)
        self.operadores = OperadoresGA(inst, self.evaluador, self.reparador, semilla=cfg.semilla)
        self.inicializador = Inicializador(inst, self.reparador, semilla=cfg.semilla)

    def _evaluar_poblacion(self, poblacion: List[Cromosoma]):
        evals = [self.evaluador.evaluar(c) for c in poblacion]
        return evals, [e.fitness for e in evals]

    def _debe_parar(self, gen: int, t0: float) -> bool:
        if self.cfg.tiempo_max is not None:
            return (time.perf_counter() - t0) >= self.cfg.tiempo_max
        return gen >= (self.cfg.n_generaciones or 0)

    def ejecutar(self) -> ResultadoGA:
        cfg = self.cfg
        t0 = time.perf_counter()

        # Poblacion inicial segun el modo elegido (A / B / C)
        poblacion = self.inicializador.generar(
            tipo=cfg.tipo_init, tam=cfg.tam_poblacion,
            pool_n1=self.pool_n1, frac_semilla=cfg.frac_semilla,
        )
        evals, fitness = self._evaluar_poblacion(poblacion)

        hist_best, hist_media, hist_lcoh = [], [], []

        def registrar():
            bi = min(range(len(fitness)), key=lambda i: fitness[i])
            hist_best.append(fitness[bi])
            hist_media.append(sum(fitness) / len(fitness))
            hist_lcoh.append(evals[bi].lcoh)

        registrar()

        gen = 0
        while not self._debe_parar(gen, t0):
            gen += 1
            hijos: List[Cromosoma] = []
            while len(hijos) < cfg.tam_poblacion:
                pA = self.operadores.seleccion_torneo(poblacion, fitness, cfg.k_torneo)
                pB = self.operadores.seleccion_torneo(poblacion, fitness, cfg.k_torneo)
                hijo = (self.operadores.cruce(pA, pB)
                        if self.operadores.rng.random() < cfg.prob_cruce else pA)
                hijo = self.operadores.mutar(hijo, cfg.prob_mutacion)
                hijos.append(hijo)

            evals_h, fit_h = self._evaluar_poblacion(hijos)

            if cfg.elitismo:
                poblacion, fitness = self.operadores.reemplazo_elitista(
                    poblacion, fitness, hijos, fit_h)
                evals, fitness = self._evaluar_poblacion(poblacion)
            else:
                poblacion, evals, fitness = hijos, evals_h, fit_h

            registrar()

            if cfg.verbose and (gen % 10 == 0 or gen == 1):
                print(f"  gen {gen:4d} | best_fitness={hist_best[-1]:.2f} "
                      f"| media={hist_media[-1]:.2f} | best_LCOH={hist_lcoh[-1]}")

        bi = min(range(len(fitness)), key=lambda i: fitness[i])
        e = evals[bi]
        return ResultadoGA(
            mejor=poblacion[bi], mejor_fitness=e.fitness, mejor_lcoh=e.lcoh,
            factible=e.factible, generaciones=gen, tiempo_s=time.perf_counter() - t0,
            hist_best_fitness=hist_best, hist_media_fitness=hist_media,
            hist_best_lcoh=hist_lcoh,
        )
