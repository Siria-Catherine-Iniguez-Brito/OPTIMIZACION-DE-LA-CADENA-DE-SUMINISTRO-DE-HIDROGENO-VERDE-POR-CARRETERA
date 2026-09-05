"""
milp_global_exacto.py
======================

Solver EXACTO del PROBLEMA del TFM
"Optimizacion de la Cadena de Suministro de Hidrogeno Verde por Carretera".

A diferencia de nivel1_exacto.py (que resuelve solo localizacion + flujo directo
planta->cliente, sin camiones ni rutas), este modulo construye y resuelve el
MILP COMPLETO tal y como lo decodifica cromosoma.py:

  - cada camion k sale de UNA planta, visita una secuencia de clientes con UN
    modo de transporte fijo, y regresa vacio a la misma planta;
  - cada cliente se visita EXACTAMENTE una vez, por un UNICO camion;
  - la carga acumulada en cada camion no puede superar CapV_m del modo elegido;
  - no puede haber sub-rutas que no toquen ningun deposito (eliminadas via una
    variable de carga tipo Gavish-Graves, coherente con el campo "f" /
    "restante" de cromosoma.decodificar);
  - la produccion de cada planta depende del modo elegido por cada camion que
    sale de ella (perdidas de acondicionamiento 1/Efi_m), igual que en
    fitness.EvaluadorFitness.

Variables de decision
----------------------
  y[i]                binaria   : planta i abierta
  u[k, p, m]           binaria   : camion k asignado a la planta p con el modo m
  v[j, k]              binaria   : cliente j servido por el camion k
  x_pj[p, j, k, m]     binaria   : arco planta->cliente recorrido por (k, m)
  x_jp[j, p, k, m]     binaria   : arco cliente->planta (retorno) recorrido por (k, m)
  x_jj[i, j, k, m]     binaria   : arco cliente->cliente recorrido por (k, m)
  f_pj[p, j, k, m]     continua  : carga que lleva el camion en el arco p->j
  f_jj[i, j, k, m]     continua  : carga que lleva el camion en el arco i->j
  load_u[i, k, m]      continua  : carga total de la ruta de k, atribuida a la
                                   planta i y al modo m (linealizacion de
                                   u[k,i,m] * load_k para el calculo de OPEX)

El camion siempre regresa VACIO (no se modela f_jp): la carga en el arco de
retorno es 0 por construccion, igual que en cromosoma.decodificar (restante
llega a 0 tras el ultimo cliente).

Eliminacion de sub-rutas
-------------------------
Se emplea una formulacion de flujo de UN SOLO PRODUCTO: la carga se genera en el deposito
y se consume estrictamente en cada cliente visitado (balance de carga). Como
la carga solo puede originarse en un deposito y decrece monotonamente, ningun
ciclo que no toque un deposito puede sostenerse, lo cual elimina las
sub-rutas sin necesidad de restricciones MTZ adicionales.

Complejidad
-----------
El numero de variables crece con |P|*|J|*|K|*|M| (principalmente por las
variables de arco-camion-modo).

Dependencias
------------
PuLP (con CBC incluido).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pulp

from modelo import Instancia


# ---------------------------------------------------------------------------
# Estructura de la solucion
# ---------------------------------------------------------------------------
@dataclass
class SolucionGlobal:
    """Solucion (optima o mejor encontrada dentro del timeout) del MILP global.

    'tiene_solucion_factible' es True SOLO si, ademas de existir un valor
    asignado a las variables, ese valor es un INCUMBENTE ENTERO real (ver
    '_es_incumbente_entero'). Si CBC se detuvo por 'timeLimit' sin haber
    encontrado todavia ningun incumbente entero, PuLP puede dejar en las
    variables los valores de la relajacion LP del ultimo nodo explorado
    (fracciones tipo 0.35, 0.62...); esa relajacion es una COTA INFERIOR
    teorica del optimo, nunca una solucion factible del problema real, y
    NO debe reportarse como tal.
    """
    estado: str                          # "Optimal", "Not Solved", "Infeasible", ...
    objetivo: Optional[float]
    y: Dict[str, int] = field(default_factory=dict)
    abiertas: List[str] = field(default_factory=list)
    rutas: List[dict] = field(default_factory=list)   # [{"planta","modo","clientes":[...]}]
    tiempo_s: float = 0.0
    n_variables: int = 0
    n_restricciones: int = 0
    tiene_solucion_factible: bool = False

    def resumen(self) -> str:
        if not self.tiene_solucion_factible:
            return (f"[{self.estado}] SIN incumbente ENTERO factible "
                    f"(las variables, si tienen valor, son de una relajacion LP)")
        lineas = [f"[{self.estado}] objetivo = {self.objetivo}",
                  f"  abiertas = {sorted(self.abiertas)}",
                  f"  rutas activas = {len(self.rutas)}"]
        for r in self.rutas:
            lineas.append(f"    {r['planta']} [{r['modo']}] -> {r['clientes']}")
        return "\n".join(lineas)


# ---------------------------------------------------------------------------
# Construccion y resolucion del modelo
# ---------------------------------------------------------------------------
def _construir(inst: Instancia):
    P, J, K, M = list(inst.P), list(inst.J), list(inst.K), list(inst.M)

    CAPV_MAX = max(inst.modos[m].CapV for m in M)
    LOAD_MAX = max(inst.HTotal, 1.0)   # cota superior segura para la carga de una ruta

    prob = pulp.LpProblem("MILP_global_exacto_rutas", pulp.LpMinimize)

    # ---------------- Variables ----------------
    y = {i: pulp.LpVariable(f"y_{i}", cat="Binary") for i in P}

    u = {(k, p, m): pulp.LpVariable(f"u_{k}_{p}_{m}", cat="Binary")
         for k in K for p in P for m in M}

    v = {(j, k): pulp.LpVariable(f"v_{j}_{k}", cat="Binary")
         for j in J for k in K}

    x_pj = {(p, j, k, m): pulp.LpVariable(f"xpj_{p}_{j}_{k}_{m}", cat="Binary")
            for p in P for j in J for k in K for m in M}
    x_jp = {(j, p, k, m): pulp.LpVariable(f"xjp_{j}_{p}_{k}_{m}", cat="Binary")
            for j in J for p in P for k in K for m in M}
    x_jj = {(i, j, k, m): pulp.LpVariable(f"xjj_{i}_{j}_{k}_{m}", cat="Binary")
            for i in J for j in J if i != j for k in K for m in M}

    f_pj = {(p, j, k, m): pulp.LpVariable(f"fpj_{p}_{j}_{k}_{m}", lowBound=0)
            for p in P for j in J for k in K for m in M}
    f_jj = {(i, j, k, m): pulp.LpVariable(f"fjj_{i}_{j}_{k}_{m}", lowBound=0)
            for i in J for j in J if i != j for k in K for m in M}

    load_u = {(i, k, m): pulp.LpVariable(f"loadu_{i}_{k}_{m}", lowBound=0)
              for i in P for k in K for m in M}

    # Produccion horaria de cada planta (igual que en nivel1_exacto.py: D3, D4)
    q = {(i, t): pulp.LpVariable(f"q_{i}_{t}", lowBound=0)
         for i in P for t in range(inst.T)}

    # ---------------- Expresiones auxiliares ----------------
    def load_k_expr(k):
        return pulp.lpSum(inst.Dem[j] * v[(j, k)] for j in J)

    # ---------------- Objetivo ----------------
    capex = pulp.lpSum(inst.Fijo[i] * y[i] for i in P)

    opex = pulp.lpSum(
        inst.CosteO[i] * q[(i, t)]
        for i in P for t in range(inst.T)
    )

    transporte = (
        pulp.lpSum(inst.CosteT[(p, j, m)] * x_pj[(p, j, k, m)]
                   for p in P for j in J for k in K for m in M)
        + pulp.lpSum(inst.CosteT[(j, p, m)] * x_jp[(j, p, k, m)]
                     for j in J for p in P for k in K for m in M)
        + pulp.lpSum(inst.CosteT[(i, j, m)] * x_jj[(i, j, k, m)]
                     for i in J for j in J if i != j for k in K for m in M)
    )

    prob += capex + opex + transporte, "coste_total_global"

    # ---------------- Restricciones ----------------
    # (C1) Solo plantas abiertas pueden alojar camiones
    for k in K:
        for p in P:
            prob += pulp.lpSum(u[(k, p, m)] for m in M) <= y[p], f"solo_abiertas_{k}_{p}"

    # (C2) Cada camion se asigna, como mucho, a una (planta, modo)
    for k in K:
        prob += pulp.lpSum(u[(k, p, m)] for p in P for m in M) <= 1, f"un_uso_camion_{k}"


    for i in J:
        for j in J:
            if i == j:
                continue
            for k in K:
                for m in M:
                    prob += x_jj[(i, j, k, m)] <= pulp.lpSum(u[(k, p, m)] for p in P), \
                            f"modo_unico_intermedio_{i}_{j}_{k}_{m}"

    # (C3)/(C4) Grado de salida/entrada del deposito = asignacion del camion
    for p in P:
        for k in K:
            for m in M:
                prob += pulp.lpSum(x_pj[(p, j, k, m)] for j in J) == u[(k, p, m)], \
                        f"salida_deposito_{p}_{k}_{m}"
                prob += pulp.lpSum(x_jp[(j, p, k, m)] for j in J) == u[(k, p, m)], \
                        f"retorno_deposito_{p}_{k}_{m}"

    # (C5)/(C6) Grado de entrada/salida de cada cliente = si lo visita ese camion
    for j in J:
        for k in K:
            entrada = (pulp.lpSum(x_pj[(p, j, k, m)] for p in P for m in M)
                       + pulp.lpSum(x_jj[(i, j, k, m)] for i in J if i != j for m in M))
            salida = (pulp.lpSum(x_jp[(j, p, k, m)] for p in P for m in M)
                      + pulp.lpSum(x_jj[(j, i, k, m)] for i in J if i != j for m in M))
            prob += entrada == v[(j, k)], f"entrada_cliente_{j}_{k}"
            prob += salida == v[(j, k)], f"salida_cliente_{j}_{k}"

    # (C7) Cada cliente visitado exactamente una vez
    for j in J:
        prob += pulp.lpSum(v[(j, k)] for k in K) == 1, f"visita_unica_{j}"

    # (C8) Capacidad de cisterna del modo asignado
    for k in K:
        prob += load_k_expr(k) <= pulp.lpSum(inst.modos[m].CapV * u[(k, p, m)]
                                              for p in P for m in M), f"capacidad_{k}"

    # (C9) Cota de carga en arco <= CapV_MAX * uso del arco
    for p in P:
        for j in J:
            for k in K:
                for m in M:
                    prob += f_pj[(p, j, k, m)] <= CAPV_MAX * x_pj[(p, j, k, m)], \
                            f"cota_fpj_{p}_{j}_{k}_{m}"
    for i in J:
        for j in J:
            if i == j:
                continue
            for k in K:
                for m in M:
                    prob += f_jj[(i, j, k, m)] <= CAPV_MAX * x_jj[(i, j, k, m)], \
                            f"cota_fjj_{i}_{j}_{k}_{m}"

    # (C10) Balance de carga en el deposito: la carga que sale = carga total de la ruta
    for p in P:
        for k in K:
            salida_p = pulp.lpSum(f_pj[(p, j, k, m)] for j in J for m in M)
            uso_pk = pulp.lpSum(u[(k, p, m)] for m in M)
            prob += salida_p <= load_k_expr(k), f"carga_dep_sup_{p}_{k}"
            prob += salida_p >= load_k_expr(k) - LOAD_MAX * (1 - uso_pk), \
                    f"carga_dep_inf_{p}_{k}"

    # (C11) Balance de carga en cada cliente: lo que entra menos lo que sale = Dem_j (si se visita)
    for j in J:
        for k in K:
            entra = (pulp.lpSum(f_pj[(p, j, k, m)] for p in P for m in M)
                     + pulp.lpSum(f_jj[(i, j, k, m)] for i in J if i != j for m in M))
            sale = pulp.lpSum(f_jj[(j, i, k, m)] for i in J if i != j for m in M)
            prob += entra - sale == inst.Dem[j] * v[(j, k)], f"balance_carga_{j}_{k}"

    # (C12) Linealizacion: load_u[i,k,m] = load_k si u[k,i,m]=1, si no 0.
    # Se usa para el balance de masa con perdidas (D5), analogo a nivel1_exacto.py
    # pero con el modo REAL asignado a cada camion (no un modo de referencia fijo).
    for i in P:
        for k in K:
            for m in M:
                prob += load_u[(i, k, m)] <= LOAD_MAX * u[(k, i, m)], f"loadu_sup_{i}_{k}_{m}"
                prob += load_u[(i, k, m)] <= load_k_expr(k), f"loadu_leload_{i}_{k}_{m}"
                prob += load_u[(i, k, m)] >= load_k_expr(k) - LOAD_MAX * (1 - u[(k, i, m)]), \
                        f"loadu_inf_{i}_{k}_{m}"

    # (D3) Capacidad del electrolizador: q_it <= Cap_i * y_i
    for i in P:
        for t in range(inst.T):
            prob += q[(i, t)] <= inst.Cap[i] * y[i], f"electro_{i}_{t}"

    # (D4) Energia renovable disponible: q_it <= Ren_it
    for i in P:
        for t in range(inst.T):
            prob += q[(i, t)] <= inst.Ren[i][t], f"renov_{i}_{t}"

    # (D5) Balance de masa con perdidas de acondicionamiento (modo REAL de cada
    # camion, no un modo de referencia fijo como en nivel1_exacto.py):
    #   sum_t q_it == sum_k sum_m load_u[i,k,m] / Efi_m
    for i in P:
        prob += (pulp.lpSum(q[(i, t)] for t in range(inst.T))
                 == pulp.lpSum(load_u[(i, k, m)] / inst.modos[m].Efi
                               for k in K for m in M)), f"balance_masa_{i}"

    variables = {"y": y, "u": u, "v": v, "x_pj": x_pj, "x_jp": x_jp, "x_jj": x_jj,
                 "f_pj": f_pj, "f_jj": f_jj, "load_u": load_u, "q": q}
    return prob, variables


def _extraer_rutas(inst: Instancia, variables: dict) -> Tuple[Dict[str, int], List[dict]]:
    """Reconstruye y_i y la lista de rutas (planta, modo, clientes en orden) a
    partir de los arcos activos, siguiendo la cadena planta -> ... -> planta."""
    P, J, K, M = list(inst.P), list(inst.J), list(inst.K), list(inst.M)
    x_pj, x_jp, x_jj = variables["x_pj"], variables["x_jp"], variables["x_jj"]

    def val(var):
        v = var.value()
        return v is not None and v > 0.5

    y_sol = {i: 0 for i in P}
    rutas = []
    for k in K:
        # Localizar el arco de salida real (planta, modo) usado por este camion
        origen = None
        modo = None
        for p in P:
            for j0 in J:
                for m in M:
                    var = x_pj.get((p, j0, k, m))
                    if var is not None and val(var):
                        origen, modo = p, m
                        break
                if origen is not None:
                    break
            if origen is not None:
                break
        if origen is None:
            continue  # camion no usado

        y_sol[origen] = 1
        secuencia = []
        actual = origen
        visitados = set()
        # primer salto: planta -> primer cliente
        siguiente = None
        for j0 in J:
            var = x_pj.get((origen, j0, k, modo))
            if var is not None and val(var):
                siguiente = j0
                break
        while siguiente is not None and siguiente not in visitados:
            secuencia.append(siguiente)
            visitados.add(siguiente)
            actual = siguiente
            # ¿vuelve a la planta?
            var_ret = x_jp.get((actual, origen, k, modo))
            if var_ret is not None and val(var_ret):
                siguiente = None
                break
            # si no, busca el siguiente cliente
            nxt = None
            for j2 in J:
                if j2 == actual:
                    continue
                var = x_jj.get((actual, j2, k, modo))
                if var is not None and val(var):
                    nxt = j2
                    break
            siguiente = nxt

        rutas.append({"planta": origen, "modo": modo, "clientes": secuencia})

    return y_sol, rutas


def _es_incumbente_entero(variables: dict, tol: float = 1e-6) -> bool:
    """True solo si TODAS las variables binarias con valor ya asignado por el
    solver son, en efecto, enteras (0 o 1, dentro de 'tol').
    """
    familias_binarias = ("y", "u", "v", "x_pj", "x_jp", "x_jj")
    for nombre in familias_binarias:
        vars_dict = variables.get(nombre, {})
        for var in vars_dict.values():
            val = var.value()
            if val is None:
                continue
            if abs(val - round(val)) > tol:
                return False
    return True


def resolver_global(inst: Instancia, timeout: float = 300, gap: float = 0.0,
                     msg: bool = False) -> SolucionGlobal:
    """Construye y resuelve EXACTAMENTE el MILP global  para la
    instancia dada. Devuelve una SolucionGlobal con el estado, el objetivo y,
    si hubo solucion, las rutas reconstruidas.

    Se acepta como solucion (UB) cualquier incumbente ENTERO que CBC haya
    dejado, tanto si el estado es "Optimal" como si es "Not Solved"/"Undefined"
    tras agotar 'timeout'. Si las variables con valor asignado no son enteras
    (ver '_es_incumbente_entero'), se trata como si NO hubiera solucion: esos
    valores corresponden a una relajacion LP, no a una solucion factible del
    problema real, y 'tiene_solucion_factible' queda en False.

    ADVERTENCIA DE TAMANO: el numero de variables crece con
    |P|*|J|*|K|*|M| (principalmente las variables de arco-camion-modo). Para
    instancias con muchos camiones (|K| grande) puede ser conveniente acotar
    K a priori (nunca se necesitan mas camiones activos que clientes), pero
    por defecto se usa inst.K tal cual viene en el fichero de la instancia.
    """
    import time
    t0 = time.time()

    prob, variables = _construir(inst)

    solver = pulp.PULP_CBC_CMD(msg=1 if msg else 0, timeLimit=int(timeout), gapRel=gap)
    prob.solve(solver)

    estado = pulp.LpStatus.get(prob.status, str(prob.status))
    objetivo = None
    y_sol: Dict[str, int] = {}
    rutas: List[dict] = []
    tiene_sol = False

    hay_valores = any(v.value() is not None for v in variables["y"].values())
    if hay_valores and _es_incumbente_entero(variables):
        try:
            objetivo = pulp.value(prob.objective)
        except Exception:
            objetivo = None
        if objetivo is not None:
            tiene_sol = True
            y_sol, rutas = _extraer_rutas(inst, variables)

    return SolucionGlobal(
        estado=estado, objetivo=objetivo, y=y_sol,
        abiertas=[i for i, val in y_sol.items() if val == 1],
        rutas=rutas, tiempo_s=time.time() - t0,
        n_variables=len(prob.variables()), n_restricciones=len(prob.constraints),
        tiene_solucion_factible=tiene_sol,
    )
