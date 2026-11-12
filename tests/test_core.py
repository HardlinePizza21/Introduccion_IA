"""Pruebas de búsqueda, heurística, costos, pico y placa y RAG (sin red ni LLM)."""
import datetime as dt
import math
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from movilidad import pico_placa  # noqa: E402
from movilidad.agent import MobilityAgent  # noqa: E402
from movilidad.config import AlgoParams, EnvParams, Weights  # noqa: E402
from movilidad.data import Edge, RoadGraph  # noqa: E402
from movilidad.planner import Planner, build_adjacency, edge_metrics  # noqa: E402
from movilidad.rag import DocIndex  # noqa: E402
from movilidad.search import astar, bfs, dijkstra, haversine_m, make_heuristic  # noqa: E402


def grid_graph(n=12, seed=0):
    """Grilla n×n (~110 m entre nodos) con longitudes >= distancia recta y clases de vía aleatorias."""
    rnd = random.Random(seed)
    g = RoadGraph("drive")
    for i in range(n):
        for j in range(n):
            g.coords[i * n + j] = (6.20 + i * 0.001, -75.58 + j * 0.001)
    classes = ["troncal", "arteria", "colectora", "local"]
    for i in range(n):
        for j in range(n):
            u = i * n + j
            for di, dj in ((0, 1), (1, 0), (0, -1), (-1, 0)):
                a, b = i + di, j + dj
                if 0 <= a < n and 0 <= b < n:
                    v = a * n + b
                    L = haversine_m(g.coords[u], g.coords[v]) * rnd.uniform(1.0, 1.6)
                    g.edges.append(Edge(u, v, L, rnd.choice(classes), "", [g.coords[u], g.coords[v]]))
    return g


@pytest.fixture(scope="module")
def grid_planner():
    return Planner({"drive": grid_graph(), "walk": grid_graph(seed=1)})


def test_haversine_known_distance():
    # 0.001° de latitud ≈ 111 m
    assert 110 < haversine_m((6.2, -75.58), (6.201, -75.58)) < 112


@pytest.mark.parametrize("weights", [Weights(time=1), Weights(distance=1), Weights(cost=1), Weights(emissions=1),
                                     Weights(distance=0.3, time=1, cost=0.5, emissions=2)])
@pytest.mark.parametrize("hour", [3, 8, 13])
def test_astar_matches_dijkstra_and_expands_less(weights, hour):
    g = grid_graph()
    adj, _m, k = build_adjacency(g, "carro", hour, EnvParams(), weights)
    rnd = random.Random(42)
    for _ in range(10):
        s, t = rnd.sample(list(g.coords), 2)
        d = dijkstra(adj, s, t)
        a = astar(adj, s, t, make_heuristic(g.coords, t, k))
        assert math.isclose(a.cost, d.cost, rel_tol=1e-9)
        assert a.expanded <= d.expanded


def test_heuristic_is_consistent():
    g = grid_graph()
    adj, _m, k = build_adjacency(g, "carro", 8, EnvParams(), Weights(time=1, emissions=1))
    goal = 77
    h = make_heuristic(g.coords, goal, k)
    for u, outs in adj.items():
        for v, c, _ in outs:
            assert h(u) <= c + h(v) + 1e-12
    assert h(goal) == 0


def test_heuristic_weight_out_of_range_rejected():
    with pytest.raises(ValueError):
        make_heuristic({0: (6.2, -75.5)}, 0, 1.0, weight=1.5)
    assert AlgoParams(heuristic_weight=3).clamp().heuristic_weight == 1.0


def test_negative_weights_rejected():
    with pytest.raises(ValueError):
        build_adjacency(grid_graph(), "carro", 8, EnvParams(), Weights(time=-1))


def test_bfs_minimizes_hops_not_cost():
    adj = {0: [(1, 10.0, 0), (2, 1.0, 1)], 1: [(3, 10.0, 2)], 2: [(4, 1.0, 3)], 4: [(3, 1.0, 4)], 3: []}
    assert bfs(adj, 0, 3).path == [0, 1, 3]
    assert dijkstra(adj, 0, 3).path == [0, 2, 4, 3]
    assert dijkstra(adj, 0, 3).cost == 3.0


