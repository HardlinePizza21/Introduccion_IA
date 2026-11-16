# Benchmark A* vs. Dijkstra vs. BFS

Pares aleatorios por escenario: 100 (semilla 7, distancia recta >= 1 km). Red: OpenStreetMap, corredor de las líneas A/B del Metro y T del Tranvía.

| escenario               | algoritmo   |   expandidos_media |   tiempo_ms_media |   pct_optimo |   sobrecosto_pct_medio |
|:------------------------|:------------|-------------------:|------------------:|-------------:|-----------------------:|
| bicicleta-distancia-10h | astar       |            5812.83 |             20.77 |          100 |                   0    |
| bicicleta-distancia-10h | astar_w0.5  |           15074    |             51.06 |          100 |                   0    |
| bicicleta-distancia-10h | bfs         |           22420.8  |             24.19 |            2 |                  34.17 |
| bicicleta-distancia-10h | dijkstra    |           23791.1  |             47.88 |          100 |                   0    |
| carro-multiobjetivo-14h | astar       |            2834.39 |              7.94 |          100 |                   0    |
| carro-multiobjetivo-14h | astar_w0.5  |            5414.34 |             14.28 |          100 |                   0    |
| carro-multiobjetivo-14h | bfs         |            8189.65 |              6.02 |            3 |                  20.84 |
| carro-multiobjetivo-14h | dijkstra    |            7860.01 |             11.79 |          100 |                   0    |
| carro-tiempo-8h         | astar       |            3558.27 |              9.69 |          100 |                   0    |
| carro-tiempo-8h         | astar_w0.5  |            5725.86 |             15.07 |          100 |                   0    |
| carro-tiempo-8h         | bfs         |            8189.65 |              5.91 |            5 |                  22.54 |
| carro-tiempo-8h         | dijkstra    |            7868.85 |             11.74 |          100 |                   0    |

| escenario               |   reduccion_expandidos_astar_vs_dijkstra_pct |   mediana_ratio |
|:------------------------|---------------------------------------------:|----------------:|
| bicicleta-distancia-10h |                                         77.4 |           0.204 |
| carro-multiobjetivo-14h |                                         66.8 |           0.313 |
| carro-tiempo-8h         |                                         57.7 |           0.419 |