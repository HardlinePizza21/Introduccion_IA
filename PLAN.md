# Plan: Copiloto de movilidad (idea 3.2)

## Problema y enfoque

Implementar un MVP reproducible en Python para comparar rutas y modos de movilidad en el Valle de Aburrá. El usuario elegirá origen, destino, modo y hora de salida estimada, configurará los supuestos que definen el entorno de búsqueda y recibirá rutas alternativas, métricas y explicaciones desde un dashboard.

El repositorio no contiene actualmente archivos de proyecto. `Quiz1.md` figura eliminado en el worktree; conservar ese cambio sin restaurarlo.

## Decisiones de diseño

- **Datos y modos:** obtener la red vial de OpenStreetMap en tiempo de ejecución. Usar una red peatonal bidireccional de OSM para bicicleta, sin restricciones específicas de ciclorrutas; su costo principal será la distancia. Carro y bus usarán una red vial común; la hora elegida será la hora local de salida prevista y afectará la velocidad estimada mediante factores de congestión supuestos. No buscar horarios ni tiempos de ruta publicados para el bus. Buscar y citar datos públicos de consumo/eficiencia de combustible y velocidades de buses para sustentar los parámetros; si no se verifica una fuente adecuada, marcar los valores como supuestos ajustables. El Metro, si tiene geometría de rutas utilizable, podrá mostrarse con velocidad promedio supuesta, sin depender de horarios publicados. La aplicación requerirá conexión para obtener OSM y reportará claramente fallos de acceso, sin dataset local de respaldo.
- **Costo de ruta:** separar controles explicados en tres grupos: (1) parámetros del entorno, como velocidades base por tipo de vía y modo, factor horario de congestión, consumo de combustible (L/100 km), precio y emisiones; (2) pesos de preferencias, por ejemplo distancia, tiempo, costo y emisiones; (3) controles del algoritmo. El factor horario reducirá la velocidad efectiva del carro y bus durante las franjas configuradas, no representará tráfico medido. La bicicleta optimizará distancia; su velocidad estimada será solo informativa.
- **Velocidad por tramo:** calcular y mostrar la velocidad estimada de cada tramo de la ruta para carro y bus usando el tipo de vía, velocidad base del modo y factor de congestión según la hora. Presentar un detalle por tramo (o información emergente en el mapa) con longitud, velocidad, tiempo estimado y la procedencia de la estimación. Los cambios en parámetros u hora deben reconstruir costos y volver a ejecutar la búsqueda.
- **A* correcto:** implementar A* propio y compararlo con Dijkstra en nodos expandidos y costo final. Construir una heurística geométrica basada en una cota inferior por distancia. Si se permite configurar su intensidad, limitarla a [0, 1] para conservar admisibilidad; distinguir ese control de los parámetros del entorno y las preferencias de objetivos. No permitir costos negativos ni presentar como óptimos resultados con una heurística no admisible.
- **Agente:** loop sencillo con endpoint compatible con OpenAI configurable por variables de entorno, RAG sobre fuentes oficiales de Metro y reglas vigentes de pico y placa, y herramientas para planificar ruta y consultar documentos. La interfaz permitirá explorar y comparar rutas aunque falten credenciales LLM; en tal caso, el chat explicará el error de configuración explícitamente.
- **Interfaz:** Streamlit con mapa de rutas y tabla comparativa de distancia, tiempo, costo estimado y emisiones, más controles con unidades, valores predeterminados y textos breves que expliquen qué modifica cada uno. Cada cambio relevante recalculará los costos y las rutas.
- **Calidad y reproducibilidad:** README con instalación, ejecución, variables de entorno, fuentes/citas y limitaciones; pruebas para costos, heurística, búsqueda y cambios de parámetros; evaluación A* vs. Dijkstra y un conjunto de preguntas para verificar herramientas/citas del agente.

## Tareas

1. Crear la estructura Python, dependencias y acceso acotado a datos OSM/transporte, con manejo explícito de errores y fuentes.
2. Implementar los modelos de costo configurables y los algoritmos A*/Dijkstra; probar optimalidad, admisibilidad y comparación de nodos expandidos.
3. Implementar el corpus RAG y las herramientas del agente para consultar rutas y documentos, incluyendo configuración del endpoint.
4. Construir el dashboard interactivo con hora de salida, parámetros explicados y velocidades estimadas por tramo; enlazar cada cambio con el recálculo de rutas y documentar ejecución, evaluación y limitaciones.
5. Mantener este documento alineado con el alcance implementado.

## Consideraciones

- Mantener pequeño el área inicial de descarga de OSM para que la demo no sea lenta ni consuma demasiada memoria.
- No confundir consumo (p. ej., L/100 km) con autonomía del bus: autonomía requeriría modelar tanque, carga y necesidad de repostar; no es necesaria para comparar rutas cortas. Si una fuente expresa rendimiento en km/L, convertir y documentar la conversión.
- Separar datos observados de estimaciones para velocidad, consumo y congestión; rotular cada métrica según su procedencia.
- El modo bicicleta seguirá caminos peatonales conectados de OSM, no movimiento geométrico sin restricciones fuera de la red. Este supuesto evita rutas atravesando edificios, ríos u otras barreras.
- Al no incluir respaldo local, la demostración depende de conectividad y disponibilidad de los servicios externos; si se prioriza robustez, una caché local sería el cambio recomendado.
