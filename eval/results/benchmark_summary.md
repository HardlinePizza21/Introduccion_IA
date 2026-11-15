# Benchmark A* vs. Dijkstra vs. BFS

Pares aleatorios por escenario: 100 (semilla 7, distancia recta >= 1 km). Red: OpenStreetMap, área Centro–Laureles–El Poblado.

| escenario               | algoritmo   |   expandidos_media |   tiempo_ms_media |   pct_optimo |   sobrecosto_pct_medio |
|:------------------------|:------------|-------------------:|------------------:|-------------:|-----------------------:|
| bicicleta-distancia-10h | astar       |            2063.02 |              9.19 |          100 |                   0    |
| bicicleta-distancia-10h | astar_w0.5  |            6861.57 |             28.2  |          100 |                   0    |
| bicicleta-distancia-10h | bfs         |           10311.9  |             13.51 |            0 |                  39.43 |
| bicicleta-distancia-10h | dijkstra    |           11103.5  |             26.86 |          100 |                   0    |
| carro-multiobjetivo-14h | astar       |             858.56 |              2.78 |          100 |                   0    |
| carro-multiobjetivo-14h | astar_w0.5  |            1942.74 |              6.1  |          100 |                   0    |
| carro-multiobjetivo-14h | bfs         |            2859.3  |              2.45 |            6 |                  15.68 |
| carro-multiobjetivo-14h | dijkstra    |            2991.85 |              5.09 |          100 |                   0    |
| carro-tiempo-8h         | astar       |            1101.95 |              3.57 |          100 |                   0    |
| carro-tiempo-8h         | astar_w0.5  |            2028    |              6.35 |          100 |                   0    |
| carro-tiempo-8h         | bfs         |            2859.3  |              2.3  |            7 |                  20.86 |
| carro-tiempo-8h         | dijkstra    |            2958.96 |              5.03 |          100 |                   0    |

| escenario               |   reduccion_expandidos_astar_vs_dijkstra_pct |   mediana_ratio |
|:------------------------|---------------------------------------------:|----------------:|
| bicicleta-distancia-10h |                                         82.1 |           0.167 |
| carro-multiobjetivo-14h |                                         72.9 |           0.272 |
| carro-tiempo-8h         |                                         64.8 |           0.348 |