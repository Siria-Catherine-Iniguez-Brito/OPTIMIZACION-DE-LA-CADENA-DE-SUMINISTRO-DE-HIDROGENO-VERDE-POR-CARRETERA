"""
Paquete EXPERIMENTOS
====================

Marco experimental del TFM "Optimizacion de la Cadena de Suministro de Hidrogeno
Verde por Carretera": calibracion de los hiperparametros del algoritmo genetico y
estudio de las estrategias de inicializacion de la poblacion.

Modulos
-------
    config_experimentos : catalogo de experimentos y rejillas de parametros (EDITAR AQUI)
    instancias          : resolucion y carga (con cache) de los ficheros de instancia
    runner              : ejecuta UNA configuracion con UNA semilla -> una fila de resultados
    calibracion         : bucle instancias x rejilla x semillas -> CSVs
    agregacion          : runs.csv -> resumen.csv -> ranking.csv (trata los infactibles)
    graficas            : convergencia, boxplots, heatmaps, Pareto, factibilidad
    exportar            : CSV -> Excel multihoja + tablas LaTeX
    main_EXPERIMENTOS   : interfaz de linea de ordenes

Diseno de referencia: EXPERIMENTOS_diseno.md
"""

__version__ = "1.0.0"
