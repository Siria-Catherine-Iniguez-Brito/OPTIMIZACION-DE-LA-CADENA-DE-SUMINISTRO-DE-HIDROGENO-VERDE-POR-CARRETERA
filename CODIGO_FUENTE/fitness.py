"""
fitness.py
==========

Evaluacion de una solucion (cromosoma) del problema global del TFM "Optimizacion
de la Cadena de Suministro de Hidrogeno Verde por Carretera".

La funcion de FITNESS combina dos terminos (enfoque hibrido acordado):

    fitness(x) = COSTE_TOTAL(x)  +  PENALIZACION(x)

donde COSTE_TOTAL es el numerador del LCOH del modelo:

    CAPEX  = sum_i Fijo_i * y_i
    OPEX   = sum_i CosteO_i * (sum_t q_it),  con  sum_t q_it = sum_j sum_m f_ij^m / Efi_m
    transp = sum_k sum_m sum_(i,j) CosteT_ij^m * x_ijk^m

y PENALIZACION castiga (de forma GRADUADA, proporcional a la magnitud de la
violacion) las infactibilidades que la codificacion por rutas no evita por
construccion:

    - visita unica     : clientes repetidos o no atendidos.
    - capacidad cisterna: kg de exceso de carga sobre CapV_m en una ruta.
    - numero de camiones: rutas activas por encima de |K|.
    - capacidad planta  : produccion necesaria por encima del maximo diario factible.

Las cuatro restricciones ESTRUCTURALES (retorno al deposito, deposito unico, modo
unico por camion y ausencia de sub-rutas) las garantiza la propia codificacion
(cromosoma.py) y no necesitan penalizacion.

El indicador economico LCOH (EUR/kg) se calcula A POSTERIORI dividiendo el coste
total entre HTotal, y SOLO se reporta para soluciones factibles (en las infactibles
carece de sentido y se devuelve None).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

from modelo import Instancia
from cromosoma import Cromosoma


@dataclass
class Evaluacion:
    """Resultado de evaluar un cromosoma."""
    coste_total: float                 # numerador del LCOH (CAPEX + OPEX + transporte)
    capex: float
    opex: float
    transporte: float
    penalizacion: float                # suma de penalizaciones por infactibilidad
    fitness: float                     # coste_total + penalizacion (lo que minimiza el GA)
    factible: bool
    lcoh: Optional[float]              # coste_total / HTotal si es factible; None si no
    detalle_infactibilidad: Dict[str, float] = field(default_factory=dict)
    produccion_por_planta: Dict[str, float] = field(default_factory=dict)  # sum_t q_it

    def resumen(self) -> str:
        estado = "FACTIBLE" if self.factible else "INFACTIBLE"
        lc = f"{self.lcoh:.4f} EUR/kg" if self.lcoh is not None else "-- (infactible)"
        s = (f"[{estado}] fitness={self.fitness:.2f} | coste={self.coste_total:.2f} "
             f"(CAPEX={self.capex:.2f}, OPEX={self.opex:.2f}, T={self.transporte:.2f}) "
             f"| penal={self.penalizacion:.2f} | LCOH={lc}")
        if not self.factible:
            det = ", ".join(f"{k}={v:g}" for k, v in self.detalle_infactibilidad.items() if v)
            s += f"\n   Infactibilidades: {det}"
        return s


class EvaluadorFitness:
    """Calcula el fitness de un cromosoma segun el modelo global."""

    def __init__(self, inst: Instancia,
                 w_visita: float = 1e5, w_capacidad: float = 1e4,
                 w_camiones: float = 1e5, w_produccion: float = 1e4):
        self.inst = inst
        # Pesos de penalizacion: grandes frente al coste tipico para dominar el
        # fitness, de modo que cualquier solucion factible sea preferible a una
        # infactible, y proporcionales a la magnitud de cada violacion.
        self.w_visita = w_visita
        self.w_capacidad = w_capacidad
        self.w_camiones = w_camiones
        self.w_produccion = w_produccion

    def _produccion_diaria_max(self, i: str) -> float:
        """Cota superior de produccion diaria de la planta i que respeta las
        restricciones del modelo:  q_it <= Cap_i  y  q_it <= Ren_it.  Es decir,
        sum_t min(Cap_i, Ren_it)."""
        return sum(min(self.inst.Cap[i], self.inst.Ren[i][t]) for t in range(self.inst.T))

    def evaluar(self, cromo: Cromosoma) -> Evaluacion:
        inst = self.inst
        dec = cromo.decodificar(inst)
        y, x, f = dec["y"], dec["x"], dec["f"]

        # ---------------- COSTE TOTAL ----------------
        # CAPEX: coste fijo de las plantas abiertas.
        capex = sum(inst.Fijo[i] * y[i] for i in inst.P)

        # Transporte: suma de CosteT sobre los arcos efectivamente recorridos.
        transporte = 0.0
        for (i, j, k, m) in x:
            transporte += inst.CosteT[(i, j, m)]

        # Produccion necesaria por planta (balance de masa con perdidas):
        # la planta i debe producir sum_j sum_m f_ij^m / Efi_m. Sumamos el flujo
        # que ABANDONA cada planta por sus arcos de salida, dividido por Efi_m.
        produccion = {i: 0.0 for i in inst.P}
        for (i, j, m), val in f.items():
            if i in inst.P:                       # arco que sale de una planta
                produccion[i] += val / inst.modos[m].Efi
        opex = sum(inst.CosteO[i] * produccion[i] for i in inst.P)

        coste_total = capex + opex + transporte

        # ---------------- PENALIZACIONES ----------------
        penal = 0.0
        detalle: Dict[str, float] = {}

        # 1) Visita unica: clientes repetidos o sin servir.
        repetidos = cromo.clientes_repetidos()
        sin_servir = cromo.clientes_sin_servir(inst)
        v_visita = len(repetidos) + len(sin_servir)
        if v_visita:
            penal += self.w_visita * v_visita
            detalle["visita"] = v_visita

        # 2) Capacidad de cisterna: kg de exceso sobre CapV_m, sumados.
        exceso_cap = 0.0
        for r in cromo.rutas_sobrecargadas(inst):
            exceso_cap += r.carga(inst) - inst.modos[r.modo].CapV
        if exceso_cap > 1e-6:
            penal += self.w_capacidad * exceso_cap
            detalle["capacidad_kg"] = round(exceso_cap, 3)

        # 3) Numero de camiones por encima de |K|.
        exceso_cam = max(0, cromo.n_camiones() - len(inst.K))
        if exceso_cam:
            penal += self.w_camiones * exceso_cam
            detalle["camiones"] = exceso_cam

        # 4) Capacidad de produccion: produccion necesaria por encima del maximo.
        exceso_prod = 0.0
        for i in inst.P:
            if y[i] == 1:
                pmax = self._produccion_diaria_max(i)
                if produccion[i] > pmax + 1e-6:
                    exceso_prod += produccion[i] - pmax
        if exceso_prod > 1e-6:
            penal += self.w_produccion * exceso_prod
            detalle["produccion_kg"] = round(exceso_prod, 3)

        factible = (penal == 0.0)
        fitness = coste_total + penal
        lcoh = (coste_total / inst.HTotal) if factible else None

        return Evaluacion(
            coste_total=coste_total, capex=capex, opex=opex, transporte=transporte,
            penalizacion=penal, fitness=fitness, factible=factible, lcoh=lcoh,
            detalle_infactibilidad=detalle, produccion_por_planta=produccion,
        )
