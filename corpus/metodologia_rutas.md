# Metodología del copiloto de movilidad: cómo se calculan las rutas

Documento técnico del proyecto (equipo SI3003, 2026).

## Datos
La red vial y peatonal se obtiene de OpenStreetMap (© colaboradores de OpenStreetMap, licencia ODbL) con la librería OSMnx, para un área entre el Centro, Laureles y El Poblado de Medellín. Carro y bus usan la red vehicular ("drive"), que respeta los sentidos de las vías. La bicicleta usa la red peatonal ("walk"), que es bidireccional; no se modelan ciclorrutas.

## Velocidades estimadas y tráfico
No se usa tráfico en tiempo real. La velocidad de cada tramo es una velocidad base por tipo de vía y modo (troncal, arteria, colectora, local) multiplicada por un factor de congestión según la hora de salida. Por defecto, en horas pico (6, 7, 8, 17, 18 y 19 h) el factor es 0,55, en horas intermedias (9, 12, 13, 16 y 20 h) es 0,8 y en el resto es 1,0. Por defecto el carro va a 60/45/35/25 km/h y el bus a 40/30/25/20 km/h según el tipo de vía. Son supuestos ajustables, no mediciones.

## Costo multiobjetivo
Cada tramo tiene cuatro métricas: distancia (km), tiempo (min), costo (miles de pesos) y emisiones (cientos de gramos de CO2). El costo usado por la búsqueda es la suma ponderada de esas métricas con los pesos elegidos por el usuario. Los pesos no pueden ser negativos. La bicicleta siempre minimiza distancia.

## Algoritmo A*
El equipo implementó A*, Dijkstra (búsqueda de costo uniforme) y BFS. La heurística de A* es h(n) = k_min × distancia en línea recta (haversine) de n al destino, donde k_min es el menor costo por metro de todas las aristas del grafo. Como ningún tramo es más corto que la línea recta entre sus extremos, la heurística nunca sobreestima: es admisible y consistente, y A* devuelve el mismo costo óptimo que Dijkstra expandiendo menos nodos. El usuario puede escalar la heurística con un peso entre 0 y 1 (0 equivale a Dijkstra); no se permiten pesos mayores que 1 porque romperían la admisibilidad.

## Limitaciones
- El bus se modela como un vehículo sobre la red vial: no usa rutas ni paraderos oficiales, ni tiempos de espera.
- El Metro no se planifica con A*; solo se muestran estaciones y se reporta la más cercana.
- Los resultados son estimaciones para comparar alternativas, no una guía de navegación ni consejo de seguridad vial.
