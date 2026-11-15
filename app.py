"""Dashboard del Copiloto de Movilidad (Streamlit).

Ejecutar:  streamlit run app.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from dataclasses import asdict
from pathlib import Path

import altair as alt
import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from movilidad.agent import LLMConfigError, MobilityAgent  # noqa: E402
from movilidad.config import BBOX, MODES, SOURCES, AlgoParams, EnvParams, Weights  # noqa: E402
from movilidad.data import (DATA_STATUS, PLACES, DataAccessError, load_metro_stations,
                            metro_line_a_geometry)  # noqa: E402
from movilidad.planner import Planner  # noqa: E402
from movilidad.rag import DocIndex  # noqa: E402

st.set_page_config(page_title="Copiloto de Movilidad – Valle de Aburrá", page_icon="🚦", layout="wide")
MODE_COLORS = {"carro": "#c0392b", "bicicleta": "#1e8449", "metro": "#7d3c98"}
MODE_LABELS = {"carro": "Carro", "bicicleta": "Bicicleta / a pie", "metro": "A pie + Metro (Línea A)"}
CUSTOM = "📍 Coordenadas personalizadas"


# ------------------------------------------------------------------ recursos
@st.cache_resource(show_spinner="Cargando red vial de OpenStreetMap (la primera vez tarda ~1 min)…")
def get_planner() -> Planner:
    p = Planner()
    p.graph("carro")
    p.graph("bicicleta")
    return p


@st.cache_resource(show_spinner="Construyendo índice RAG…")
def get_index() -> DocIndex:
    return DocIndex()


@st.cache_data(show_spinner=False)
def get_stations():
    try:
        return load_metro_stations()
    except DataAccessError:
        return []


def build_route_map(shown_plans):
    fmap = folium.Map(location=[(BBOX[1] + BBOX[3]) / 2, (BBOX[0] + BBOX[2]) / 2], zoom_start=13,
                      tiles="OpenStreetMap")
    stations_data = get_stations()
    line_a = metro_line_a_geometry(stations_data)
    if len(line_a) > 1:
        folium.PolyLine(
            line_a, color="#9b59b6", weight=3, opacity=0.55, dash_array="6 8",
            tooltip="Línea A esquemática; estaciones conectadas en orden",
        ).add_to(fmap)
    stations = folium.FeatureGroup("Estaciones Metro / Metroplús")
    for station in stations_data:
        folium.CircleMarker(
            [station["lat"], station["lon"]], radius=5, color="#7d3c98", fill=True, fill_opacity=0.9,
            tooltip=f"{station['line']}: {station['name']}",
        ).add_to(stations)
    stations.add_to(fmap)
    for mode, route in shown_plans.items():
        legs = route.legs or [{
            "mode": mode, "geometry": route.geometry, "time_min": route.time_min, "description": MODE_LABELS[mode],
        }]
        for leg in legs:
            if len(leg["geometry"]) < 2:
                continue
            leg_mode = leg["mode"]
            color = "#1e8449" if leg_mode == "a pie" else MODE_COLORS[leg_mode]
            folium.PolyLine(
                leg["geometry"], color=color, weight=7 if leg_mode == "metro" else 5, opacity=0.9,
                tooltip=f"{MODE_LABELS[mode]} · {leg['description']} ({leg['time_min']:.1f} min)",
            ).add_to(fmap)
    any_plan = next(iter(shown_plans.values()), None)
    if any_plan:
        folium.Marker(any_plan.origin, tooltip="Origen", icon=folium.Icon(color="green", icon="play")).add_to(fmap)
        folium.Marker(any_plan.destination, tooltip="Destino", icon=folium.Icon(color="red", icon="flag")).add_to(fmap)
    folium.LayerControl().add_to(fmap)
    return fmap


@st.cache_data(show_spinner="Calculando tiempos por hora del día…")
def hourly_profile(origin, destination, env_json: str, w_json: str):
    env, w = EnvParams(**json.loads(env_json)), Weights(**json.loads(w_json))
    rows = []
    for m in MODES:
        hours = range(24) if m != "metro" else (8,)
        for h in hours:
            p = get_planner().plan(origin, destination, m, h, env, w)
            if p.found:
                profile_hours = range(24) if m == "metro" else (h,)
                rows.extend({"hora": profile_hour, "modo": MODE_LABELS[m], "tiempo_min": round(p.time_min, 1)}
                            for profile_hour in profile_hours)
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ barra lateral
st.sidebar.title("🚦 Copiloto de movilidad")
st.sidebar.caption("Área: Centro – Laureles – El Poblado (Medellín). Datos viales: © OpenStreetMap.")


def place_input(label, default):
    opts = list(PLACES) + [CUSTOM]
    choice = st.sidebar.selectbox(label, opts, index=opts.index(default))
    if choice == CUSTOM:
        txt = st.sidebar.text_input(f"{label} (lat, lon)", "6.2442, -75.5812",
                                    help=f"Debe estar dentro del área: lat {BBOX[1]}–{BBOX[3]}, lon {BBOX[0]}–{BBOX[2]}")
        return txt
    return choice


origin = place_input("Origen", "Universidad EAFIT")
destination = place_input("Destino", "Universidad de Antioquia")
hour = st.sidebar.slider("Hora de salida (hora local)", 0, 23, 8,
                         help="Cambia el factor de congestión del carro; el Metro no usa horarios publicados.")
modes = st.sidebar.multiselect("Alternativas de transporte", list(MODES), default=list(MODES),
                               format_func=lambda mode: MODE_LABELS[mode])
st.sidebar.caption("La alternativa Metro combina caminata por OSM con estaciones de Línea A.")

d = EnvParams()
with st.sidebar.expander("1 · Parámetros del entorno", expanded=False):
    st.caption("Definen el costo físico de cada tramo. Son **supuestos ajustables** salvo los marcados como fuente.")
    st.markdown("**Velocidad base del carro (km/h) a flujo libre**")
    speed_car = {c: st.number_input(f"Carro – {c}", 5.0, 100.0, v, 5.0, key=f"car_{c}") for c, v in d.speed_car.items()}
    speed_bike = st.number_input("Bicicleta (km/h, informativa)", 5.0, 35.0, d.speed_bike_kmh, 1.0)
    walk_speed = st.number_input("Caminata hacia/desde Metro (km/h, supuesto)", 2.0, 8.0, d.walk_speed_kmh, 0.5)
    peak = st.slider("Factor de congestión en hora pico (6–8 h, 17–19 h)", 0.2, 1.0, d.peak_factor, 0.05,
                     help="Multiplica la velocidad del carro. 1 = sin congestión.")
    shoulder = st.slider("Factor en horas intermedias (9, 12, 13, 16, 20 h)", 0.2, 1.0, d.shoulder_factor, 0.05)
    cons = st.number_input("Consumo del carro (L/100 km)", 3.0, 25.0, d.car_consumption_l_100km, 0.5)
    price = st.number_input("Precio gasolina (COP/galón)", 0.0, 40000.0, d.gasoline_price_cop_gal, 100.0,
                            help="Fuente: CREG/MinEnergía, Medellín nov-2026.")
    metro_speed = st.number_input("Velocidad promedio Metro (km/h, supuesto)", 5.0, 80.0, d.metro_speed_kmh, 1.0)
    metro_wait = st.number_input("Espera para abordar Metro (min, supuesto)", 0.0, 30.0, d.metro_boarding_min, 1.0)
    metro_fare = st.number_input("Tarifa Metro frecuente (COP)", 0.0, 10000.0, d.metro_fare_cop, 50.0,
                                 help="Referencia documental 2026; tarifa individual y perfil pueden variar.")
env = EnvParams(
    speed_car=speed_car,
    speed_bike_kmh=speed_bike,
    walk_speed_kmh=walk_speed,
    peak_factor=peak,
    shoulder_factor=shoulder,
    car_consumption_l_100km=cons,
    gasoline_price_cop_gal=price,
    metro_speed_kmh=metro_speed,
    metro_boarding_min=metro_wait,
    metro_fare_cop=metro_fare,
)

with st.sidebar.expander("2 · Preferencias (pesos del costo)", expanded=True):
    st.caption("Costo = w_d·km + w_t·min + w_c·(miles COP) + w_e·(100 g CO₂). Bicicleta minimiza distancia.")
    weights = Weights(
        distance=st.slider("Peso distancia", 0.0, 5.0, 0.0, 0.1),
        time=st.slider("Peso tiempo", 0.0, 5.0, 1.0, 0.1),
        cost=st.slider("Peso costo", 0.0, 5.0, 0.0, 0.1),
        emissions=st.slider("Peso emisiones", 0.0, 5.0, 0.0, 0.1),
    )

with st.sidebar.expander("3 · Algoritmo de búsqueda", expanded=False):
    algo_name = st.radio("Algoritmo", ["astar", "dijkstra", "bfs"], horizontal=True,
                         help="A* y Dijkstra son óptimos; BFS minimiza número de tramos (línea base).")
    hw = st.slider("Intensidad de la heurística A* (0–1)", 0.0, 1.0, 1.0, 0.05,
                   help="0 equivale a Dijkstra. Se limita a 1 para que la heurística siga siendo admisible.",
                   disabled=algo_name != "astar")
algo = AlgoParams(algo_name, hw).clamp()

# ------------------------------------------------------------------ cálculo
st.title("Copiloto de movilidad: rutas con A* y asistente RAG")
try:
    planner = get_planner()
except DataAccessError as exc:
    st.error(str(exc))
    st.stop()
for net, status in DATA_STATUS.items():
    (st.sidebar.warning if "PLAN B" in status else st.sidebar.caption)(f"Red '{net}': {status}")

try:
    weights.validate()
    plans = {m: planner.plan(origin, destination, m, hour, env, weights, algo) for m in modes}
except ValueError as exc:
    st.error(f"Parámetros inválidos: {exc}")
    st.stop()

tab_routes, tab_hours, tab_chat, tab_eval = st.tabs(["🗺️ Rutas", "⏱️ Hora del día", "💬 Asistente", "📊 Evaluación"])

with tab_routes:
    if not modes:
        st.info("Seleccione al menos un modo en la barra lateral.")
    found_plans = {m: p for m, p in plans.items() if p.found}
    winner = min(found_plans.values(), key=lambda route: route.selection_cost, default=None)
    rows = []
    for m, p in plans.items():
        rows.append({"Modo": f"🏆 {MODE_LABELS[m]}" if winner is p else MODE_LABELS[m],
                     "Distancia (km)": round(p.distance_km, 2), "Tiempo (min)": round(p.time_min, 1),
                     "Costo (COP)": round(p.cost_cop), "CO₂ (kg)": round(p.co2_kg, 3),
                     "Puntaje de preferencias": round(p.selection_cost, 3),
                     "Nodos expandidos": p.expanded, "Búsqueda (ms)": round(p.runtime_ms, 1),
                     "Nota": p.message if p.found else f"⚠️ {p.message}"})
    col_map, col_tab = st.columns([3, 2])
    with col_map:
        winner_tab, all_routes_tab = st.tabs(["🏆 Ruta ganadora", "🌐 Todas las rutas"])
        with winner_tab:
            if winner:
                st.caption(f"Menor puntaje con las preferencias actuales: {MODE_LABELS[winner.mode]}.")
                st_folium(build_route_map({winner.mode: winner}), height=520, use_container_width=True,
                          returned_objects=[], key="winner_route_map")
            else:
                st.info("No se encontró una ruta ganadora para los modos seleccionados.")
        with all_routes_tab:
            st_folium(build_route_map(found_plans), height=520, use_container_width=True,
                      returned_objects=[], key="all_route_map")
        st.caption("Rojo: carro · Verde: bicicleta / a pie · Morado: estaciones de Metro. "
                   "La Línea A se dibuja esquemáticamente entre estaciones; sus tramos no son geometría ferroviaria oficial.")
    with col_tab:
        st.subheader("Comparación de modos")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        found = [r for r in rows if r["Tiempo (min)"] > 0]
        if found:
            long = pd.DataFrame(found).melt(id_vars="Modo", value_vars=["Tiempo (min)", "Costo (COP)", "CO₂ (kg)"])
            chart = alt.Chart(long).mark_bar().encode(
                x=alt.X("value:Q", title=None), y=alt.Y("Modo:N", title=None),
                color=alt.Color("Modo:N", scale=alt.Scale(domain=list(MODE_LABELS.values()), range=list(MODE_COLORS.values())),
                                legend=None),
                tooltip=["Modo", "variable", "value"],
            ).properties(height=80).facet(row=alt.Row("variable:N", title=None)).resolve_scale(x="independent")
            st.altair_chart(chart, width="stretch")

    st.subheader("A* frente a Dijkstra para esta consulta")
    comp = []
    for m in (mode for mode in modes if mode != "metro"):
        for a in ("astar", "dijkstra", "bfs"):
            p = planner.plan(origin, destination, m, hour, env, weights, AlgoParams(a, hw if a == "astar" else 1.0))
            comp.append({"Modo": MODE_LABELS[m], "Algoritmo": a, "Nodos expandidos": p.expanded,
                         "Costo ponderado": round(p.weighted_cost, 4), "Tiempo (min)": round(p.time_min, 1)})
    st.dataframe(pd.DataFrame(comp), hide_index=True, width="stretch")
    if "metro" in modes:
        st.caption("La alternativa a pie + Metro compara estaciones y estima tiempo; no corresponde a una búsqueda A* en las vías férreas.")

    st.subheader("Detalle por tramo")
    found_modes = [m for m, p in plans.items() if p.found]
    if found_modes:
        sel = st.selectbox("Modo", found_modes, format_func=lambda mode: MODE_LABELS[mode])
        seg = pd.DataFrame(plans[sel].segments)
        st.dataframe(seg, hide_index=True, width="stretch", height=280)

with tab_hours:
    st.subheader("Tiempo estimado de viaje según la hora de salida")
    st.caption("Recalcula la ruta por hora para carro; la caminata + Metro se mantiene constante porque no se modelan horarios ni variación temporal.")
    prof = hourly_profile(origin, destination, json.dumps(asdict(env)), json.dumps(asdict(weights)))
    if prof.empty:
        st.warning("No hay ruta para estos puntos.")
    else:
        line = alt.Chart(prof).mark_line(point=True).encode(
            x=alt.X("hora:Q", title="Hora de salida", scale=alt.Scale(domain=[0, 23])),
            y=alt.Y("tiempo_min:Q", title="Tiempo (min)"),
            color=alt.Color(
                "modo:N",
                scale=alt.Scale(domain=list(MODE_LABELS.values()), range=list(MODE_COLORS.values())),
            ),
            tooltip=["hora", "modo", "tiempo_min"])
        rule = alt.Chart(pd.DataFrame({"hora": [hour]})).mark_rule(strokeDash=[4, 4]).encode(x="hora:Q")
        st.altair_chart(line + rule, width="stretch")

with tab_chat:
    st.subheader("Asistente (LLM + RAG + herramientas)")
    st.caption("Usa la hora, los parámetros y los pesos del dashboard. Herramientas: plan_route, compare_modes, "
               "search_docs, check_pico_y_placa, nearest_metro_station. No es consejo legal ni de seguridad.")
    if "history" not in st.session_state:
        st.session_state.history = []
    box = st.container(height=480)
    for msg in st.session_state.history:
        with box.chat_message(msg["role"]):
            st.markdown(msg["content"])
            for tc in msg.get("tools", []):
                with st.expander(f"🔧 {tc['name']}({json.dumps(tc['args'], ensure_ascii=False)})"):
                    st.json(tc["result"])
    q = st.chat_input("Ej.: ¿Puedo ir en carro de placa 236 de EAFIT al Estadio hoy a las 6 p. m.?")
    if q:
        st.session_state.history.append({"role": "user", "content": q})
        with box.chat_message("user"):
            st.markdown(q)
        with box.chat_message("assistant"):
            with st.spinner("Pensando…"):
                agent = MobilityAgent(planner=planner, index=get_index(), env=env, weights=weights, algo=algo,
                                      hour=hour, today=dt.date.today())
                past = [{"role": m["role"], "content": m["content"]} for m in st.session_state.history[:-1]][-6:]
                try:
                    res = agent.run(q, history=past)
                    content, tools = res.answer, res.tool_calls
                except LLMConfigError as exc:
                    content, tools = f"⚙️ {exc}", []
                except Exception as exc:
                    content, tools = f"❌ Error al llamar al LLM: {type(exc).__name__}: {exc}", []
            st.markdown(content)
            for tc in tools:
                with st.expander(f"🔧 {tc['name']}({json.dumps(tc['args'], ensure_ascii=False)})"):
                    st.json(tc["result"])
        st.session_state.history.append({"role": "assistant", "content": content, "tools": tools})

with tab_eval:
    st.subheader("Benchmark A* vs. Dijkstra vs. BFS (red OSM real)")
    csv = ROOT / "eval" / "results" / "benchmark_search.csv"
    if csv.exists():
        bench = pd.read_csv(csv)
        agg = bench.groupby(["escenario", "algoritmo"], as_index=False).agg(
            expandidos=("expandidos", "mean"), optimo=("optimo", "mean"))
        bars = alt.Chart(agg).mark_bar().encode(
            x=alt.X("expandidos:Q", title="Nodos expandidos (media)"), y=alt.Y("algoritmo:N", title=None),
            color=alt.Color("algoritmo:N", legend=None), row=alt.Row("escenario:N", title=None),
            tooltip=["escenario", "algoritmo", alt.Tooltip("expandidos:Q", format=".0f"),
                     alt.Tooltip("optimo:Q", format=".0%", title="% óptimo")]).properties(height=90)
        st.altair_chart(bars, width="stretch")
    else:
        st.info("Ejecute `python eval/benchmark_search.py` para generar los resultados.")
    md = ROOT / "eval" / "results" / "agent_eval.md"
    st.subheader("Evaluación del agente")
    if md.exists():
        st.markdown(md.read_text(encoding="utf-8").split("## Respuestas")[0])
    else:
        st.info("Ejecute `python eval/run_agent_eval.py` (requiere LLM_API_KEY).")
    st.subheader("Fuentes de datos")
    for k, v in SOURCES.items():
        st.markdown(f"- **{k}**: {v}")
