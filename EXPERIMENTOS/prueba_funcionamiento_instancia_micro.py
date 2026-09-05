"""
prueba_funcionamiento_instancia_micro.py
=========================================

Pipeline de verificaciondel algoritmo genetico frente al MILP global EXACTO
para una sintetica instancia micro.

Que hace, en orden:
  1. Configura rutas (repositorio + instancia) y el experimento.
  2. Importa los modulos necesarios del repositorio: modelo, cromosoma,
     fitness, ga_engine y milp_global_exacto.
  3. Carga la instancia con modelo.Instancia.desde_json(...).
  4. Resuelve el MILP global EXACTO con rutas (milp_global_exacto.resolver_global).
  5. Ejecuta UNA VEZ el algoritmo genetico (MotorGA) con poblacion inicial
     aleatoria.
  6. Muestra AMBAS soluciones de forma interpretable: plantas abiertas,
     rutas, modo de transporte y clientes visitados en orden.
  7. Compara el coste exacto vs el del GA (gap %) y concluye si el GA
     encontro una solucion factible.

"""

from __future__ import annotations

import os
import sys
import io
import json
import time
import random
import traceback
import datetime
import platform

# =========================================================================
# CONFIGURACION — 
# =========================================================================
CONFIG = {
    # --- Rutas locales -----------------------------------------------
    # RUTA_REPO: carpeta donde estan modelo.py, cromosoma.py, fitness.py,
    #            ga_engine.py y milp_global_exacto.py.
    "RUTA_REPO":        "/TFM/CODIGO_FUENTE",

    # RUTA_INSTANCIA: fichero JSON de la instancia a resolver.
    "RUTA_INSTANCIA":   "/TFM/DATOS/tablas/instancia_micro.json",

    # DIR_EXPERIMENTO: subcarpeta donde se guardan logs y RESULTADOS_VerificacionMicro.
    # de este experimento
    "DIR_EXPERIMENTO":  os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "PruebaFuncionamientoInstanciaMicro"
    ),

    # --- Determinismo ---------------------------------------------------
    "SEMILLA":          123,

    # --- MILP exacto ------------------------------------------------
    "TIMEOUT_MILP":     300,     # segundos
    "MIP_GAP":          0.0,     # 0.0 = exacto

    # --- Algoritmo genetico (ConfigGA) -------------------------------
    "GA": {
    "tam_poblacion":   100,      
    "n_generaciones":  150,      
    "prob_cruce":      0.6,      
    "prob_mutacion":   0.1,      
    "k_torneo":        2,        
    "tipo_init":       "A",      
    "elitismo":        2,
    "semilla":         123,
    "verbose":         False,
    },

    "MOSTRAR_TRACEBACKS": True,
}


# =========================================================================
# UTILIDADES DE LOG 
# =========================================================================
_BUFFER_LOG = io.StringIO()
TRACEBACKS: list = []


def LOG(*args):
    msg = " ".join(str(a) for a in args)
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    linea = f"[{ts}] {msg}"
    print(linea)
    _BUFFER_LOG.write(linea + "\n")


def SEC(titulo):
    barra = "=" * 78
    print(barra)
    print(titulo)
    print(barra)
    _BUFFER_LOG.write(barra + "\n" + titulo + "\n" + barra + "\n")


def CAPTURAR(etapa, exc):
    tb = traceback.format_exc()
    TRACEBACKS.append({"etapa": etapa, "excepcion": repr(exc), "traceback": tb})
    LOG(f"[ERROR] {etapa}: {exc!r}")
    if CONFIG["MOSTRAR_TRACEBACKS"]:
        print(tb)
        _BUFFER_LOG.write(tb + "\n")


def guardar_json(obj, ruta):
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, default=str)


# =========================================================================
# PASO 1 — CONFIGURACION
# =========================================================================
def paso1_configuracion():
    SEC("PASO 1 — CONFIGURACION")
    LOG("Python:", platform.python_version())
    LOG("Semilla global:", CONFIG["SEMILLA"])
    for k, v in CONFIG.items():
        if k != "GA":
            LOG(f"  CONFIG[{k}] = {v}")
    LOG("  CONFIG[GA] =", json.dumps(CONFIG["GA"], ensure_ascii=False))

    random.seed(CONFIG["SEMILLA"])
    try:
        import numpy as _np
        _np.random.seed(CONFIG["SEMILLA"] % (2**32 - 1))
    except Exception:
        pass

    dir_exp = CONFIG["DIR_EXPERIMENTO"]
    os.makedirs(dir_exp, exist_ok=True)
    os.makedirs(os.path.join(dir_exp, "RESULTADOS_VerificacionMicro"), exist_ok=True)
    os.makedirs(os.path.join(dir_exp, "logs"), exist_ok=True)
    LOG("Directorio de experimento (local):", dir_exp)


