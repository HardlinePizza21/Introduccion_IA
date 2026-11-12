"""Acceso a datos reales de OpenStreetMap y lugares predefinidos.

Descarga: la red se obtiene en tiempo de ejecución desde la API principal de
OpenStreetMap (https://api.openstreetmap.org/api/0.6/map) en teselas pequeñas.
Se eligió esta vía porque los servidores públicos de Overpass (los que usa OSMnx
por defecto) respondían 502/timeout por saturación durante el desarrollo.
Las vías se filtran con los mismos criterios de los tipos de red 'drive' y 'walk'
de OSMnx y el grafo se construye con `osmnx.graph_from_xml`.

Caché: las teselas crudas se guardan en `cache/osm_tiles/` y el grafo resultante
en `cache/<red>.graphml`; las ejecuciones siguientes no requieren internet.
Plan B: si la descarga falla y no hay caché, se usa la instantánea versionada en
`data/<red>.graphml.gz` (descargada de OSM el 12-nov-2026) y se avisa al usuario.
Sin descarga ni instantánea se lanza `DataAccessError` con un mensaje claro.
"""
from __future__ import annotations

import json
import math
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from .config import BBOX, road_class
from .search import haversine_m

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "cache"
TILE_DIR = CACHE / "osm_tiles"
DATA_DIR = ROOT / "data"
DATA_STATUS: dict = {}  # red -> "caché" | "descarga OSM" | "plan B: instantánea ..." 
OSM_API = "https://api.openstreetmap.org/api/0.6/map"
USER_AGENT = "SI3003-EAFIT-copiloto-movilidad/1.0 (proyecto academico)"
TILE_LON, TILE_LAT = 0.015, 0.02  # tamaño de tesela (grados)

# Lugares de referencia dentro del BBOX (lat, lon). Coordenadas aproximadas tomadas de OSM.
PLACES = {
    "Universidad EAFIT": (6.2003, -75.5783),
    "Parque Lleras": (6.2087, -75.5671),
    "Ciudad del Río": (6.2235, -75.5737),
    "Pueblito Paisa (Cerro Nutibara)": (6.2364, -75.5797),
    "Plaza Mayor": (6.2441, -75.5763),
    "Parque Berrío": (6.2502, -75.5683),
    "Estadio Atanasio Girardot": (6.2566, -75.5900),
    "Universidad de Antioquia": (6.2675, -75.5686),
    "Parque de los Deseos": (6.2695, -75.5658),
    "Parque del Poblado": (6.2100, -75.5705),
    "Centro Comercial El Tesoro": (6.1990, -75.5585),
    "Unicentro Medellín": (6.2411, -75.5868),
}

# Filtros equivalentes a los tipos de red de OSMnx (osmnx/_overpass.py).
_EXCLUDE = {
    "drive": {"abandoned", "bridleway", "bus_guideway", "construction", "corridor", "cycleway", "elevator",
              "escalator", "footway", "no", "path", "pedestrian", "planned", "platform", "proposed", "raceway",
              "razed", "service", "steps", "track"},
    "walk": {"abandoned", "bus_guideway", "construction", "cycleway", "motor", "no", "planned", "platform",
             "proposed", "raceway", "razed", "motorway", "motorway_link"},
}


class DataAccessError(RuntimeError):
    """Error al obtener datos externos (OpenStreetMap)."""


@dataclass
class Edge:
    u: int
    v: int
    length_m: float
    road_class: str
    name: str
    geometry: list  # [(lat, lon), ...]


@dataclass
class RoadGraph:
    network_type: str
    coords: dict = field(default_factory=dict)  # node -> (lat, lon)
    edges: list = field(default_factory=list)  # list[Edge]; edge_id = índice

    def nearest_node(self, latlon: tuple[float, float]) -> tuple[int, float]:
        """Nodo más cercano (búsqueda lineal; el grafo es pequeño)."""
        best, best_d = None, math.inf
        lat0, lon0 = latlon
        coslat = math.cos(math.radians(lat0))
        for n, (lat, lon) in self.coords.items():
            d = (lat - lat0) ** 2 + ((lon - lon0) * coslat) ** 2
            if d < best_d:
                best, best_d = n, d
        return best, haversine_m(latlon, self.coords[best])


