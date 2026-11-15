"""Modelo de costos multiobjetivo por tramo y planificación de rutas por modo."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .config import AlgoParams, EnvParams, MODES, Weights
from .data import RoadGraph, load_graph, load_metro_stations, metro_line_a_stations, resolve_place
from .search import astar, bfs, dijkstra, haversine_m, make_heuristic

NETWORK_FOR_MODE = {"carro": "drive", "bicicleta": "walk"}
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
    selection_cost: float = 0.0
    algorithm: str = ""
    expanded: int = 0
    runtime_ms: float = 0.0
    snap_m: tuple = (0.0, 0.0)
    geometry: list = field(default_factory=list)
    segments: list = field(default_factory=list)
    legs: list = field(default_factory=list)
    message: str = ""

    def summary(self) -> dict:
        return {
            "modo": self.mode, "hora_salida": f"{self.hour:02d}:00", "encontrada": self.found,
            "distancia_km": round(self.distance_km, 2), "tiempo_min": round(self.time_min, 1),
            "costo_cop": round(self.cost_cop), "co2_kg": round(self.co2_kg, 3),
            "costo_preferencias": round(self.selection_cost, 3),
            "algoritmo": self.algorithm, "nodos_expandidos": self.expanded,
            "distancia_a_la_red_m": [round(x) for x in self.snap_m],
            "itinerario": [
                {"modo": leg["mode"], "distancia_km": round(leg["distance_km"], 2),
                 "tiempo_min": round(leg["time_min"], 1), "detalle": leg["description"]}
                for leg in self.legs
            ],
            "nota": self.message,
        }


class Planner:
    """Mantiene los grafos cargados y resuelve rutas con el algoritmo elegido."""

    def __init__(self, graphs: dict | None = None, stations: list[dict] | None = None):
        self._graphs = dict(graphs or {})
        self._stations = stations

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
        if mode == "metro":
            return self._plan_metro(o, d, hour, env, weights, algo)
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
                "modo_tramo": mode,
            })
        plan.selection_cost = (
            weights.distance * plan.distance_km + weights.time * plan.time_min
            + weights.cost * plan.cost_cop / 1000 + weights.emissions * plan.co2_kg * 10
        )
        plan.legs = [{
            "mode": mode, "geometry": plan.geometry, "distance_km": plan.distance_km, "time_min": plan.time_min,
            "description": {"carro": "Carro", "bicicleta": "Bicicleta / a pie"}[mode],
        }]
        if mode == "bicicleta":
            plan.message = "Bicicleta sobre la red peatonal de OSM; la ruta minimiza distancia."
        else:
            plan.message = "Costo = combustible estimado; no incluye parqueadero ni peajes."
        return plan

    def _plan_metro(self, origin, destination, hour, env, weights, algo) -> RoutePlan:
        weights.validate()
        if (env.metro_speed_kmh <= 0 or env.walk_speed_kmh <= 0
                or env.metro_boarding_min < 0 or env.metro_fare_cop < 0):
            raise ValueError("Las velocidades deben ser positivas; espera y tarifa no pueden ser negativas.")
        plan = RoutePlan("metro", hour, origin, destination, False, algorithm=algo.algorithm)
        stations = self._stations
        if stations is None:
            stations = load_metro_stations()
            self._stations = stations
        stations = metro_line_a_stations(stations)
        if len(stations) < 2:
            plan.message = "No hay suficientes estaciones de Línea A para calcular un tramo en Metro."
            return plan

        walking_to = [
            self.plan(origin, (station["lat"], station["lon"]), "bicicleta", hour, env, weights, algo)
            for station in stations
        ]
        walking_from = [
            self.plan((station["lat"], station["lon"]), destination, "bicicleta", hour, env, weights, algo)
            for station in stations
        ]
        best = None
        for start, access in enumerate(walking_to):
            if not access.found:
                continue
            for end, egress in enumerate(walking_from):
                if start == end or not egress.found:
                    continue
                step = 1 if end > start else -1
                indices = range(start, end + step, step)
                ride_geometry = [(stations[i]["lat"], stations[i]["lon"]) for i in indices]
                ride_distance_m = sum(
                    haversine_m(a, b) for a, b in zip(ride_geometry, ride_geometry[1:])
                )
                ride_time_s = ride_distance_m / (env.metro_speed_kmh / 3.6) + env.metro_boarding_min * 60
                ride = EdgeMetrics(
                    ride_distance_m, env.metro_speed_kmh, ride_time_s, env.metro_fare_cop, 0.0,
                    "tarifa frecuente 2026; velocidad y espera de abordaje son supuestos",
                )
                access_time_s = access.distance_km * 1000 / (env.walk_speed_kmh / 3.6)
                egress_time_s = egress.distance_km * 1000 / (env.walk_speed_kmh / 3.6)
                access_metrics = EdgeMetrics(
                    access.distance_km * 1000, env.walk_speed_kmh, access_time_s, 0.0, 0.0,
                    "caminata por red peatonal OSM; velocidad supuesta",
                )
                egress_metrics = EdgeMetrics(
                    egress.distance_km * 1000, env.walk_speed_kmh, egress_time_s, 0.0, 0.0,
                    "caminata por red peatonal OSM; velocidad supuesta",
                )
                score = sum(weighted_cost(metrics, weights) for metrics in (access_metrics, ride, egress_metrics))
                if best is None or score < best[0]:
                    best = (score, start, end, access, egress, ride, ride_geometry)

        if best is None:
            plan.message = "No se encontró una combinación de caminata y estaciones de Línea A conectadas por la red."
            return plan

        score, start, end, access, egress, ride, ride_geometry = best
        access_leg = {
            "mode": "a pie", "geometry": access.geometry, "distance_km": access.distance_km,
            "time_min": access.distance_km * 60 / env.walk_speed_kmh,
            "description": f"Caminata hasta {stations[start]['name']}",
        }
        metro_leg = {
            "mode": "metro", "geometry": ride_geometry, "distance_km": ride.length_m / 1000,
            "time_min": ride.time_s / 60,
            "description": f"Línea A: {stations[start]['name']} → {stations[end]['name']}",
        }
        egress_leg = {
            "mode": "a pie", "geometry": egress.geometry, "distance_km": egress.distance_km,
            "time_min": egress.distance_km * 60 / env.walk_speed_kmh,
            "description": f"Caminata desde {stations[end]['name']}",
        }
        plan.legs = [access_leg, metro_leg, egress_leg]
        for leg in plan.legs:
            plan.distance_km += leg["distance_km"]
            plan.time_min += leg["time_min"]
            plan.geometry.extend(leg["geometry"] if not plan.geometry else leg["geometry"][1:])
        plan.cost_cop = env.metro_fare_cop
        plan.weighted_cost = score
        plan.selection_cost = score
        plan.expanded = access.expanded + egress.expanded
        plan.runtime_ms = access.runtime_ms + egress.runtime_ms
        plan.snap_m = (access.snap_m[0], egress.snap_m[1])
        def walking_segments(route):
            return [{
                **segment,
                "modo_tramo": "a pie",
                "velocidad_kmh": round(env.walk_speed_kmh, 1),
                "tiempo_s": round(segment["longitud_m"] / (env.walk_speed_kmh / 3.6), 1),
                "procedencia": f"velocidad al caminar supuesta: {env.walk_speed_kmh:.1f} km/h; red peatonal OSM",
            } for segment in route.segments]

        plan.segments = walking_segments(access) + [{
            "via": metro_leg["description"], "clase": "Metro Línea A",
            "longitud_m": round(ride.length_m, 1), "velocidad_kmh": round(ride.speed_kmh, 1),
            "tiempo_s": round(ride.time_s, 1), "procedencia": ride.provenance,
            "modo_tramo": "metro", "costo_cop": round(ride.money_cop),
        }] + walking_segments(egress)
        plan.found = True
        plan.message = (
            "Itinerario multimodal: caminata por red peatonal OSM + Línea A esquemática + caminata. "
            "Tiempo de Metro y espera estimados; tarifa frecuente 2026; emisiones de escape = 0."
        )
        return plan

    def compare(self, origin, destination, hour: int = 8, env=None, weights=None, algo=None) -> list[RoutePlan]:
        return [self.plan(origin, destination, m, hour, env, weights, algo) for m in MODES]