def test_unreachable_goal():
    adj = {0: [(1, 1.0, 0)], 1: [], 2: []}
    assert not astar(adj, 0, 2).found


def test_congestion_slows_car_and_changes_cost():
    e = Edge(0, 1, 1000.0, "arteria", "Calle", [])
    env = EnvParams()
    free, peak = edge_metrics(e, "carro", 3, env), edge_metrics(e, "carro", 8, env)
    assert peak.speed_kmh == pytest.approx(free.speed_kmh * env.peak_factor)
    assert peak.time_s > free.time_s
    # 1 km a 8 L/100 km = 0,08 L
    assert free.money_cop == pytest.approx(0.08 * env.gasoline_price_cop_l)
    assert free.co2_kg == pytest.approx(0.08 * env.gasoline_kgco2_l)


def test_parameter_change_changes_route_metrics(grid_planner):
    o, d = (6.200, -75.580), (6.211, -75.569)
    base = grid_planner.plan(o, d, "carro", 3)
    slow = grid_planner.plan(o, d, "carro", 3, env=EnvParams(speed_car={k: 10.0 for k in EnvParams().speed_car}))
    assert slow.time_min > base.time_min
    cheap = grid_planner.plan(o, d, "carro", 3, env=EnvParams(gasoline_price_cop_gal=0.0))
    assert cheap.cost_cop == 0


def test_bus_cost_is_fare(grid_planner):
    p = grid_planner.plan((6.200, -75.580), (6.211, -75.569), "bus", 8)
    assert p.found and p.cost_cop == pytest.approx(EnvParams().bus_fare_cop)


def test_bike_optimizes_distance(grid_planner):
    o, d = (6.200, -75.580), (6.211, -75.569)
    a = grid_planner.plan(o, d, "bicicleta", 8, weights=Weights(time=1))
    b = grid_planner.plan(o, d, "bicicleta", 8, weights=Weights(distance=1))
    assert a.distance_km == pytest.approx(b.distance_km) and a.co2_kg == 0


def test_far_point_reported(grid_planner):
    p = grid_planner.plan((6.0, -75.0), (6.211, -75.569), "carro", 8)
    assert not p.found and "fuera del área" in p.message


@pytest.mark.parametrize("plate,date,expected", [
    ("ABC125", "2026-11-09", True),   # lunes, 5
    ("ABC128", "2026-11-09", True),   # lunes, 8
    ("ABC123", "2026-11-09", False),
    ("XYZ990", "2026-11-11", True),   # miércoles, 0
    ("XYZ997", "2026-11-13", True),   # viernes, 7
    ("XYZ997", "2026-11-14", False),  # sábado
])
def test_pico_y_placa(plate, date, expected):
    assert pico_placa.check(plate, date)["restringido"] is expected


def test_pico_y_placa_hour_exempt_and_moto():
    assert pico_placa.check("ABC125", "2026-11-09", hour=21)["restringido"] is False
    assert pico_placa.check("ABC125", "2026-11-09", fuel="eléctrico")["restringido"] is False
    assert pico_placa.check("5AB12C", "2026-11-09", vehicle="moto")["digito_evaluado"] == 5
    assert pico_placa.check("ABC125", "2027-03-01")["restringido"] is None
    with pytest.raises(ValueError):
        pico_placa.check("ABC125", "09/11/2026")


def test_rag_tfidf_retrieves_relevant_doc():
    ix = DocIndex(backend="tfidf")
    top = ix.search("rotación de dígitos pico y placa miércoles", k=1)[0]
    assert top["documento"] == "pico_y_placa_2026_2.md"
    assert ix.search("tarifa Metro tarjeta Cívica frecuente", k=1)[0]["documento"] == "tarifas_transporte_2026.md"


