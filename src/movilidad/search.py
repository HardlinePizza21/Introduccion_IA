"""Búsqueda en grafos implementada por el equipo: A*, Dijkstra (UCS) y BFS.

No se usa networkx para resolver la ruta: el grafo se recibe como lista de
adyacencia `adj[u] = [(v, costo, edge_id), ...]` y coordenadas `coords[u] = (lat, lon)`.
"""
from __future__ import annotations

import heapq
import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Hashable

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distancia de gran círculo en metros entre (lat, lon) a y b."""
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


@dataclass
class SearchResult:
    algorithm: str
    path: list = field(default_factory=list)  # nodos
    edges: list = field(default_factory=list)  # edge_id de cada tramo
    cost: float = math.inf
    expanded: int = 0
    runtime_ms: float = 0.0

    @property
    def found(self) -> bool:
        return bool(self.path)


def _reconstruct(parent: dict, goal: Hashable) -> tuple[list, list, float]:
    path, edges, total = [goal], [], 0.0
    node = goal
    while parent[node] is not None:
        prev, eid, cost = parent[node]
        edges.append(eid)
        path.append(prev)
        total += cost
        node = prev
    return path[::-1], edges[::-1], total


def astar(adj: dict, start, goal, h: Callable[[Hashable], float] | None = None, name: str = "astar") -> SearchResult:
    """A* con conjunto cerrado. Con h=None se comporta como Dijkstra/UCS.

    Si h es consistente (como la heurística de `make_heuristic`), el primer
    costo con que se expande un nodo es óptimo y nunca se reabre.
    """
    t0 = time.perf_counter()
    h = h or (lambda _n: 0.0)
    g = {start: 0.0}
    parent = {start: None}
    closed = set()
    counter = 0  # desempate estable
    frontier = [(h(start), counter, start)]
    expanded = 0
    while frontier:
        _f, _c, u = heapq.heappop(frontier)
        if u in closed:
            continue
        closed.add(u)
        expanded += 1
        if u == goal:
            path, edges, _ = _reconstruct(parent, goal)
            return SearchResult(name, path, edges, g[goal], expanded, (time.perf_counter() - t0) * 1000)
        gu = g[u]
        for v, cost, eid in adj.get(u, ()):
            if cost < 0:
                raise ValueError("Costo negativo detectado: A*/Dijkstra no lo admiten.")
            if v in closed:
                continue
            ng = gu + cost
            if ng < g.get(v, math.inf):
                g[v] = ng
                parent[v] = (u, eid, cost)
                counter += 1
                heapq.heappush(frontier, (ng + h(v), counter, v))
    return SearchResult(name, expanded=expanded, runtime_ms=(time.perf_counter() - t0) * 1000)


def dijkstra(adj: dict, start, goal) -> SearchResult:
    return astar(adj, start, goal, h=None, name="dijkstra")


def bfs(adj: dict, start, goal) -> SearchResult:
    """BFS: minimiza el número de tramos, no el costo. Línea base no ponderada."""
    t0 = time.perf_counter()
    parent = {start: None}
    queue = deque([start])
    expanded = 0
    while queue:
        u = queue.popleft()
        expanded += 1
        if u == goal:
            path, edges, cost = _reconstruct(parent, goal)
            return SearchResult("bfs", path, edges, cost, expanded, (time.perf_counter() - t0) * 1000)
        for v, cost, eid in adj.get(u, ()):
            if v not in parent:
                parent[v] = (u, eid, cost)
                queue.append(v)
    return SearchResult("bfs", expanded=expanded, runtime_ms=(time.perf_counter() - t0) * 1000)


def make_heuristic(coords: dict, goal, cost_per_meter_lb: float, weight: float = 1.0) -> Callable:
    """h(n) = w · k_min · dist_haversine(n, goal).

    k_min es la menor razón costo/longitud entre todas las aristas del grafo. Como la
    longitud de cada arista es >= la distancia en línea recta entre sus extremos,
    c(u,v) >= k_min·d(u,v) >= k_min·(hav(u,goal) - hav(v,goal)): la heurística es
    consistente (y por tanto admisible) para w en [0, 1].
    """
    if not 0.0 <= weight <= 1.0:
        raise ValueError("El peso de la heurística debe estar en [0, 1] para ser admisible.")
    goal_xy = coords[goal]
    k = cost_per_meter_lb * weight * 0.999  # margen numérico
    return lambda n: k * haversine_m(coords[n], goal_xy)
