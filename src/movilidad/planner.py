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
        graph = self.graph("bicicleta")
        origin_node, origin_snap = graph.nearest_node(origin)
        destination_node, destination_snap = graph.nearest_node(destination)
        plan.snap_m = (origin_snap, destination_snap)
        if max(plan.snap_m) > MAX_SNAP_M:
            plan.message = "Origen o destino fuera del área cubierta por la red peatonal descargada."
            return plan

        road_nodes = {node: ("road", node) for node in graph.coords}
        start, goal = road_nodes[origin_node], road_nodes[destination_node]
        adjacency = {state: [] for state in road_nodes.values()}
        coords = {road_nodes[node]: point for node, point in graph.coords.items()}
        transitions = []
        min_cost_per_meter = math.inf

        def add_transition(source, target, kind, mode, metrics, geometry, description, via, road_class):
            nonlocal min_cost_per_meter
            edge_cost = weighted_cost(metrics, weights)
            edge_id = len(transitions)
            transitions.append({
                "kind": kind, "mode": mode, "metrics": metrics, "geometry": geometry,
                "description": description, "via": via, "road_class": road_class,
            })
            adjacency.setdefault(source, []).append((target, edge_cost, edge_id))
            if metrics.length_m > 0:
                min_cost_per_meter = min(min_cost_per_meter, edge_cost / metrics.length_m)

        walk_provenance = f"red peatonal OSM; velocidad supuesta {env.walk_speed_kmh:.1f} km/h"
        for edge in graph.edges:
            metrics = EdgeMetrics(
                edge.length_m, env.walk_speed_kmh, edge.length_m / (env.walk_speed_kmh / 3.6),
                0.0, 0.0, walk_provenance,
            )
            add_transition(
                road_nodes[edge.u], road_nodes[edge.v], "walk", "a pie", metrics,
                edge.geometry or [graph.coords[edge.u], graph.coords[edge.v]],
                "Caminata por red peatonal OSM", edge.name or "(sin nombre)", edge.road_class,
            )

        stations = self._stations
        if stations is None:
            stations = load_metro_stations()
            self._stations = stations
        connected_stations = []
        for station in metro_line_a_stations(stations):
            station_xy = (station["lat"], station["lon"])
            road_node, snap_m = graph.nearest_node(station_xy)
            if snap_m > MAX_SNAP_M:
                continue
            connected_stations.append((station, station_xy, road_node, snap_m))

        for index, (station, station_xy, road_node, snap_m) in enumerate(connected_stations):
            platform = ("platform", index)
            onboard = ("train", index)
            coords[platform] = station_xy
            coords[onboard] = station_xy
            adjacency[platform] = []
            adjacency[onboard] = []
            access_metrics = EdgeMetrics(
                snap_m, env.walk_speed_kmh, snap_m / (env.walk_speed_kmh / 3.6), 0.0, 0.0,
                f"aproximación peatonal al nodo OSM más cercano; {walk_provenance}",
            )
            connector_geometry = [graph.coords[road_node], station_xy]
            add_transition(
                road_nodes[road_node], platform, "walk", "a pie", access_metrics, connector_geometry,
                f"Caminata hasta {station['name']}", f"Acceso a {station['name']}", "acceso a estación",
            )
            add_transition(
                platform, road_nodes[road_node], "walk", "a pie", access_metrics,
                connector_geometry[::-1], f"Caminata desde {station['name']}",
                f"Salida de {station['name']}", "acceso a estación",
            )
            board = EdgeMetrics(
                0.0, 0.0, env.metro_boarding_min * 60, env.metro_fare_cop, 0.0,
                "tarifa frecuente 2026 y espera de abordaje supuesta",
            )
            add_transition(
                platform, onboard, "board", "metro", board, [],
                f"Abordaje en {station['name']}", f"Abordaje en {station['name']}", "Metro Línea A",
            )
            alight = EdgeMetrics(0.0, 0.0, 0.0, 0.0, 0.0, "descenso del tren")
            add_transition(
                onboard, platform, "alight", "metro", alight, [],
                f"Descenso en {station['name']}", f"Descenso en {station['name']}", "Metro Línea A",
            )

        for index, (first, second) in enumerate(zip(connected_stations, connected_stations[1:])):
            first_station, first_xy = first[0], first[1]
            second_station, second_xy = second[0], second[1]
            distance_m = haversine_m(first_xy, second_xy)
            ride = EdgeMetrics(
                distance_m, env.metro_speed_kmh, distance_m / (env.metro_speed_kmh / 3.6),
                0.0, 0.0, "trazo esquemático; velocidad supuesta",
            )
            for source, target, a, b in (
                (("train", index), ("train", index + 1), first_station, second_station),
                (("train", index + 1), ("train", index), second_station, first_station),
            ):
                description = f"Línea A: {a['name']} → {b['name']}"
                add_transition(
                    source, target, "ride", "metro", ride, [(a["lat"], a["lon"]), (b["lat"], b["lon"])],
                    description, description, "Metro Línea A",
                )

        algo = algo.clamp()
        heuristic = make_heuristic(
            coords, goal, 0.0 if math.isinf(min_cost_per_meter) else min_cost_per_meter,
            algo.heuristic_weight,
        )
        if algo.algorithm == "astar":
            result = astar(adjacency, start, goal, heuristic)
        elif algo.algorithm == "dijkstra":
            result = dijkstra(adjacency, start, goal)
        elif algo.algorithm == "bfs":
            result = bfs(adjacency, start, goal)
        else:
            raise ValueError(f"Algoritmo desconocido: {algo.algorithm}")
        plan.expanded, plan.runtime_ms = result.expanded, result.runtime_ms
        if not result.found:
            plan.message = "No se encontró una ruta peatonal ni una combinación con la Línea A."
            return plan

        plan.found = True
        plan.weighted_cost = result.cost
        plan.selection_cost = result.cost
        for edge_id in result.edges:
            transition = transitions[edge_id]
            metrics = transition["metrics"]
            plan.distance_km += metrics.length_m / 1000
            plan.time_min += metrics.time_s / 60
            plan.cost_cop += metrics.money_cop
            plan.co2_kg += metrics.co2_kg

            if transition["kind"] == "alight":
                continue
            if plan.legs and plan.legs[-1]["mode"] == transition["mode"]:
                leg = plan.legs[-1]
            else:
                leg = {
                    "mode": transition["mode"], "geometry": [], "distance_km": 0.0,
                    "time_min": 0.0, "cost_cop": 0.0, "description": "",
                }
                plan.legs.append(leg)
            leg_geometry = transition["geometry"]
            if leg_geometry:
                if leg["geometry"] and leg["geometry"][-1] == leg_geometry[0]:
                    leg["geometry"].extend(leg_geometry[1:])
                else:
                    leg["geometry"].extend(leg_geometry)
            leg["distance_km"] += metrics.length_m / 1000
            leg["time_min"] += metrics.time_s / 60
            leg["cost_cop"] += metrics.money_cop
            if transition["description"] and transition["mode"] == "metro":
                leg["description"] = "; ".join(filter(None, (leg["description"], transition["description"])))
            elif transition["mode"] == "a pie":
                leg["description"] = "Caminata por red peatonal OSM"

            plan.segments.append({
                "via": transition["via"], "clase": transition["road_class"],
                "longitud_m": round(metrics.length_m, 1), "velocidad_kmh": round(metrics.speed_kmh, 1),
                "tiempo_s": round(metrics.time_s, 1), "procedencia": metrics.provenance,
                "modo_tramo": transition["mode"], "costo_cop": round(metrics.money_cop),
            })
        for leg in plan.legs:
            if leg["geometry"]:
                if plan.geometry and plan.geometry[-1] == leg["geometry"][0]:
                    plan.geometry.extend(leg["geometry"][1:])
                else:
                    plan.geometry.extend(leg["geometry"])
        rode_metro = any(leg["mode"] == "metro" for leg in plan.legs)
        if rode_metro:
            plan.message = (
                "Ruta multimodal calculada con A*: caminar y abordar la Línea A son opciones. "
                "Velocidad, espera y trazo del Metro son estimados."
            )
        else:
            plan.message = (
                "A* encontró que caminar es la opción de menor costo; no es necesario abordar el Metro."
            )
        return plan

    def compare(self, origin, destination, hour: int = 8, env=None, weights=None, algo=None) -> list[RoutePlan]:
        return [self.plan(origin, destination, m, hour, env, weights, algo) for m in MODES]
