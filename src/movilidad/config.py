"""Parámetros del entorno, pesos de preferencias y controles del algoritmo.

Cada valor numérico lleva su procedencia ("fuente" o "supuesto") para separar
datos observados de estimaciones, como exige el plan del proyecto.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

# Área de estudio (left, bottom, right, top) en grados: corredor Centro–La Estrella,
# San Javier y Oriente, para que las tres líneas de transporte queden conectadas a OSM.
BBOX = (-75.645, 6.135, -75.525, 6.275)

MODES = ("carro", "bicicleta", "metro")

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
    speed_bike_kmh: float = 15.0  # informativa; la bicicleta optimiza distancia
    walk_speed_kmh: float = 4.5  # SUPUESTO para tramos a pie de la alternativa Metro

    # Congestión: factor multiplicativo sobre la velocidad en horas pico (0 < f <= 1) — SUPUESTO
    peak_hours: tuple = (6, 7, 8, 17, 18, 19)
    peak_factor: float = 0.55
    shoulder_hours: tuple = (9, 12, 13, 16, 20)
    shoulder_factor: float = 0.8

    # Carro (gasolina)
    car_consumption_l_100km: float = 8.0  # SUPUESTO: consumo urbano típico de un carro particular
    gasoline_price_cop_gal: float = 16251.0  # FUENTE: precio de referencia Medellín nov-2026 (CREG/MinEnergía)
    gasoline_kgco2_l: float = 2.31  # SUPUESTO (≈ factor IPCC 2006); verificar con calculadora FECOC de UPME

    # Metro: tarifa frecuente de 2026 y velocidades/espera estimadas.
    metro_speed_kmh: float = 35.0
    metro_boarding_min: float = 5.0
    metro_fare_cop: float = 3820.0

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
    "metro_fare": "Publimetro (ene-2026): tarifa frecuente Metro Medellín $3.820. https://www.publimetro.co/noticias/2026/01/09/asi-quedaron-las-tarifas-de-transporte-publico-en-medellin-pasaje-del-metro-subio-a-3820-pesos/",
    "osm": "© OpenStreetMap contributors (ODbL), descargado con OSMnx.",
}