# ---------------------------------------------------------------- descarga
def _fetch_tile(left, bottom, right, top, depth=0) -> list[Path]:
    """Descarga una tesela; si excede el límite de nodos de la API (HTTP 400) se divide en 4."""
    import requests

    path = TILE_DIR / f"{left:.4f}_{bottom:.4f}_{right:.4f}_{top:.4f}.osm"
    if path.exists() and path.stat().st_size > 0:
        return [path]
    last = None
    for attempt in range(4):
        try:
            r = requests.get(OSM_API, params={"bbox": f"{left},{bottom},{right},{top}"},
                             headers={"User-Agent": USER_AGENT}, timeout=120)
        except requests.RequestException as exc:
            last = exc
            time.sleep(2 ** attempt)
            continue
        if r.status_code == 200:
            TILE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_bytes(r.content)
            return [path]
        if r.status_code == 400 and depth < 4:  # demasiados nodos: dividir
            mx, my = (left + right) / 2, (bottom + top) / 2
            out = []
            for box in ((left, bottom, mx, my), (mx, bottom, right, my), (left, my, mx, top), (mx, my, right, top)):
                out += _fetch_tile(*box, depth=depth + 1)
            return out
        last = f"HTTP {r.status_code}: {r.text[:120]}"
        time.sleep(2 ** attempt)
    raise DataAccessError(f"No fue posible descargar datos de OpenStreetMap ({last}). "
                          "Verifique la conexión a internet y vuelva a intentar.")


def download_tiles() -> list[Path]:
    left, bottom, right, top = BBOX
    paths = []
    lat = bottom
    while lat < top - 1e-9:
        lon = left
        while lon < right - 1e-9:
            paths += _fetch_tile(round(lon, 4), round(lat, 4), round(min(lon + TILE_LON, right), 4),
                                 round(min(lat + TILE_LAT, top), 4))
            lon += TILE_LON
        lat += TILE_LAT
    return paths


def _keep_way(tags: dict, network_type: str) -> bool:
    hw = tags.get("highway")
    if not hw or tags.get("area") == "yes" or hw in _EXCLUDE[network_type]:
        return False
    if tags.get("access") in ("private", "no") and network_type == "drive":
        return False
    if network_type == "drive" and (tags.get("motor_vehicle") == "no" or tags.get("motorcar") == "no"):
        return False
    if network_type == "walk" and (tags.get("foot") == "no" or tags.get("service") == "private"):
        return False
    return True


def build_osm_xml(network_type: str, tiles: list[Path]) -> Path:
    """Une las teselas en un único .osm con solo las vías del tipo de red pedido."""
    nodes, ways = {}, {}
    for p in tiles:
        root = ET.parse(p).getroot()
        for el in root:
            if el.tag == "node":
                nodes.setdefault(el.get("id"), el)
            elif el.tag == "way":
                tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
                if _keep_way(tags, network_type):
                    ways.setdefault(el.get("id"), el)
    out = ET.Element("osm", version="0.6", generator="SI3003-tiles")
    used = {nd.get("ref") for w in ways.values() for nd in w.findall("nd")}
    for nid in used:
        if nid in nodes:
            out.append(nodes[nid])
    for w in ways.values():
        if all(nd.get("ref") in nodes for nd in w.findall("nd")):
            out.append(w)
    path = CACHE / f"{network_type}.osm"
    ET.ElementTree(out).write(path, encoding="utf-8", xml_declaration=True)
    return path


# ---------------------------------------------------------------- grafos
def from_networkx(G, network_type: str) -> RoadGraph:
    """Convierte el MultiDiGraph de OSMnx a la estructura propia del proyecto."""
    rg = RoadGraph(network_type)
    for n, d in G.nodes(data=True):
        rg.coords[n] = (float(d["y"]), float(d["x"]))
    for u, v, d in G.edges(data=True):
        geom = d.get("geometry")
        geom = [(y, x) for x, y in geom.coords] if geom is not None else [rg.coords[u], rg.coords[v]]
        name = d.get("name", "")
        if isinstance(name, list):
            name = " / ".join(map(str, name))
        rg.edges.append(Edge(u, v, float(d["length"]), road_class(d.get("highway", "")), str(name or ""), geom))
    return rg


