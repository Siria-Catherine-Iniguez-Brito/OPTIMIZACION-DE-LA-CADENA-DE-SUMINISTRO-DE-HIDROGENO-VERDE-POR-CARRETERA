"""
reparacion.py
=============

Reparadores del enfoque HIBRIDO de tratamiento de la infactibilidad. Corrigen, de
forma barata y segura, las infactibilidades del ruteo de un cromosoma ANTES de
evaluarlo, dejando a la penalizacion del fitness (fitness.py) solo aquello que no
se puede o no conviene reparar. Asi la poblacion se mantiene mayoritariamente
factible sin renunciar a explorar el espacio de busqueda.

Reparaciones aplicadas, en este orden:

  1) Visita unica - clientes repetidos:
     se conserva la primera aparicion de cada cliente y se eliminan las demas.
  2) Capacidad de cisterna:
     las rutas cuya carga excede CapV_m se PARTEN (split) en varias rutas que la
     respeten, conservando el orden de visita.
  3) Visita unica - clientes sin servir:
     cada cliente no atendido se inserta en la ruta con hueco de capacidad y menor
     COSTE DE INSERCION; si ninguna ruta tiene hueco, se crea una ruta nueva (si
     quedan camiones libres) o, en ultimo caso, se anade a la menos cargada.
  4) Limite de camiones |K|:
     si hay mas rutas activas que camiones, se FUSIONAN rutas de la misma planta y
     modo mientras la carga combinada quepa en la cisterna. El exceso que no se
     pueda fusionar lo penaliza el fitness.

Todos los reparadores preservan las cuatro restricciones ESTRUCTURALES de la
codificacion (retorno al deposito de origen, deposito unico por camion, modo unico
por camion y ausencia de sub-rutas), pues operan siempre sobre rutas completas.
"""

from __future__ import annotations

import random
from typing import List, Optional

from modelo import Instancia
from cromosoma import Cromosoma, Ruta


class Reparador:
    def __init__(self, inst: Instancia, semilla: Optional[int] = None):
        self.inst = inst
        self.rng = random.Random(semilla)

    # ------------------------------------------------------------------
    # 1) Eliminar clientes repetidos (conservar la primera aparicion)
    # ------------------------------------------------------------------
    def _quitar_repetidos(self, cromo: Cromosoma) -> None:
        vistos = set()
        for r in cromo.rutas:
            nuevos = []
            for j in r.clientes:
                if j not in vistos:
                    vistos.add(j)
                    nuevos.append(j)
            r.clientes = nuevos

    # ------------------------------------------------------------------
    # Coste incremental de insertar el cliente j en la posicion 'pos' de r
    # ------------------------------------------------------------------
    def _coste_insercion(self, r: Ruta, j: str, pos: int) -> float:
        inst = self.inst
        m = r.modo
        secuencia = [r.planta] + list(r.clientes) + [r.planta]
        a, b = secuencia[pos], secuencia[pos + 1]   # arco a -> j -> b
        return inst.CosteT[(a, j, m)] + inst.CosteT[(j, b, m)] - inst.CosteT[(a, b, m)]

    # ------------------------------------------------------------------
    # 3) Insertar clientes sin servir (mejor insercion)
    # ------------------------------------------------------------------
    def _insertar_sin_servir(self, cromo: Cromosoma) -> None:
        inst = self.inst
        for j in cromo.clientes_sin_servir(inst):
            mejor = None   # (coste, ruta, pos)
            for r in cromo.rutas_activas():
                if r.carga(inst) + inst.Dem[j] <= inst.modos[r.modo].CapV + 1e-9:
                    for pos in range(len(r.clientes) + 1):
                        c = self._coste_insercion(r, j, pos)
                        if mejor is None or c < mejor[0]:
                            mejor = (c, r, pos)
            if mejor is not None:
                _, r, pos = mejor
                r.clientes.insert(pos, j)
            elif cromo.n_camiones() < len(inst.K):
                # crear ruta nueva desde la planta mas barata en transporte
                p = min(inst.P, key=lambda p: inst.CosteT[(p, j, inst.M[0])])
                m = min(inst.M, key=lambda m: inst.modos[m].coste_por_km)
                cromo.rutas.append(Ruta(p, m, [j]))
            else:
                # sin camiones libres: a la ruta menos cargada (lo penaliza fitness)
                r = min(cromo.rutas_activas(), key=lambda r: r.carga(inst))
                r.clientes.append(j)

    # ------------------------------------------------------------------
    # 2) Partir rutas que exceden la capacidad de cisterna CapV_m
    # ------------------------------------------------------------------
    def _partir_sobrecargadas(self, cromo: Cromosoma) -> None:
        inst = self.inst
        nuevas: List[Ruta] = []
        for r in cromo.rutas:
            if r.vacia():
                continue
            cap = inst.modos[r.modo].CapV
            if r.carga(inst) <= cap + 1e-9:
                nuevas.append(r)
                continue
            # first-fit conservando el orden de visita
            actual = Ruta(r.planta, r.modo, [])
            carga = 0.0
            for j in r.clientes:
                d = inst.Dem[j]
                if carga + d > cap + 1e-9 and actual.clientes:
                    nuevas.append(actual)
                    actual = Ruta(r.planta, r.modo, [])
                    carga = 0.0
                actual.clientes.append(j)
                carga += d
            if actual.clientes:
                nuevas.append(actual)
        cromo.rutas = nuevas

    # ------------------------------------------------------------------
    # 4) Fusionar rutas si hay mas camiones activos que |K|
    # ------------------------------------------------------------------
    def _fusionar_exceso(self, cromo: Cromosoma) -> None:
        inst = self.inst
        while cromo.n_camiones() > len(inst.K):
            activas = cromo.rutas_activas()
            fusion_hecha = False
            for a in range(len(activas)):
                for b in range(a + 1, len(activas)):
                    ra, rb = activas[a], activas[b]
                    if (ra.planta == rb.planta and ra.modo == rb.modo
                            and ra.carga(inst) + rb.carga(inst) <= inst.modos[ra.modo].CapV + 1e-9):
                        ra.clientes += rb.clientes
                        cromo.rutas.remove(rb)
                        fusion_hecha = True
                        break
                if fusion_hecha:
                    break
            if not fusion_hecha:
                break   # no se puede fusionar mas; el exceso lo penaliza el fitness

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------
    def reparar(self, cromo: Cromosoma) -> Cromosoma:
        """Devuelve una COPIA reparada del cromosoma."""
        c = cromo.copiar()
        self._quitar_repetidos(c)
        self._partir_sobrecargadas(c)
        self._insertar_sin_servir(c)
        self._partir_sobrecargadas(c)     # por si una insercion desbordo una ruta
        self._fusionar_exceso(c)
        c.rutas = [r for r in c.rutas if not r.vacia()]
        return c