# =========================================================================
# PASO 2 — IMPORTACION DE MODULOS DEL REPOSITORIO
# =========================================================================
def paso2_importar_modulos():
    SEC("PASO 2 — IMPORTACION DE MODULOS")

    ruta_repo = CONFIG["RUTA_REPO"]

    if not os.path.isdir(ruta_repo):
        LOG("[ERROR] RUTA_REPO no existe:", ruta_repo)
        LOG("  Edita CONFIG['RUTA_REPO'] al principio del script.")
    elif ruta_repo not in sys.path:
        sys.path.insert(0, ruta_repo)
        LOG("sys.path += ", ruta_repo)

    if os.path.isdir(ruta_repo):
        LOG("Contenido del repo:", sorted(os.listdir(ruta_repo))[:40])

    mod = {}

    def importar(nombre):
        try:
            m = __import__(nombre, fromlist=["*"])
            mod[nombre] = m
            LOG(f"  OK  import {nombre}  ->  {getattr(m, '__file__', '?')}")
            return m
        except Exception as e:
            LOG(f"  --  fallo import {nombre}: {e.__class__.__name__}: {e}")
            mod[nombre] = None
            return None

    modelo = importar("modelo")
    cromosoma_mod = importar("cromosoma")
    fitness = importar("fitness")
    ga_engine = importar("ga_engine")
    milp_global_exacto = importar("milp_global_exacto")

    faltantes = [k for k, v in mod.items() if v is None]
    if faltantes:
        LOG("[AVISO] Modulos NO importados:", faltantes)
    else:
        LOG("Todos los modulos necesarios se importaron correctamente.")

    return modelo, cromosoma_mod, fitness, ga_engine, milp_global_exacto


# =========================================================================
# PASO 3 — CARGA DE LA INSTANCIA
# =========================================================================
def paso3_cargar_instancia(modelo):
    SEC("PASO 3 — INSTANCIA")

    ruta_inst = CONFIG["RUTA_INSTANCIA"]
    ruta_repo = CONFIG["RUTA_REPO"]

    if not os.path.isfile(ruta_inst):
        LOG("[AVISO] No existe la ruta indicada. Buscando '*.json' bajo el repo...")
        encontrados = []
        for raiz, _dirs, ficheros in os.walk(ruta_repo if os.path.isdir(ruta_repo) else "."):
            for f in ficheros:
                if f.endswith(".json") and "instancia" in f.lower():
                    encontrados.append(os.path.join(raiz, f))
        encontrados.sort()
        LOG("  Candidatos:", encontrados[:10])
        if encontrados:
            ruta_inst = encontrados[0]
            LOG("  Usando:", ruta_inst)

    inst = None
    try:
        inst = modelo.Instancia.desde_json(ruta_inst)
        LOG("Instancia cargada desde:", ruta_inst)
        print(inst.resumen())
        LOG("  P =", list(inst.P))
        LOG("  J =", list(inst.J))
        LOG("  K =", list(inst.K))
        LOG("  M =", list(inst.M))
    except Exception as e:
        CAPTURAR("cargar_instancia", e)

    dir_exp = CONFIG["DIR_EXPERIMENTO"]
    guardar_json(
        {
            "ruta_instancia": ruta_inst,
            "P": list(inst.P) if inst else [],
            "J": list(inst.J) if inst else [],
            "K": list(inst.K) if inst else [],
            "M": list(inst.M) if inst else [],
        },
        os.path.join(dir_exp, "RESULTADOS_VerificacionMicro", "instancia.json"),
    )
    return inst