def load_graph(network_type: str, refresh: bool = False) -> RoadGraph:
    """Red OSM del área: 'drive' (carro/bus, respeta sentidos) o 'walk' (bicicleta, bidireccional)."""
    if network_type not in ("drive", "walk"):
        raise ValueError("network_type debe ser 'drive' o 'walk'")
    import osmnx as ox

    CACHE.mkdir(parents=True, exist_ok=True)
    snapshot = CACHE / f"{network_type}.graphml"
    if snapshot.exists() and not refresh:
        G = ox.load_graphml(snapshot)
        DATA_STATUS[network_type] = "caché local de una descarga OSM previa"
    else:
        try:
            xml = build_osm_xml(network_type, download_tiles())
            G = ox.graph_from_xml(xml, bidirectional=(network_type == "walk"), simplify=True, retain_all=False)
            G = ox.truncate.truncate_graph_bbox(G, BBOX)
            G = ox.truncate.largest_component(G, strongly=True)
            DATA_STATUS[network_type] = "descarga en vivo de la API de OpenStreetMap"
        except DataAccessError:
            backup = DATA_DIR / f"{network_type}.graphml.gz"
            if not backup.exists():
                raise
            import gzip
            import shutil

            with gzip.open(backup, "rb") as src, open(snapshot, "wb") as dst:
                shutil.copyfileobj(src, dst)
            DATA_STATUS[network_type] = "PLAN B: instantánea OSM versionada (data/, 12-nov-2026)"
            return from_networkx(ox.load_graphml(snapshot), network_type)
        ox.save_graphml(G, snapshot)
    return from_networkx(G, network_type)


def load_metro_stations() -> list[dict]:
    """Estaciones del sistema Metro (metro, tranvía, cable, Metroplús) dentro del BBOX.

    En OSM las estaciones de Medellín se modelan como nodos `public_transport=stop_position|station`
    con `network=Metro de Medellín` (o Metroplús); se agrupan por nombre y se promedian coordenadas.
    """
    snapshot = CACHE / "metro_stations.json"
    if snapshot.exists():
        cached = json.loads(snapshot.read_text(encoding="utf-8"))
        if cached:
            return cached
    left, bottom, right, top = BBOX
    groups: dict = {}
    try:
        tiles = download_tiles()
    except DataAccessError:
        return json.loads((DATA_DIR / "metro_stations.json").read_text(encoding="utf-8"))
    for p in tiles:
        for el in ET.parse(p).getroot().iter("node"):
            tags = {t.get("k"): t.get("v") for t in el.findall("tag")}
            network = tags.get("network", "")
            name = tags.get("name")
            if not name or "metro" not in network.lower() or name.lower().startswith("estación"):
                continue
            if tags.get("public_transport") not in ("stop_position", "station", "platform") and                     tags.get("railway") not in ("station", "halt", "tram_stop"):
                continue
            lat, lon = float(el.get("lat")), float(el.get("lon"))
            if not (bottom <= lat <= top and left <= lon <= right):
                continue
            if tags.get("subway") == "yes" or tags.get("train") == "yes":
                kind = "Metro"
            elif tags.get("tram") == "yes" or tags.get("railway") == "tram_stop":
                kind = "Tranvía"
            elif tags.get("aerialway") or tags.get("gondola") == "yes":
                kind = "Metrocable"
            else:
                kind = "Metroplús" if "plús" in network.lower() or "plus" in network.lower() else "Metro"
            key = (name, kind)
            g = groups.setdefault(key, {"lat": [], "lon": []})
            g["lat"].append(lat)
            g["lon"].append(lon)
    stations = [{"name": n, "line": k, "lat": sum(g["lat"]) / len(g["lat"]), "lon": sum(g["lon"]) / len(g["lon"])}
                for (n, k), g in sorted(groups.items())]
    CACHE.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(json.dumps(stations, ensure_ascii=False, indent=1), encoding="utf-8")
    return stations


def resolve_place(place) -> tuple[float, float]:
    """Acepta el nombre de un lugar predefinido o una cadena/tupla 'lat, lon'."""
    if isinstance(place, (tuple, list)) and len(place) == 2:
        return float(place[0]), float(place[1])
    text = str(place).strip()
    for name, latlon in PLACES.items():
        if name.lower() == text.lower():
            return latlon
    matches = [n for n in PLACES if text.lower() in n.lower()]
    if len(matches) == 1:
        return PLACES[matches[0]]
    try:
        lat, lon = (float(x) for x in text.split(","))
        return lat, lon
    except ValueError:
        pass
    raise ValueError(f"Lugar desconocido: '{place}'. Use uno de {list(PLACES)} o 'lat, lon'.")
