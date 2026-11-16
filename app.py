"""Dashboard del Copiloto de Movilidad (Streamlit).

Ejecutar:  streamlit run app.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
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
                            resolve_place, transit_route_geometries)  # noqa: E402
from movilidad.planner import Planner  # noqa: E402
from movilidad.rag import DocIndex  # noqa: E402

st.set_page_config(page_title="Copiloto de Movilidad – Valle de Aburrá", page_icon="🚦", layout="wide")
MODE_COLORS = {"carro": "#c0392b", "bicicleta": "#1e8449", "metro": "#7d3c98"}
MODE_LABELS = {"carro": "Carro", "bicicleta": "Bicicleta / a pie",
               "metro": "A pie + Metro / Tranvía opcional"}
CUSTOM = "📍 Coordenadas personalizadas"
DEFAULT_DEPARTURE_HOUR = 8


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
def get_stations(cache_version: int = 3):
    try:
        return load_metro_stations(cache_version=cache_version)
    except DataAccessError:
        return []


def build_route_map(shown_plans, selected_points=None):
    fmap = folium.Map(location=[(BBOX[1] + BBOX[3]) / 2, (BBOX[0] + BBOX[2]) / 2], zoom_start=13,
                      tiles="OpenStreetMap")
    coverage = folium.FeatureGroup(name="Límite del área de cobertura")
    folium.Rectangle(
        bounds=[(BBOX[1], BBOX[0]), (BBOX[3], BBOX[2])],
        color="#f1c40f", weight=4, dash_array="8 6", fill=False,
        tooltip="Límite del área de datos OpenStreetMap",
    ).add_to(coverage)
    coverage.add_to(fmap)
    stations_data = get_stations(3)
    route_colors = {"A": "#9b59b6", "B": "#2980b9", "T": "#e67e22"}
    for route_id, geometry in transit_route_geometries(stations_data).items():
        if len(geometry) > 1:
            label = "Tranvía Línea T" if route_id == "T" else f"Línea {route_id}"
            folium.PolyLine(
                geometry, color=route_colors[route_id], weight=3, opacity=0.65, dash_array="6 8",
                tooltip=f"{label} esquemática",
            ).add_to(fmap)
    stations = folium.FeatureGroup("Estaciones Metro y Tranvía")
    for station in stations_data:
        color = "#e67e22" if station["line"] == "Tranvía" else "#7d3c98"
        folium.CircleMarker(
            [station["lat"], station["lon"]], radius=5, color=color, fill=True, fill_opacity=0.9,
            tooltip=f"{station['line']}: {station['name']}",
        ).add_to(stations)
    stations.add_to(fmap)
    fmap.fit_bounds([(BBOX[1], BBOX[0]), (BBOX[3], BBOX[2])])
    for mode, route in shown_plans.items():
        legs = route.legs or [{
            "mode": mode, "geometry": route.geometry, "time_min": route.time_min, "description": MODE_LABELS[mode],
        }]
        for leg in legs:
            if len(leg["geometry"]) < 2:
                continue
            leg_mode = leg["mode"]
            color = "#5b5fc7" if leg_mode == "a pie" else MODE_COLORS[leg_mode]
            folium.PolyLine(
                leg["geometry"], color=color, weight=7 if leg_mode == "metro" else 5, opacity=0.9,
                tooltip=f"{MODE_LABELS[mode]} · {leg['description']} ({leg['time_min']:.1f} min)",
            ).add_to(fmap)
    any_plan = next(iter(shown_plans.values()), None)
    if any_plan:
        folium.Marker(any_plan.origin, tooltip="Origen", icon=folium.Icon(color="green", icon="play")).add_to(fmap)
        folium.Marker(any_plan.destination, tooltip="Destino", icon=folium.Icon(color="red", icon="flag")).add_to(fmap)
    elif selected_points:
        if selected_points.get("origin"):
            folium.Marker(selected_points["origin"], tooltip="Origen", icon=folium.Icon(
                color="green", icon="play")).add_to(fmap)
        if selected_points.get("destination"):
            folium.Marker(selected_points["destination"], tooltip="Destino", icon=folium.Icon(
                color="red", icon="flag")).add_to(fmap)
    folium.LayerControl().add_to(fmap)
    return fmap


# ------------------------------------------------------------------ barra lateral
st.sidebar.title("🚦 Copiloto de movilidad")
st.sidebar.caption("Área de cobertura: ver límite amarillo en el mapa. Datos viales: © OpenStreetMap.")

st.session_state.setdefault("origin_choice", "Universidad EAFIT")
st.session_state.setdefault("destination_choice", "Universidad de Antioquia")
st.session_state.setdefault("origin_coordinates", "6.2442, -75.5812")
st.session_state.setdefault("destination_coordinates", "6.2442, -75.5812")
st.session_state.setdefault("location_target", "Origen")
st.session_state.setdefault("location_map_nonce", 0)

st.title("Copiloto de movilidad: rutas con A* y asistente RAG")
st.caption("Haz clic en el mapa para fijar el punto seleccionado. También puedes conservar o elegir lugares predeterminados.")

try:
    planner = get_planner()
except DataAccessError as exc:
    st.error(str(exc))
    st.stop()

location_target = st.segmented_control(
    "Al hacer clic en el mapa, seleccionar",
    ["Origen", "Destino"],
    format_func=lambda value: f"Seleccionar {value.lower()}",
    key="location_target",
)


def selected_map_point(field):
    choice = st.session_state[f"{field}_choice"]
    if choice == CUSTOM:
        try:
            return resolve_place(st.session_state[f"{field}_coordinates"])
        except ValueError:
            return None
    return PLACES.get(choice)


map_state = st_folium(
    build_route_map({}, {
        "origin": selected_map_point("origin"),
        "destination": selected_map_point("destination"),
    }),
    height=430, use_container_width=True, returned_objects=["last_clicked"],
    key=f"location_picker_{location_target}_{st.session_state.location_map_nonce}",
)
clicked = map_state.get("last_clicked") if map_state else None
if clicked:
    latitude, longitude = clicked["lat"], clicked["lng"]
    field = "origin" if location_target == "Origen" else "destination"
    if BBOX[1] <= latitude <= BBOX[3] and BBOX[0] <= longitude <= BBOX[2]:
        st.session_state[f"{field}_choice"] = CUSTOM
        st.session_state[f"{field}_coordinates"] = f"{latitude:.6f}, {longitude:.6f}"
        st.session_state["location_click_message"] = f"{location_target} fijado en el mapa."
    else:
        st.session_state["location_click_message"] = "Selecciona un punto dentro del límite amarillo."
    st.session_state.location_map_nonce += 1
    st.rerun()

location_click_message = st.session_state.pop("location_click_message", None)
if location_click_message:
    if location_click_message.startswith("Selecciona"):
        st.warning(location_click_message)
    else:
        st.success(location_click_message)


def place_input(label, field):
    opts = list(PLACES) + [CUSTOM]
    choice = st.sidebar.selectbox(label, opts, key=f"{field}_choice")
    if choice == CUSTOM:
        return st.sidebar.text_input(
            f"{label} (lat, lon)", key=f"{field}_coordinates",
            help=f"Debe estar dentro del área: lat {BBOX[1]}–{BBOX[3]}, lon {BBOX[0]}–{BBOX[2]}",
        )
    return choice


origin = place_input("Origen", "origin")
destination = place_input("Destino", "destination")
modes = st.sidebar.multiselect("Alternativas de transporte", list(MODES), default=list(MODES),
                               format_func=lambda mode: MODE_LABELS[mode])
st.sidebar.caption("La alternativa combina caminata por OSM con las líneas A/B y el Tranvía T.")

d = EnvParams()
with st.sidebar.expander("1 · Parámetros del entorno", expanded=False):
    st.caption("Definen el costo físico de cada tramo. Son **supuestos ajustables** salvo los marcados como fuente.")
    st.markdown("**Velocidad base del carro (km/h) a flujo libre**")
    speed_car = {c: st.number_input(f"Carro – {c}", 5.0, 100.0, v, 5.0, key=f"car_{c}") for c, v in d.speed_car.items()}
    speed_bike = st.number_input("Bicicleta (km/h, informativa)", 5.0, 35.0, d.speed_bike_kmh, 1.0)
    walk_speed = st.number_input("Caminata hacia/desde Metro (km/h, supuesto)", 2.0, 8.0, d.walk_speed_kmh, 0.5)
    hour_col, peak_col = st.columns(2)
    hour = hour_col.slider(
        "Hora de salida (hora local)", 0, 23, DEFAULT_DEPARTURE_HOUR, 1, format="%d:00",
        help="Se usa para estimar la congestión y planificar la ruta.",
        key="departure_hour",
    )
    peak = peak_col.slider(
        "Factor de congestión",
        0.2, 1.0, d.peak_factor, 0.05,
        help="Aplica entre 6–8 h y 17–19 h. Multiplica la velocidad del carro; 1 = sin congestión.",
    )
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
for net, status in DATA_STATUS.items():
    (st.sidebar.warning if "PLAN B" in status else st.sidebar.caption)(f"Red '{net}': {status}")

try:
    weights.validate()
    plans = {m: planner.plan(origin, destination, m, hour, env, weights, algo) for m in modes}
except ValueError as exc:
    st.error(f"Parámetros inválidos: {exc}")
    st.stop()

tab_routes, tab_chat, tab_eval = st.tabs(["🗺️ Rutas", "💬 Asistente", "📊 Evaluación"])

with tab_routes:
    if not modes:
        st.info("Seleccione al menos un modo en la barra lateral.")
    found_plans = {m: p for m, p in plans.items() if p.found}
    winner = min(found_plans.values(), key=lambda route: route.selection_cost, default=None)
    rows = []
    for m, p in plans.items():
        rows.append({"Modo": f"🏆 {MODE_LABELS[m]}" if winner is p else MODE_LABELS[m],
                     "Distancia (km)": round(p.distance_km, 2) if p.found else None,
                     "Tiempo (min)": round(p.time_min, 1) if p.found else None,
                     "Costo directo (COP)": round(p.cost_cop) if p.found else None,
                     "CO₂ (kg)": round(p.co2_kg, 3) if p.found else None,
                     "Puntaje de preferencias": round(p.selection_cost, 3) if p.found else None,
                     "Nodos expandidos": p.expanded, "Búsqueda (ms)": round(p.runtime_ms, 1),
                     "Nota": p.message if p.found else f"⚠️ {p.message}"})
    route_view = st.segmented_control(
        "Vista de rutas",
        ["🏆 Ruta ganadora", "🌐 Todas las rutas"],
        default="🏆 Ruta ganadora",
        key="route_map_view",
    )
    if route_view == "🏆 Ruta ganadora":
        if winner:
            st.caption(f"Menor puntaje con las preferencias actuales: {MODE_LABELS[winner.mode]}.")
            st_folium(build_route_map({winner.mode: winner}), height=520, use_container_width=True,
                      returned_objects=[], key="winner_route_map")
        else:
            st.info("No se encontró una ruta ganadora para los modos seleccionados.")
    elif route_view == "🌐 Todas las rutas":
        st_folium(build_route_map(found_plans), height=520, use_container_width=True,
                  returned_objects=[], key="all_route_map")
    st.caption("Rojo: carro · Verde: bicicleta · Azul-violeta: caminata · Morado: Metro · Naranja: Tranvía. "
               "Amarillo discontinuo: límite aproximado del área de cobertura de datos. "
               "Las líneas A, B y T se dibujan esquemáticamente; no son geometría ferroviaria oficial.")

    st.subheader("Comparación de modos")
    st.dataframe(
        pd.DataFrame(rows),
        column_config={
            "Costo directo (COP)": st.column_config.NumberColumn(
                format="$%,.0f",
                help="Carro: combustible estimado; Metro/Tranvía: tarifa; bicicleta: no tiene tarifa modelada.",
            ),
        },
        hide_index=True,
        width="stretch",
    )
    found_plans = {mode: plan for mode, plan in plans.items() if plan.found}
    if found_plans:
        st.caption(
            "Carro: combustible estimado (sin parqueadero ni peajes). Bici: costo y emisiones no modelados. "
            "Metro/Tranvía: tarifa frecuente estimada. Los gráficos muestran solo rutas encontradas."
        )
        chart_modes = {"carro": "Carro", "bicicleta": "Bici", "metro": "Metro/Tranvía"}
        chart_data = pd.DataFrame([
            {
                "Modo": chart_modes[mode],
                "Modo completo": MODE_LABELS[mode],
                "Distancia (km)": plan.distance_km,
                "Tiempo (min)": plan.time_min,
                "Costo (COP)": plan.cost_cop,
                "CO₂ (kg)": plan.co2_kg,
            }
            for mode, plan in found_plans.items()
        ])
        chart_specs = [
            ("Distancia (km)", "Distancia recorrida", ".1f",
             "Comparación de la distancia estimada por modo"),
            ("Tiempo (min)", "Tiempo estimado", ".1f",
             "Comparación del tiempo estimado por modo"),
            ("Costo (COP)", "Costo directo estimado", "$,.0f",
             "Comparación del costo directo estimado en pesos colombianos por modo"),
            ("CO₂ (kg)", "Emisiones estimadas", ".2f",
             "Comparación de las emisiones estimadas de dióxido de carbono por modo"),
        ]
        mode_order = list(chart_modes.values())
        color_scale = alt.Scale(
            domain=mode_order,
            range=[MODE_COLORS["carro"], MODE_COLORS["bicicleta"], MODE_COLORS["metro"]],
        )
        for row_start in range(0, len(chart_specs), 2):
            chart_columns = st.columns(2)
            for column, (field, title, value_format, alt_text) in zip(
                chart_columns, chart_specs[row_start:row_start + 2]
            ):
                with column:
                    with st.container(border=True):
                        st.markdown(f"**{title}**")
                        bars = alt.Chart(chart_data).mark_bar().encode(
                            x=alt.X(field, title=None, axis=alt.Axis(format=value_format)),
                            y=alt.Y("Modo:N", title=None, sort=mode_order),
                            color=alt.Color("Modo:N", scale=color_scale, legend=None),
                            tooltip=[
                                alt.Tooltip("Modo completo:N", title="Modo"),
                                alt.Tooltip(field, title=title, format=value_format),
                            ],
                        )
                        values = alt.Chart(chart_data).mark_text(
                            align="left", baseline="middle", dx=5,
                        ).encode(
                            x=alt.X(field, axis=alt.Axis(format=value_format)),
                            y=alt.Y("Modo:N", sort=mode_order),
                            text=alt.Text(field, format=value_format),
                        )
                        st.altair_chart(
                            (bars + values).properties(height=115),
                            width="stretch",
                            alt=alt_text,
                        )

    st.subheader("A* frente a Dijkstra para esta consulta")
    st.caption("El costo ponderado usa las unidades de las preferencias; no representa pesos colombianos.")
    comp = []
    for m in (mode for mode in modes if mode != "metro"):
        for a in ("astar", "dijkstra", "bfs"):
            p = planner.plan(origin, destination, m, hour, env, weights, AlgoParams(a, hw if a == "astar" else 1.0))
            comp.append({
                "Modo": MODE_LABELS[m],
                "Algoritmo": a,
                "Nodos expandidos": p.expanded,
                "Costo ponderado": round(p.weighted_cost, 4) if p.found else None,
                "Tiempo (min)": round(p.time_min, 1) if p.found else None,
                "Estado": "Ruta encontrada" if p.found else p.message,
            })
    st.dataframe(pd.DataFrame(comp), hide_index=True, width="stretch")
    if "metro" in modes:
        st.caption("La alternativa usa A* sobre la red peatonal y las líneas A/B y T esquemáticas; abordar es opcional y depende del costo ponderado.")

    st.subheader("Detalle por tramo")
    found_modes = [m for m, p in plans.items() if p.found]
    if found_modes:
        sel = st.selectbox("Modo", found_modes, format_func=lambda mode: MODE_LABELS[mode])
        seg = pd.DataFrame(plans[sel].segments)
        st.dataframe(seg, hide_index=True, width="stretch", height=280)

with tab_chat:
    st.subheader("Asistente (LLM + RAG + herramientas)")
    st.caption(f"Usa la hora de salida {hour:02d}:00, los parámetros y los pesos del dashboard. Herramientas: plan_route, compare_modes, "
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
