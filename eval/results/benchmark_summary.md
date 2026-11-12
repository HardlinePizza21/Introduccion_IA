# Benchmark A* vs. Dijkstra vs. BFS

Pares aleatorios por escenario: 100 (semilla 7, distancia recta >= 1 km). Red: OpenStreetMap, área Centro–Laureles–El Poblado.

| escenario               | algoritmo   |   expandidos_media |   tiempo_ms_media |   pct_optimo |   sobrecosto_pct_medio |
|:------------------------|:------------|-------------------:|------------------:|-------------:|-----------------------:|
| bicicleta-distancia-10h | astar       |            2245.74 |              8.79 |          100 |                   0    |
| bicicleta-distancia-10h | astar_w0.5  |            6245.68 |             23.24 |          100 |                   0    |
| bicicleta-distancia-10h | bfs         |           10137.1  |             10.87 |            0 |                  34.89 |
| bicicleta-distancia-10h | dijkstra    |            9888.54 |             19.82 |          100 |                   0    |
| bus-tiempo-18h          | astar       |            1323.96 |              3.24 |          100 |                   0    |
| bus-tiempo-18h          | astar_w0.5  |            2262.93 |              5.39 |          100 |                   0    |
| bus-tiempo-18h          | bfs         |            3238.03 |              1.56 |            5 |                  21.18 |
| bus-tiempo-18h          | dijkstra    |            3245.81 |              3.75 |          100 |                   0    |
| carro-multiobjetivo-14h | astar       |            1034.88 |              2.53 |          100 |                   0    |
| carro-multiobjetivo-14h | astar_w0.5  |            2129.16 |              5    |          100 |                   0    |
| carro-multiobjetivo-14h | bfs         |            3238.03 |              1.42 |            5 |                  20.52 |
| carro-multiobjetivo-14h | dijkstra    |            3249.81 |              3.58 |          100 |                   0    |
| carro-tiempo-8h         | astar       |            1336.34 |              3.39 |          100 |                   0    |
| carro-tiempo-8h         | astar_w0.5  |            2264.3  |              5.55 |          100 |                   0    |
| carro-tiempo-8h         | bfs         |            3238.03 |              2.22 |            5 |                  25.03 |
| carro-tiempo-8h         | dijkstra    |            3242.06 |              3.87 |          100 |                   0    |

| escenario               |   reduccion_expandidos_astar_vs_dijkstra_pct |   mediana_ratio |
|:------------------------|---------------------------------------------:|----------------:|
| bicicleta-distancia-10h |                                         78.8 |           0.2   |
| bus-tiempo-18h          |                                         61.5 |           0.374 |
| carro-multiobjetivo-14h |                                         70.3 |           0.29  |
| carro-tiempo-8h         |                                         61   |           0.37  |