# =========================================================================
# PASO 4 — RESOLUCION DEL MILP GLOBAL EXACTO
# =========================================================================
def paso4_milp_exacto(inst, milp_global_exacto):
    SEC("PASO 4 — MILP GLOBAL EXACTO")

    sol_exacta = None
    milp_ok = False

    if inst is None:
        LOG("[ERROR] Sin instancia cargada.")
    elif milp_global_exacto is not None and hasattr(milp_global_exacto, "resolver_global"):
        try:
            t0 = time.time()
            res = milp_global_exacto.resolver_global(
                inst, timeout=CONFIG["TIMEOUT_MILP"], gap=CONFIG["MIP_GAP"]
            )
            dt = time.time() - t0
            if getattr(res, "estado", None) == "Optimal":
                sol_exacta = {
                    "objetivo": res.objetivo,
                    "abiertas": list(res.abiertas),
                    "rutas": list(res.rutas),
                    "tiempo_s": dt,
                }
                milp_ok = True
                LOG(f"MILP global resuelto en {dt:.2f}s. Objetivo = {res.objetivo:.4f}")
            else:
                LOG(f"[AVISO] MILP global no optimo (estado={getattr(res, 'estado', '?')}).")
        except Exception as e:
            CAPTURAR("milp_global_exacto.resolver_global", e)
    else:
        LOG("[AVISO] milp_global_exacto no disponible en el repo: se omite el MILP exacto.")
        LOG("  Copia milp_global_exacto.py junto a modelo.py para activarlo.")

    dir_exp = CONFIG["DIR_EXPERIMENTO"]
    guardar_json(
        {
            "ok": milp_ok,
            "objetivo": (sol_exacta or {}).get("objetivo"),
            "abiertas": (sol_exacta or {}).get("abiertas"),
            "rutas": (sol_exacta or {}).get("rutas"),
        },
        os.path.join(dir_exp, "RESULTADOS_VerificacionMicro", "solucion_exacta.json"),
    )
    return sol_exacta


# =========================================================================
# PASO 5 — EJECUCION DEL ALGORITMO GENETICO 
# =========================================================================
def paso5_algoritmo_genetico(inst, fitness, ga_engine):
    SEC("PASO 5 — ALGORITMO GENETICO")

    eval_ = None
    if fitness is not None:
        ev_cls = getattr(fitness, "EvaluadorFitness", None)
        if ev_cls is not None:
            try:
                eval_ = ev_cls(inst)
                LOG("EvaluadorFitness instanciado.")
            except Exception as e:
                CAPTURAR("EvaluadorFitness", e)

    def evaluar(cromo):
        if eval_ is None or cromo is None:
            return None, None
        try:
            r = eval_.evaluar(cromo)
            return getattr(r, "fitness", None), getattr(r, "factible", None)
        except Exception as e:
            CAPTURAR("evaluar_cromosoma", e)
            return None, None

    resultado_ga = None

    if ga_engine is None or inst is None:
        LOG("[ERROR] No se puede ejecutar el GA (falta ga_engine o la instancia).")
    else:
        try:
            cfg = ga_engine.ConfigGA(
                tam_poblacion=CONFIG["GA"]["tam_poblacion"],      # <-- AÑADIDO
                n_generaciones=CONFIG["GA"]["n_generaciones"],
                prob_cruce=CONFIG["GA"]["prob_cruce"],            # <-- AÑADIDO
                prob_mutacion=CONFIG["GA"]["prob_mutacion"],      # <-- AÑADIDO
                k_torneo=CONFIG["GA"]["k_torneo"],                # <-- AÑADIDO
                elitismo=CONFIG["GA"]["elitismo"],
                tipo_init="A",
                semilla=CONFIG["SEMILLA"],
                verbose=CONFIG["GA"]["verbose"],
            )
            motor = ga_engine.MotorGA(inst, cfg, None)
            t0 = time.time()
            res = motor.ejecutar()
            dt = time.time() - t0

            mejor = getattr(res, "mejor", None)
            fit_val, factible = evaluar(mejor)
            if fit_val is None:
                fit_val = getattr(res, "mejor_fitness", None)
            if factible is None:
                factible = getattr(res, "factible", None)

            resultado_ga = {
                "fitness": fit_val,
                "factible": factible,
                "tiempo_s": dt,
                "mejor": mejor,
            }
            LOG(f"GA terminado en {dt:.2f}s | fitness = {fit_val}  |  factible = {factible}")
        except Exception as e:
            CAPTURAR("GA", e)

    if resultado_ga:
        dir_exp = CONFIG["DIR_EXPERIMENTO"]
        guardar_json(
            {
                "fitness": resultado_ga["fitness"],
                "factible": resultado_ga["factible"],
                "tiempo_s": resultado_ga["tiempo_s"],
            },
            os.path.join(dir_exp, "RESULTADOS_VerificacionMicro", "resultado_ga.json"),
        )

    return resultado_ga, eval_
