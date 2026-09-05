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
  y las perdidas se usa un modo de REFERENCIA (por defecto el MENOS eficiente,
  Efi mas baja, y su coste_por_km), de forma que el balance de masa (D5) contemple
  las perdidas de acondicionamiento en el PEOR caso. Este criterio conservador
  hace que el Nivel 1 reserve produccion suficiente y no concentre demasiada
  demanda en pocas plantas, de modo que la semilla (y_i, z_pj) siga siendo
  factible aunque el genetico use el modo menos eficiente. El modo de referencia
  es configurable.
- El coste de transporte directo del arco (i, j) es
        costo_directo_ij = coste_por_km[m_ref] * D[i][j].
- Al deducir z_pj se asigna cada cliente a la planta que le envia MAYOR flujo
  (regla de mayoria), garantizando z_pj binaria y coherente (una planta por cliente).

Construccion del POOL de semillas
----------------------------------
Se ofrecen tres estrategias para construir el pool de soluciones distintas que
alimentan la inicializacion tipo B/C del genetico (Seccion E08_INIT / E08b_POOL):

  1. pool_perturbacion(n, sigma, semilla)
       Estrategia ORIGINAL: perturba aleatoriamente Fijo_i y CosteO_i y resuelve
       el Nivel 1 a OPTIMALIDAD en cada intento. Problema detectado empiricamente
       (Seccion E08_INIT): con sigma=0.15 el pool resultante contenia solo 2
       soluciones distintas en las tres instancias (small/medium/large),
       independientemente del numero de plantas candidatas P. La causa mas
       probable es que, en instancias donde la capacidad y la energia renovable
       disponible restringen mucho que plantas pueden cubrir la demanda, el
       subconjunto optimo de apertura es poco sensible a variaciones moderadas
       de coste: la perturbacion rara vez cambia CUAL es el y_i optimo.

  2. pool_nogood(K, ...)
       Estrategia RECOMENDADA: en lugar de esperar a que el azar cambie la
       solucion optima, se fuerza la diversidad de forma EXPLICITA mediante
       cortes 'no-good' sobre y_i (ya usados en pool_kbest), de modo que cada
       resolucion devuelve necesariamente una configuracion de apertura nunca
       vista. Ademas, como para sembrar la poblacion inicial del genetico NO
       hace falta la solucion OPTIMA de cada MILP perturbado, sino solo una
       solucion FACTIBLE de buena calidad, se relaja el gap de optimalidad del
       solver (gapRel) para acelerar cada resolucion. Combina, por tanto,
       diversidad GARANTIZADA con menor coste computacional por resolucion.

  3. pool_kbest(K)
       Las K mejores configuraciones de apertura DISTINTAS por optimalidad
       estricta (gap=0). Se mantiene por compatibilidad y como referencia sin
       aproximacion, pero es mas lenta que pool_nogood al no relajar el gap.

