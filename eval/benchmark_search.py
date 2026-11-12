"""Evaluación cuantitativa de la técnica de la Parte 1: A* vs. Dijkstra (UCS) vs. BFS.

Para N pares origen-destino aleatorios (semilla fija) sobre la red OSM real se mide:
nodos expandidos, tiempo de búsqueda, costo de la ruta y si el costo coincide con el óptimo.

Uso:  python eval/benchmark_search.py [--pairs 100] [--seed 7]
Salida: eval/results/benchmark_search.csv y eval/results/benchmark_summary.md
"""
from __future__ import annotations

import argparse
import math
import random
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from movilidad.config import EnvParams, Weights  # noqa: E402
from movilidad.planner import NETWORK_FOR_MODE, Planner, build_adjacency  # noqa: E402
from movilidad.search import astar, bfs, dijkstra, haversine_m, make_heuristic  # noqa: E402

SCENARIOS = [
    ("carro", 8, "tiempo", Weights(time=1)),
    ("carro", 14, "multiobjetivo", Weights(distance=0.2, time=1, cost=0.5, emissions=1)),
    ("bus", 18, "tiempo", Weights(time=1)),
    ("bicicleta", 10, "distancia", Weights(distance=1)),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", type=int, default=100)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    planner, env = Planner(), EnvParams()
    rows = []
    for mode, hour, label, w in SCENARIOS:
        g = planner.graph(mode)
        adj, _m, k = build_adjacency(g, mode, hour, env, w)
        nodes = list(g.coords)
        rnd = random.Random(args.seed)
        done = 0
        while done < args.pairs:
            s, t = rnd.sample(nodes, 2)
            if haversine_m(g.coords[s], g.coords[t]) < 1000:  # pares de al menos 1 km
                continue
            d = dijkstra(adj, s, t)
            if not d.found:
                continue
            a = astar(adj, s, t, make_heuristic(g.coords, t, k))
            a05 = astar(adj, s, t, make_heuristic(g.coords, t, k, 0.5), name="astar_w0.5")
            b = bfs(adj, s, t)
            for r in (d, a, a05, b):
                rows.append({"escenario": f"{mode}-{label}-{hour}h", "red": NETWORK_FOR_MODE[mode],
                             "par": done, "algoritmo": r.algorithm, "expandidos": r.expanded,
                             "tiempo_ms": r.runtime_ms, "costo": r.cost,
                             "optimo": math.isclose(r.cost, d.cost, rel_tol=1e-9),
                             "sobrecosto_pct": 100 * (r.cost - d.cost) / d.cost if d.cost else 0.0,
                             "dist_recta_km": haversine_m(g.coords[s], g.coords[t]) / 1000})
            done += 1
        print(f"{mode}-{label}: {done} pares listos")
    df = pd.DataFrame(rows)
    out = ROOT / "eval" / "results"
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "benchmark_search.csv", index=False)

    summ = df.groupby(["escenario", "algoritmo"]).agg(
        expandidos_media=("expandidos", "mean"), tiempo_ms_media=("tiempo_ms", "mean"),
        pct_optimo=("optimo", lambda x: 100 * x.mean()), sobrecosto_pct_medio=("sobrecosto_pct", "mean"),
    ).round(2).reset_index()
    ratio = []
    for esc, grp in df.groupby("escenario"):
        piv = grp.pivot(index="par", columns="algoritmo", values="expandidos")
        ratio.append({"escenario": esc, "reduccion_expandidos_astar_vs_dijkstra_pct":
                      round(100 * (1 - (piv["astar"] / piv["dijkstra"]).mean()), 1),
                      "mediana_ratio": round(st.median(piv["astar"] / piv["dijkstra"]), 3)})
    ratio = pd.DataFrame(ratio)
    md = ["# Benchmark A* vs. Dijkstra vs. BFS", "",
          f"Pares aleatorios por escenario: {args.pairs} (semilla {args.seed}, distancia recta >= 1 km). "
          "Red: OpenStreetMap, área Centro–Laureles–El Poblado.", "",
          summ.to_markdown(index=False), "", ratio.to_markdown(index=False)]
    (out / "benchmark_summary.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
