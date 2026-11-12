"""Modelo de costos multiobjetivo por tramo y planificación de rutas por modo."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .config import AlgoParams, EnvParams, MODES, Weights
from .data import RoadGraph, load_graph, resolve_place
from .search import astar, bfs, dijkstra, make_heuristic

NETWORK_FOR_MODE = {"carro": "drive", "bus": "drive", "bicicleta": "walk"}
MAX_SNAP_M = 400  # si el punto queda más lejos de la red, se considera fuera del área


@dataclass
class EdgeMetrics:
    length_m: float
    speed_kmh: float
    time_s: float
    money_cop: float
    co2_kg: float
    provenance: str


def edge_metrics(edge, mode: str, hour: int, env: EnvParams) -> EdgeMetrics:
    """Métricas físicas de un tramo para un modo y hora de salida."""
    L = edge.length_m
    if mode == "carro":
        f = env.congestion(hour)
        v = env.speed_car[edge.road_class] * f
        fuel_l = L / 1000 * env.car_consumption_l_100km / 100
        return EdgeMetrics(L, v, L / (v / 3.6), fuel_l * env.gasoline_price_cop_l, fuel_l * env.gasoline_kgco2_l,
                           f"supuesto: base {edge.road_class} {env.speed_car[edge.road_class]:.0f} km/h × congestión {f:.2f} ({hour}:00)")
    if mode == "bus":
        f = env.congestion(hour)
        v = env.speed_bus[edge.road_class] * f
        fuel_l = L / 1000 * env.bus_consumption_l_100km / 100
        return EdgeMetrics(L, v, L / (v / 3.6), 0.0, fuel_l * env.diesel_kgco2_l / env.bus_occupancy,
                           f"supuesto: base {edge.road_class} {env.speed_bus[edge.road_class]:.0f} km/h × congestión {f:.2f} ({hour}:00)")
    if mode == "bicicleta":
        v = env.speed_bike_kmh
        return EdgeMetrics(L, v, L / (v / 3.6), 0.0, 0.0, f"supuesto: velocidad constante {v:.0f} km/h (informativa)")
    raise ValueError(f"Modo desconocido: {mode}. Use uno de {MODES}.")


def weighted_cost(m: EdgeMetrics, w: Weights) -> float:
    """Costo escalar: km, minutos, miles de COP y cientos de gramos de CO2 ponderados."""
    return (w.distance * m.length_m / 1000 + w.time * m.time_s / 60
            + w.cost * m.money_cop / 1000 + w.emissions * m.co2_kg * 10)


def effective_weights(mode: str, w: Weights) -> Weights:
    # La bicicleta optimiza distancia (tiempo ∝ distancia, costo y emisiones = 0).
    return Weights(distance=1.0, time=0.0, cost=0.0, emissions=0.0) if mode == "bicicleta" else w


def build_adjacency(graph: RoadGraph, mode: str, hour: int, env: EnvParams, w: Weights):
    """Lista de adyacencia con costos ponderados, métricas por arista y cota k_min (costo/metro)."""
    w = effective_weights(mode, w)
    w.validate()
    adj: dict = {n: [] for n in graph.coords}
    metrics = []
    k_min = math.inf
    for eid, e in enumerate(graph.edges):
        m = edge_metrics(e, mode, hour, env)
        c = weighted_cost(m, w)
        if c < 0:
            raise ValueError("Costo negativo: revise los parámetros.")
        metrics.append(m)
        adj[e.u].append((e.v, c, eid))
        if e.length_m > 0:
            k_min = min(k_min, c / e.length_m)
    return adj, metrics, (0.0 if k_min is math.inf else k_min)


@dataclass
class RoutePlan:
    mode: str
    hour: int
    origin: tuple
    destination: tuple
    found: bool
    distance_km: float = 0.0
    time_min: float = 0.0
    cost_cop: float = 0.0
    co2_kg: float = 0.0
    weighted_cost: float = 0.0
    algorithm: str = ""
    expanded: int = 0
    runtime_ms: float = 0.0
    snap_m: tuple = (0.0, 0.0)
    geometry: list = field(default_factory=list)
    segments: list = field(default_factory=list)
    message: str = ""

    def summary(self) -> dict:
        return {
            "modo": self.mode, "hora_salida": f"{self.hour:02d}:00", "encontrada": self.found,
            "distancia_km": round(self.distance_km, 2), "tiempo_min": round(self.time_min, 1),
            "costo_cop": round(self.cost_cop), "co2_kg": round(self.co2_kg, 3),
            "algoritmo": self.algorithm, "nodos_expandidos": self.expanded,
            "distancia_a_la_red_m": [round(x) for x in self.snap_m],
            "nota": self.message,
        }


class Planner:
    """Mantiene los grafos cargados y resuelve rutas con el algoritmo elegido."""

    def __init__(self, graphs: dict | None = None):
        self._graphs = dict(graphs or {})

    def graph(self, mode: str) -> RoadGraph:
        nt = NETWORK_FOR_MODE[mode]
        if nt not in self._graphs:
            self._graphs[nt] = load_graph(nt)
        return self._graphs[nt]

    def search(self, mode, o_node, d_node, hour, env, w, algo: AlgoParams):
        g = self.graph(mode)
        adj, metrics, k_min = build_adjacency(g, mode, hour, env, w)
        algo = algo.clamp()
        if algo.algorithm == "astar":
            h = make_heuristic(g.coords, d_node, k_min, algo.heuristic_weight)
            res = astar(adj, o_node, d_node, h)
        elif algo.algorithm == "dijkstra":
            res = dijkstra(adj, o_node, d_node)
        elif algo.algorithm == "bfs":
            res = bfs(adj, o_node, d_node)
        else:
            raise ValueError(f"Algoritmo desconocido: {algo.algorithm}")
        return res, metrics

    def plan(self, origin, destination, mode: str = "carro", hour: int = 8,
             env: EnvParams | None = None, weights: Weights | None = None,
             algo: AlgoParams | None = None) -> RoutePlan:
        env, weights, algo = env or EnvParams(), weights or Weights(), algo or AlgoParams()
        if mode not in MODES:
            raise ValueError(f"Modo desconocido: '{mode}'. Use uno de {MODES}.")
        if not 0 <= int(hour) <= 23:
            raise ValueError("La hora debe estar entre 0 y 23.")
        hour = int(hour)
        o, d = resolve_place(origin), resolve_place(destination)
        g = self.graph(mode)
        o_node, o_snap = g.nearest_node(o)
        d_node, d_snap = g.nearest_node(d)
        plan = RoutePlan(mode, hour, o, d, False, snap_m=(o_snap, d_snap), algorithm=algo.algorithm)
        if max(o_snap, d_snap) > MAX_SNAP_M:
            plan.message = "Origen o destino fuera del área cubierta por la red descargada (Centro–Laureles–El Poblado)."
            return plan
        res, metrics = self.search(mode, o_node, d_node, hour, env, weights, algo)
        plan.expanded, plan.runtime_ms = res.expanded, res.runtime_ms
        if not res.found:
            plan.message = "No existe ruta entre los puntos en la red de este modo."
            return plan
        plan.found = True
        plan.weighted_cost = res.cost
        for eid in res.edges:
            e, m = g.edges[eid], metrics[eid]
            plan.distance_km += m.length_m / 1000
            plan.time_min += m.time_s / 60
            plan.cost_cop += m.money_cop
            plan.co2_kg += m.co2_kg
            plan.geometry.extend(e.geometry if not plan.geometry else e.geometry[1:])
            plan.segments.append({
                "via": e.name or "(sin nombre)", "clase": e.road_class, "longitud_m": round(m.length_m, 1),
                "velocidad_kmh": round(m.speed_kmh, 1), "tiempo_s": round(m.time_s, 1), "procedencia": m.provenance,
            })
        if mode == "bus":
            plan.cost_cop += env.bus_fare_cop
            plan.message = ("Bus estimado sobre la red vial (sin rutas ni horarios oficiales); "
                            "el costo es la tarifa básica.")
        elif mode == "bicicleta":
            plan.message = "Bicicleta sobre la red peatonal de OSM; la ruta minimiza distancia."
        else:
            plan.message = "Costo = combustible estimado; no incluye parqueadero ni peajes."
        return plan

    def compare(self, origin, destination, hour: int = 8, env=None, weights=None, algo=None) -> list[RoutePlan]:
        return [self.plan(origin, destination, m, hour, env, weights, algo) for m in MODES]