Dependencias
------------
PuLP (con el solver CBC incluido). Ver requirements.txt.
"""

from __future__ import annotations

import random
import time
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

    def clave_apertura(self) -> Tuple[str, ...]:
        """Clave canonica de la configuracion de apertura (para deduplicar)."""
        return tuple(sorted(self.abiertas))

    def clave_completa(self) -> Tuple:
        """Clave canonica de apertura + asignacion cliente-planta."""
        return self.clave_apertura() + tuple(sorted(self.asignacion.items()))

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
                 solver_msg: bool = False, tmp_dir: Optional[str] = None):
        self.inst = inst
        # Directorio para los ficheros temporales (.mps/.sol) que CBC lee y
        # escribe en cada resolucion. Por defecto se usa el temporal del
        # SISTEMA (normalmente /tmp, en el disco LOCAL de la maquina).

        import os
        import tempfile
        self.tmp_dir = tmp_dir or tempfile.gettempdir()
        try:
            os.makedirs(self.tmp_dir, exist_ok=True)
        except Exception:
            pass
        os.environ.setdefault("TMPDIR", self.tmp_dir)
        tempfile.tempdir = self.tmp_dir
        # Modo de referencia para coste/perdidas: por defecto el MENOS eficiente
        # (criterio CONSERVADOR). Al usar la Efi mas baja, el balance de masa (D5)
        # exige la produccion mas alta posible, de modo que el Nivel 1 reserva
        # capacidad de produccion suficiente y NO concentra demasiada demanda en
        # pocas plantas. Asi la semilla (y_i, z_pj) sigue siendo factible aunque
        # el genetico sirva las rutas con el modo menos eficiente (p. ej.
        # amoniaco).
        if modo_referencia is None:
            modo_referencia = min(inst.M, key=lambda m: inst.modos[m].Efi)
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
                  extra_no_good: Optional[List[pulp.LpConstraint]] = None,
                  gap_rel: Optional[float] = None,
                  time_limit: Optional[float] = None,
                  reintentos: int = 2,
                  espera_reintento: float = 1.5) -> Optional[SolucionNivel1]:
        """Resuelve el MILP con CBC.

        Parametros
        ----------
        extra_no_good : cortes adicionales sobre y_i (diversidad forzada).
        gap_rel       : gap relativo de optimalidad aceptado (p.ej. 0.10 = 10%).
                        Si es None, se exige el gap por defecto de CBC (~optimo).
                        Al relajarlo, CBC puede parar en cuanto encuentra una
                        solucion FACTIBLE suficientemente buena, sin demostrar
                        optimalidad: mas rapido y suficiente para sembrar el
                        genetico (no necesitamos el optimo de cada MILP
                        perturbado, solo una solucion factible de buena calidad).
        time_limit    : limite de tiempo (s) por resolucion, como salvaguarda
                        adicional cuando se usa gap_rel.
        reintentos    : numero de reintentos si CBC falla al EJECUTARSE (no si
                        el problema es infactible). Se ha observado que, en
                        entornos como Google Colab con Google Drive montado o
                        con muchas invocaciones consecutivas del binario CBC
                        (como hace pool_nogood, con hasta K resoluciones
                        seguidas), el propio proceso 'cbc' puede fallar de
                        forma transitoria (PulpSolverError: "Error while
                        executing .../cbc"), sin que el modelo tenga ningun
                        problema. Reintentar tras una breve espera basta para
                        superar la mayoria de estos fallos puntuales.
        espera_reintento : segundos de espera entre reintentos.
        """
        if extra_no_good:
            for k, c in enumerate(extra_no_good):
                prob += c, f"nogood_{k}_{id(c)}"

        # No se pasa tmpDir aqui (incompatible con algunas versiones de PuLP,
        # ver comentario en __init__); el directorio temporal ya quedo fijado
        # via tempfile.tempdir / TMPDIR al construir el SolverNivel1.
        solver_kwargs = {"msg": 1 if self.solver_msg else 0}
        if gap_rel is not None:
            solver_kwargs["gapRel"] = gap_rel
        if time_limit is not None:
            solver_kwargs["timeLimit"] = time_limit
        solver = pulp.PULP_CBC_CMD(**solver_kwargs)

        ultimo_error: Optional[Exception] = None
        for intento in range(reintentos + 1):
            try:
                prob.solve(solver)
                ultimo_error = None
                break
            except pulp.PulpSolverError as exc:
                ultimo_error = exc
                if intento < reintentos:
                    if self.solver_msg:
                        print(f"    [nivel1] CBC fallo (intento {intento + 1}/"
                              f"{reintentos + 1}): {exc}. Reintentando...")
                    time.sleep(espera_reintento)
                    continue

        if ultimo_error is not None:
            # Se agotaron los reintentos: se trata como resolucion fallida (no
            # se propaga la excepcion), para no tumbar toda una campana de
            # calibracion por un fallo puntual del binario CBC. El llamador
            # (pool_nogood/pool_perturbacion/pool_kbest) interpreta un None
            # igual que una resolucion infactible: deja de pedir mas
            # soluciones y conserva las ya obtenidas.
            if self.solver_msg:
                print(f"    [nivel1] CBC no pudo ejecutarse tras "
                      f"{reintentos + 1} intentos: {ultimo_error}")
            return None

        estado = pulp.LpStatus[prob.status]
        # Con gapRel/timeLimit, CBC puede devolver "Optimal" (para el problema
        # relajado por gap) o, en instancias mas duras, dejar una solucion
        # incumbent sin declarar "Optimal". Aceptamos cualquier estado con
        # variables ya fijadas a un valor numerico factible.
        if estado not in ("Optimal", "Not Solved", "Undefined"):
            return None
        if vars_["y"][self.inst.P[0]].value() is None:
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

    # ------------------------------------------------------------------
    # Corte 'no-good' sobre y_i: prohibe repetir exactamente una apertura
    # ------------------------------------------------------------------
    @staticmethod
    def _corte_nogood(y_vars: Dict[str, pulp.LpVariable],
                       abiertas: List[str], cerradas: List[str]) -> pulp.LpConstraint:
        # sum_{abiertas}(1 - y) + sum_{cerradas} y >= 1
        return (pulp.lpSum(1 - y_vars[i] for i in abiertas)
                + pulp.lpSum(y_vars[i] for i in cerradas) >= 1)

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
        """POOL por PERTURBACION de costes (estrategia ORIGINAL, ver docstring
        del modulo). Se mantiene por compatibilidad; en la practica se
        recomienda `pool_nogood`, que garantiza la diversidad solicitada.
        """
        rng = random.Random(semilla)
        soluciones: List[SolucionNivel1] = [self.resolver_optimo()]
        vistas = {soluciones[0].clave_completa()}

        intentos = 0
        while len(soluciones) < n and intentos < 10 * n:
            intentos += 1
            fp = {i: self.inst.Fijo[i] * (1 + rng.uniform(-sigma, sigma)) for i in self.inst.P}
            op = {i: self.inst.CosteO[i] * (1 + rng.uniform(-sigma, sigma)) for i in self.inst.P}
            prob, vars_ = self._construir(fijo_pert=fp, op_pert=op)
            sol = self._resolver(prob, vars_)
            if sol is None:
                continue
            clave = sol.clave_completa()
            if clave not in vistas:
                vistas.add(clave)
                soluciones.append(sol)
        soluciones.sort(key=lambda s: s.coste)
        return soluciones

    def pool_nogood(self, K: int, gap_rel: float = 0.10,
                    time_limit: Optional[float] = 5.0,
                    perturbar: bool = True, sigma: float = 0.15,
                    semilla: Optional[int] = None,
                    completar_repitiendo: bool = True) -> List[SolucionNivel1]:
        """POOL RECOMENDADO: diversidad GARANTIZADA + resolucion relajada.

        Combina dos ideas para resolver la falta de diversidad observada con
        `pool_perturbacion` (Seccion E08_INIT: solo 2 soluciones de 8 pedidas):

        1. Diversidad FORZADA mediante cortes 'no-good' sobre y_i: tras cada
           resolucion se prohibe explicitamente repetir esa configuracion de
           apertura exacta, de modo que la siguiente resolucion SIEMPRE
           devuelve (si existe) una apertura nunca vista. Ya no se depende de
           que una perturbacion aleatoria de costes "cambie de opinion" al
           solver.
        2. Resolucion relajada (gap_rel > 0, time_limit acotado): para sembrar
           la poblacion inicial del genetico no hace falta el OPTIMO de cada
           MILP, solo una solucion FACTIBLE de coste razonable. Relajar el gap
           de optimalidad de CBC permite obtener bastantes mas soluciones
           factibles y distintas en el mismo tiempo de computo.

        Opcionalmente (perturbar=True) se sigue perturbando Fijo_i y CosteO_i
        en cada intento, para que ademas de la apertura tambien varien algo
        los flujos/asignacion entre soluciones con la misma apertura previa
        prohibida; no es indispensable, pues el corte no-good ya garantiza
        aperturas distintas, pero anade variedad adicional sin coste extra.

        Parametros
        ----------
        K          : numero de soluciones (configuraciones de apertura)
                     distintas deseadas.
        gap_rel    : gap relativo de optimalidad aceptado en cada resolucion
                     (por defecto 10%): basta con soluciones factibles buenas,
                     no optimas.
        time_limit : limite de tiempo (s) por resolucion individual, como
                     salvaguarda adicional en instancias grandes.
        perturbar  : si True, perturba Fijo_i/CosteO_i en cada intento (no
                     afecta a la garantia de diversidad, que viene del corte).
        sigma      : magnitud de la perturbacion (si perturbar=True).
        semilla    : semilla del generador aleatorio, para reproducibilidad.

        completar_repitiendo : si True (por defecto) y el espacio combinatorio
                     de aperturas se agota antes de alcanzar K soluciones
                     DISTINTAS (caso observado, por ejemplo, en instancias con
                     pocas plantas candidatas y demanda ajustada, donde solo
                     existe una apertura factible bajo el criterio conservador
                     de Efi_ref), se completa el resto del pool repitiendo
                     ciclicamente las soluciones YA encontradas (empezando por
                     la de menor coste) hasta alcanzar K elementos en total.
                     Si False, se devuelve el pool tal cual, con menos de K
                     elementos si la diversidad real no llega a K.
                     NOTA: `Inicializador.poblacion_semilla` (inicializadores.py)
                     ya cicla por el pool con `pool_n1[k % len(pool_n1)]` al
                     construir la poblacion del GA, por lo que un pool corto no
                     rompe la inicializacion tipo B/C; completar aqui sirve
                     sobre todo para que el TAMAÑO del pool (y las metricas que
                     se reportan sobre el, como en E08b_POOL) sean consistentes
                     con pool_n, y para dejar constancia explicita en el log de
                     cuantas soluciones son realmente distintas.

        Devuelve
        --------
        Lista de SolucionNivel1 de longitud K (si completar_repitiendo=True y
        se encontro al menos 1 solucion) o de longitud <= K (si
        completar_repitiendo=False). Las primeras `n_distintas` (ver mensaje
        de log) tienen aperturas y_i TODAS DISTINTAS entre si, ordenadas por
        coste; el resto, si las hay, son repeticiones de esas mismas
        soluciones para completar K.
        """
        rng = random.Random(semilla)
        soluciones: List[SolucionNivel1] = []
        # IMPORTANTE: se guardan solo los DATOS de cada apertura ya vista
        # (listas de plantas, no objetos LpConstraint/LpVariable). Cada llamada
        # a self._construir() crea variables y_i NUEVAS (nuevos objetos Python,
        # aunque con el mismo nombre de texto); reutilizar un corte construido
        # con las variables de una iteracion ANTERIOR sobre el problema NUEVO
        # mezclaria variables de dos problemas distintos que comparten nombre,
        # lo que corrompe el modelo (columnas duplicadas) y provocaba, segun el
        # caso, que CBC fallase al ejecutarse o que la resolucion saliera
        # infactible de forma espuria tras la primera solucion. Por eso el
        # corte de cada apertura ya vista se RECONSTRUYE en cada iteracion
        # usando las variables y_i del problema RECIEN construido.
        aperturas_vistas: List[Tuple[List[str], List[str]]] = []

        for _ in range(K):
            if perturbar:
                fp = {i: self.inst.Fijo[i] * (1 + rng.uniform(-sigma, sigma)) for i in self.inst.P}
                op = {i: self.inst.CosteO[i] * (1 + rng.uniform(-sigma, sigma)) for i in self.inst.P}
            else:
                fp = op = None

            prob, vars_ = self._construir(fijo_pert=fp, op_pert=op)
            y = vars_["y"]
            for k, (abiertas_prev, cerradas_prev) in enumerate(aperturas_vistas):
                corte = self._corte_nogood(y, abiertas_prev, cerradas_prev)
                prob += corte, f"nogood_{k}"

            sol = self._resolver(prob, vars_, gap_rel=gap_rel, time_limit=time_limit)
            if sol is None:
                # No hay (mas) aperturas factibles distintas de las ya usadas:
                # el espacio combinatorio de aperturas se ha agotado (o fallo
                # la resolucion tras los reintentos de _resolver).
                break

            soluciones.append(sol)
            abiertas = [i for i in self.inst.P if sol.y[i] == 1]
            cerradas = [i for i in self.inst.P if sol.y[i] == 0]
            aperturas_vistas.append((abiertas, cerradas))

        soluciones.sort(key=lambda s: s.coste)
        n_distintas = len(soluciones)

        if n_distintas < K:
            if self.solver_msg:
                print(f"    [nivel1] pool_nogood: se obtuvieron {n_distintas}/{K} "
                      f"soluciones DISTINTAS (espacio de aperturas agotado o "
                      f"fallo de resolucion tras los reintentos).")
            if completar_repitiendo and n_distintas > 0:
                # Se completa ciclando por las soluciones ya encontradas,
                # empezando por la de menor coste (indice 0 tras el sort).
                faltan = K - n_distintas
                for k in range(faltan):
                    soluciones.append(soluciones[k % n_distintas])
                if self.solver_msg:
                    print(f"    [nivel1] pool_nogood: pool completado a {len(soluciones)}/{K} "
                          f"repitiendo ciclicamente las {n_distintas} soluciones distintas "
                          f"(la instancia no admite mas diversidad de apertura bajo "
                          f"m_ref={self.m_ref}).")

        return soluciones

    def pool_kbest(self, K: int) -> List[SolucionNivel1]:
        """POOL por K-BEST con cortes 'no-good' a OPTIMALIDAD estricta.

        Obtiene las K mejores CONFIGURACIONES DE APERTURA distintas, sin
        relajar el gap de optimalidad (cada resolucion es exacta). Se
        mantiene como referencia sin aproximacion; para sembrar el genetico
        se recomienda `pool_nogood`, mas rapida al aceptar soluciones solo
        factibles (no necesariamente optimas) en cada paso.
        """
        soluciones: List[SolucionNivel1] = []
        # Mismo cuidado que en pool_nogood: se guardan solo los DATOS de cada
        # apertura ya vista, y el corte se reconstruye en cada iteracion con
        # las variables y_i del problema recien construido (ver comentario
        # detallado en pool_nogood).
        aperturas_vistas: List[Tuple[List[str], List[str]]] = []

        for _ in range(K):
            # Reconstruimos limpio cada vez y re-aplicamos todos los cortes.
            prob, vars_ = self._construir()
            y = vars_["y"]
            for k, (abiertas_prev, cerradas_prev) in enumerate(aperturas_vistas):
                corte = self._corte_nogood(y, abiertas_prev, cerradas_prev)
                prob += corte, f"nogood_{k}"

            sol = self._resolver(prob, vars_)
            if sol is None:
                break
            soluciones.append(sol)
            abiertas = [i for i in self.inst.P if sol.y[i] == 1]
            cerradas = [i for i in self.inst.P if sol.y[i] == 0]
            aperturas_vistas.append((abiertas, cerradas))

        soluciones.sort(key=lambda s: s.coste)
        return soluciones