# =========================================================================
# PASO 6 — DETALLES AMBAS SOLUCIONES
# =========================================================================
def paso6_detalle_soluciones(inst, sol_exacta, resultado_ga):
    SEC("PASO 6 — DETALLE DE LAS SOLUCIONES")

    def mostrar_rutas_exactas(sol):
        if not sol:
            LOG("  [MILP exacto] Sin solucion.")
            return
        LOG(
            f"  [MILP exacto] Plantas abiertas: {sorted(sol['abiertas'])}  |  "
            f"Camiones activos: {len(sol['rutas'])}"
        )
        for idx, r in enumerate(sol["rutas"], start=1):
            recorrido = " -> ".join([r["planta"]] + list(r["clientes"]) + [r["planta"]])
            LOG(f"    Camion {idx:2d} [{r['modo']}]: {recorrido}")

    def mostrar_cromosoma_ga(cromo):
        if cromo is None:
            LOG("  [GA] Sin solucion.")
            return
        rutas = getattr(cromo, "rutas", None)
        if rutas is None:
            LOG("  [GA] No se pudo leer 'rutas' del resultado.")
            return
        activas = [r for r in rutas if getattr(r, "clientes", None)]
        if not activas:
            LOG("  [GA] Cromosoma sin rutas activas.")
            return
        plantas = sorted({r.planta for r in activas})
        LOG(f"  [GA] Plantas abiertas: {plantas}  |  Camiones activos: {len(activas)}")
        for idx, r in enumerate(activas, start=1):
            recorrido = " -> ".join([r.planta] + list(r.clientes) + [r.planta])
            try:
                carga = r.carga(inst)
                LOG(f"    Camion {idx:2d} [{r.modo}]: {recorrido}  (carga={carga:.1f} kg)")
            except Exception:
                LOG(f"    Camion {idx:2d} [{r.modo}]: {recorrido}")

    LOG("--- Solucion EXACTA (MILP global con rutas) ---")
    mostrar_rutas_exactas(sol_exacta)

    LOG("")
    LOG("--- Solucion del ALGORITMO GENETICO (poblacion aleatoria) ---")
    mostrar_cromosoma_ga(resultado_ga["mejor"] if resultado_ga else None)


# =========================================================================
# PASO 7 — COMPARATIVA Y VEREDICTO
# =========================================================================
def paso7_comparativa(sol_exacta, resultado_ga):
    SEC("PASO 7 — COMPARATIVA")

    ref = (sol_exacta or {}).get("objetivo")
    val_ga = (resultado_ga or {}).get("fitness")

    print(f"{'METODO':<20} {'VALOR':>14} {'GAP %':>10}")
    print("-" * 46)
    if ref is not None:
        print(f"{'MILP exacto':<20} {ref:>14.4f} {'0.000':>10}")
    if val_ga is not None:
        gap = (100.0 * (val_ga - ref) / abs(ref)) if ref else None
        gap_str = f"{gap:.3f}" if gap is not None else "n/d"
        print(f"{'GA (aleatorio)':<20} {val_ga:>14.4f} {gap_str:>10}")

    factible = (resultado_ga or {}).get("factible")
    if resultado_ga is None:
        veredicto = "FALLO: el GA no llego a ejecutarse."
    elif factible is True:
        veredicto = "EXITO: el GA encontro una solucion FACTIBLE."
    elif factible is False:
        veredicto = "AVISO: la mejor solucion del GA es INFACTIBLE."
    else:
        veredicto = "INDETERMINADO: no se pudo comprobar la factibilidad."
    LOG("VEREDICTO:", veredicto)

    dir_exp = CONFIG["DIR_EXPERIMENTO"]
    marca = datetime.datetime.now().isoformat(timespec="seconds")
    with open(os.path.join(dir_exp, "logs", "log_completo.txt"), "w", encoding="utf-8") as fh:
        fh.write(_BUFFER_LOG.getvalue())
    guardar_json(
        {
            "objetivo_exacto": ref,
            "fitness_ga": val_ga,
            "veredicto": veredicto,
            "marca_temporal": marca,
        },
        os.path.join(dir_exp, "RESULTADOS_VerificacionMicro", "comparativa.json"),
    )
    if TRACEBACKS:
        guardar_json(TRACEBACKS, os.path.join(dir_exp, "logs", "tracebacks.json"))
        LOG(f"Tracebacks registrados: {len(TRACEBACKS)} (ver logs/tracebacks.json)")


# =========================================================================
# MAIN
# =========================================================================
def main():
    paso1_configuracion()
    modelo, cromosoma_mod, fitness, ga_engine, milp_global_exacto = paso2_importar_modulos()
    inst = paso3_cargar_instancia(modelo)
    sol_exacta = paso4_milp_exacto(inst, milp_global_exacto)
    resultado_ga, _eval = paso5_algoritmo_genetico(inst, fitness, ga_engine)
    paso6_detalle_soluciones(inst, sol_exacta, resultado_ga)
    paso7_comparativa(sol_exacta, resultado_ga)


if __name__ == "__main__":
    main()