def test_agent_tool_errors_are_observations(grid_planner):
    ag = MobilityAgent(planner=grid_planner, index=DocIndex(backend="tfidf"), today=dt.date(2026, 11, 12))
    assert "error" in ag.call_tool("plan_route", {"origin": "Narnia", "destination": "Plaza Mayor", "mode": "carro"})
    assert "error" in ag.call_tool("no_existe", {})
    assert "error" in ag.call_tool("plan_route", {"foo": 1})
    ok = ag.call_tool("check_pico_y_placa", {"plate": "AAA111", "date": "2026-11-10"})
    assert ok["restringido"] is True


def test_plan_b_snapshot_used_when_download_fails(tmp_path, monkeypatch):
    from movilidad import data

    def fail():
        raise data.DataAccessError("sin conexión (simulado)")

    monkeypatch.setattr(data, "CACHE", tmp_path)
    monkeypatch.setattr(data, "download_tiles", fail)
    g = data.load_graph("drive")
    assert len(g.coords) > 1000 and "PLAN B" in data.DATA_STATUS["drive"]


class _Fn:
    def __init__(self, name, arguments):
        self.name, self.arguments = name, arguments


class _TC:
    def __init__(self, i, name, arguments):
        self.id, self.type, self.function = f"call_{i}", "function", _Fn(name, arguments)

    def model_dump(self):
        return {"id": self.id, "type": "function",
                "function": {"name": self.function.name, "arguments": self.function.arguments}}


class _Msg:
    def __init__(self, content=None, tool_calls=None):
        self.content, self.tool_calls = content, tool_calls


class _FakeClient:
    """Simula un LLM: primero pide herramientas (una con JSON inválido) y luego responde."""

    def __init__(self, script):
        self.script, self.seen = list(script), []
        self.chat = self
        self.completions = self

    def create(self, **kw):
        self.seen.append(kw["messages"])
        msg = self.script.pop(0)
        return type("R", (), {"choices": [type("C", (), {"message": msg})()]})()


def test_agent_loop_executes_tools_and_returns_answer(grid_planner):
    script = [
        _Msg(tool_calls=[_TC(1, "check_pico_y_placa", '{"plate": "AAA116", "date": "2026-11-12"}'),
                         _TC(2, "search_docs", '{"query": "rotación jueves"}'),
                         _TC(3, "plan_route", "{no es json")]),
        _Msg(content="Tiene pico y placa hoy [pico_y_placa_2026_2.md § Rotación de dígitos]."),
    ]
    fake = _FakeClient(script)
    ag = MobilityAgent(planner=grid_planner, index=DocIndex(backend="tfidf"), today=dt.date(2026, 11, 12))
    ag._client = lambda: (fake, "fake-model")
    res = ag.run("¿Puedo circular hoy con placa AAA116?")
    assert [c["name"] for c in res.tool_calls] == ["check_pico_y_placa", "search_docs", "plan_route"]
    assert res.tool_calls[0]["result"]["restringido"] is True
    assert "error" in res.tool_calls[2]["result"]
    assert "pico_y_placa_2026_2.md" in res.answer and res.iterations == 2
    tool_msgs = [m for m in fake.seen[1] if m["role"] == "tool"]
    assert len(tool_msgs) == 3


def test_agent_stops_at_tmax(grid_planner, monkeypatch):
    monkeypatch.setenv("AGENT_T_MAX", "2")
    loop = [_Msg(tool_calls=[_TC(i, "search_docs", '{"query": "metro"}')]) for i in range(5)]
    ag = MobilityAgent(planner=grid_planner, index=DocIndex(backend="tfidf"))
    ag._client = lambda: (_FakeClient(loop), "fake-model")
    res = ag.run("bucle")
    assert res.stopped_by_tmax and res.iterations == 2


def test_missing_llm_key_raises_config_error(monkeypatch):
    from movilidad import agent as agent_mod

    monkeypatch.setattr(agent_mod, "load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    with pytest.raises(agent_mod.LLMConfigError):
        MobilityAgent()._client()
