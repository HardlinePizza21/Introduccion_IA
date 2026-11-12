"""Parámetros del entorno, pesos de preferencias y controles del algoritmo.

Cada valor numérico lleva su procedencia ("fuente" o "supuesto") para separar
datos observados de estimaciones, como exige el plan del proyecto.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

# Área de estudio (left, bottom, right, top) en grados: Centro – Laureles – El Poblado.
# Se mantiene pequeña para que la descarga OSM y la búsqueda sean rápidas en la demo.
BBOX = (-75.600, 6.195, -75.555, 6.272)

MODES = ("carro", "bus", "bicicleta")

# Clases de vía OSM agrupadas -> velocidad base (km/h) a flujo libre por modo.
# SUPUESTO ajustable: valores de referencia urbanos, NO medidos (ver README).
ROAD_CLASSES = ("troncal", "arteria", "colectora", "local")
HIGHWAY_TO_CLASS = {
    "motorway": "troncal", "motorway_link": "troncal", "trunk": "troncal", "trunk_link": "troncal",
    "primary": "arteria", "primary_link": "arteria", "secondary": "arteria", "secondary_link": "arteria",
    "tertiary": "colectora", "tertiary_link": "colectora",
}


def road_class(highway) -> str:
    """Mapea la etiqueta `highway` de OSM (str o lista) a una clase agregada."""
    if isinstance(highway, (list, tuple)):
        classes = [road_class(h) for h in highway]
        order = {c: i for i, c in enumerate(ROAD_CLASSES)}
        return min(classes, key=order.__getitem__)
    return HIGHWAY_TO_CLASS.get(str(highway), "local")


@dataclass
class EnvParams:
    """Grupo 1: parámetros del entorno (definen costos físicos de cada tramo)."""

    # Velocidades base a flujo libre (km/h) — SUPUESTO
    speed_car: dict = field(default_factory=lambda: {"troncal": 60.0, "arteria": 45.0, "colectora": 35.0, "local": 25.0})
    speed_bus: dict = field(default_factory=lambda: {"troncal": 40.0, "arteria": 30.0, "colectora": 25.0, "local": 20.0})
    speed_bike_kmh: float = 15.0  # informativa; la bicicleta optimiza distancia

    # Congestión: factor multiplicativo sobre la velocidad en horas pico (0 < f <= 1) — SUPUESTO
    peak_hours: tuple = (6, 7, 8, 17, 18, 19)
    peak_factor: float = 0.55
    shoulder_hours: tuple = (9, 12, 13, 16, 20)
    shoulder_factor: float = 0.8

    # Carro (gasolina)
    car_consumption_l_100km: float = 8.0  # SUPUESTO: consumo urbano típico de un carro particular
    gasoline_price_cop_gal: float = 16251.0  # FUENTE: precio de referencia Medellín nov-2026 (CREG/MinEnergía)
    gasoline_kgco2_l: float = 2.31  # SUPUESTO (≈ factor IPCC 2006); verificar con calculadora FECOC de UPME

    # Bus (diésel), emisiones repartidas por pasajero
    bus_fare_cop: float = 3000.0  # FUENTE: tarifa básica bus urbano Medellín 2026 (Valora Analitik)
    bus_consumption_l_100km: float = 35.0  # SUPUESTO
    diesel_kgco2_l: float = 2.68  # SUPUESTO (≈ factor IPCC 2006)
    bus_occupancy: float = 30.0  # SUPUESTO: pasajeros promedio a bordo

    @property
    def gasoline_price_cop_l(self) -> float:
        return self.gasoline_price_cop_gal / 3.785411784  # 1 galón US = 3,785 L

    def congestion(self, hour: int) -> float:
        if hour in self.peak_hours:
            return self.peak_factor
        if hour in self.shoulder_hours:
            return self.shoulder_factor
        return 1.0


@dataclass
class Weights:
    """Grupo 2: pesos de preferencias. Cada término se mide en su unidad:
    distancia [km], tiempo [min], costo [miles de COP], emisiones [100 g CO2]."""

    distance: float = 0.0
    time: float = 1.0
    cost: float = 0.0
    emissions: float = 0.0

    def validate(self) -> None:
        vals = asdict(self).values()
        if any(v < 0 for v in vals):
            raise ValueError("Los pesos no pueden ser negativos (A* requiere costos >= 0).")
        if sum(vals) == 0:
            raise ValueError("Al menos un peso debe ser mayor que 0.")


@dataclass
class AlgoParams:
    """Grupo 3: controles del algoritmo."""

    algorithm: str = "astar"  # astar | dijkstra | bfs
    heuristic_weight: float = 1.0  # se recorta a [0, 1] para conservar admisibilidad

    def clamp(self) -> "AlgoParams":
        self.heuristic_weight = min(1.0, max(0.0, float(self.heuristic_weight)))
        return self


SOURCES = {
    "gasoline_price": "Circular CREG 371 de 2026 / MinEnergía: gasolina corriente Medellín $16.251/galón (nov-2026). https://gestornormativo.creg.gov.co/gestor/entorno/docs/originales/Circular_CREG_371_2026/",
    "bus_fare": "Valora Analitik (ene-2026): bus urbano Medellín $3.000. https://www.valoraanalitik.com/tarifas-del-transporte-en-las-principales-ciudades-para-2026/",
    "osm": "© OpenStreetMap contributors (ODbL), descargado con OSMnx.",
}
