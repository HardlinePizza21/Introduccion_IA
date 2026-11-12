"""Agente LLM con loop manual de tool calling (endpoint compatible con OpenAI).

Variables de entorno (o archivo .env):
  LLM_API_KEY   clave del proveedor (Groq, NVIDIA NIM...). Ollama no la requiere.
  LLM_BASE_URL  por defecto https://api.groq.com/openai/v1
  LLM_MODEL     por defecto llama-3.3-70b-versatile
  AGENT_T_MAX   máximo de iteraciones del loop (por defecto 6)
"""
from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import pico_placa
from .config import AlgoParams, EnvParams, MODES, Weights
from .data import PLACES, load_metro_stations, resolve_place
from .planner import Planner
from .rag import DocIndex
from .search import haversine_m

ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Carga simple de .env (sin sobrescribir variables ya definidas)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class LLMConfigError(RuntimeError):
    pass


OPTIMIZE_PRESETS = {
    "tiempo": Weights(time=1.0),  # Weights tiene time=1 por defecto: se fija explícitamente en 0 donde no aplica
    "distancia": Weights(distance=1.0, time=0.0),
    "costo": Weights(cost=1.0, time=0.05),  # pequeño peso al tiempo para desempatar
    "emisiones": Weights(emissions=1.0, time=0.05),
}

TOOLS = [
    {"type": "function", "function": {
        "name": "plan_route",
        "description": "Calcula con A* la mejor ruta en un modo (carro, bus o bicicleta) entre dos lugares del área "
                       "Centro–Laureles–El Poblado de Medellín. Devuelve distancia, tiempo, costo, CO2 y vías principales.",
        "parameters": {"type": "object", "properties": {
            "origin": {"type": "string", "description": f"Lugar predefinido ({', '.join(PLACES)}) o 'lat, lon'"},
            "destination": {"type": "string", "description": "Lugar predefinido o 'lat, lon'"},
            "mode": {"type": "string", "enum": list(MODES)},
            "hour": {"type": "integer", "description": "Hora local de salida 0-23. Si no se indica, use la del dashboard."},
            "optimize": {"type": "string", "enum": ["dashboard", *OPTIMIZE_PRESETS],
                         "description": "Criterio a optimizar; 'dashboard' usa los pesos elegidos en la interfaz."},
        }, "required": ["origin", "destination", "mode"]}}},
    {"type": "function", "function": {
        "name": "compare_modes",
        "description": "Compara carro, bus y bicicleta entre dos lugares a una hora: distancia, tiempo, costo y CO2.",
        "parameters": {"type": "object", "properties": {
            "origin": {"type": "string"}, "destination": {"type": "string"},
            "hour": {"type": "integer", "description": "Hora local de salida 0-23"},
        }, "required": ["origin", "destination"]}}},
    {"type": "function", "function": {
        "name": "search_docs",
        "description": "Busca en el corpus documental (pico y placa 2026-2, tarifas 2026, sistema Metro, EnCicla, "
                       "combustible y emisiones, metodología del copiloto). Devuelve fragmentos con su cita.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "check_pico_y_placa",
        "description": "Determina si una placa tiene pico y placa en Medellín en una fecha (y hora) dada.",
        "parameters": {"type": "object", "properties": {
            "plate": {"type": "string", "description": "Placa, p. ej. ABC123"},
            "date": {"type": "string", "description": "Fecha AAAA-MM-DD"},
            "hour": {"type": "integer"},
            "vehicle": {"type": "string", "enum": ["carro", "moto"]},
            "fuel": {"type": "string", "description": "gasolina, diésel, eléctrico, híbrido o gas natural"},
        }, "required": ["plate", "date"]}}},
    {"type": "function", "function": {
        "name": "nearest_metro_station",
        "description": "Estación de Metro/tranvía/cable más cercana (en línea recta) a un lugar, según OpenStreetMap.",
        "parameters": {"type": "object", "properties": {"place": {"type": "string"}}, "required": ["place"]}}},
]


def system_prompt(today: dt.date, hour: int) -> str:
    return f"""Eres el Copiloto de Movilidad del Valle de Aburrá (proyecto académico SI3003, EAFIT).
Hoy es {today.isoformat()} ({pico_placa.DAY_NAMES[today.weekday()]}); la hora de salida seleccionada en el dashboard es {hour}:00.
Reglas:
1. Para rutas, tiempos, costos o emisiones usa SIEMPRE plan_route o compare_modes; nunca inventes cifras.
2. Para normas, tarifas, horarios del Metro, EnCicla o supuestos del modelo usa search_docs y cita cada dato con la cita
   exacta que devuelve la herramienta, con el formato [archivo.md § sección].
3. Para saber si un vehículo puede circular usa check_pico_y_placa (y cita pico_y_placa_2026_2.md).
4. Cuando cites cifras de rutas, indica que provienen del cálculo A* sobre OpenStreetMap con velocidades estimadas (no tráfico real).
5. Puedes encadenar varias herramientas. Si una herramienta devuelve un error, explícalo o corrige los argumentos.
6. Si la información no está en el corpus ni en las herramientas, dilo. No des consejo legal ni de seguridad.
Responde en español, de forma breve y clara."""


@dataclass
class AgentResult:
    answer: str
    tool_calls: list = field(default_factory=list)  # [{"name", "args", "result"}]
    iterations: int = 0
    stopped_by_tmax: bool = False


class MobilityAgent:
    def __init__(self, planner: Planner | None = None, index: DocIndex | None = None,
                 env: EnvParams | None = None, weights: Weights | None = None,
                 algo: AlgoParams | None = None, hour: int = 8, today: dt.date | None = None):
        self.planner = planner or Planner()
        self.index = index
        self.env, self.weights, self.algo = env or EnvParams(), weights or Weights(), algo or AlgoParams()
        self.hour, self.today = hour, today or dt.date.today()
        self.t_max = int(os.getenv("AGENT_T_MAX", "6"))
        self._stations = None

    # ---------------- herramientas ----------------
    def _index(self) -> DocIndex:
        if self.index is None:
            self.index = DocIndex()
        return self.index

    def tool_plan_route(self, origin, destination, mode, hour=None, optimize="dashboard"):
        w = self.weights if optimize in (None, "dashboard") else OPTIMIZE_PRESETS.get(optimize)
        if w is None:
            raise ValueError(f"optimize debe ser uno de {['dashboard', *OPTIMIZE_PRESETS]}")
        p = self.planner.plan(origin, destination, mode, self.hour if hour is None else hour, self.env, w, self.algo)
        out = p.summary()
        names = []
        for s in p.segments:
            if s["via"] != "(sin nombre)" and (not names or names[-1] != s["via"]):
                names.append(s["via"])
        out["vias_principales"] = names[:8]
        out["fuente"] = "Cálculo A* propio sobre red OpenStreetMap; velocidades y consumos estimados (metodologia_rutas.md)"
        return out

    def tool_compare_modes(self, origin, destination, hour=None):
        h = self.hour if hour is None else hour
        rows = [p.summary() for p in self.planner.compare(origin, destination, h, self.env, self.weights, self.algo)]
        return {"comparacion": rows,
                "fuente": "Cálculo A* propio sobre red OpenStreetMap; velocidades y consumos estimados (metodologia_rutas.md)"}

    def tool_search_docs(self, query):
        return {"resultados": self._index().search(query, k=4)}

    def tool_check_pico_y_placa(self, plate, date, hour=None, vehicle="carro", fuel="gasolina"):
        return pico_placa.check(plate, date, hour, vehicle, fuel)

    def tool_nearest_metro_station(self, place):
        latlon = resolve_place(place)
        if self._stations is None:
            self._stations = load_metro_stations()
        if not self._stations:
            raise RuntimeError("No hay estaciones de Metro disponibles en el área.")
        best = min(self._stations, key=lambda s: haversine_m(latlon, (s["lat"], s["lon"])))
        d = haversine_m(latlon, (best["lat"], best["lon"]))
        return {"estacion": best["name"], "linea_o_red": best.get("line", ""), "distancia_linea_recta_m": round(d),
                "caminata_estimada_min": round(d * 1.3 / 80, 1),  # factor de desvío 1,3 y 80 m/min (supuestos)
                "fuente": "Estaciones de OpenStreetMap; caminata estimada con supuestos (sistema_metro.md)"}

    def call_tool(self, name: str, args: dict) -> dict:
        fn = getattr(self, f"tool_{name}", None)
        if fn is None:
            return {"error": f"Herramienta desconocida: {name}"}
        try:
            return fn(**args)
        except TypeError as exc:
            return {"error": f"Argumentos inválidos para {name}: {exc}"}
        except Exception as exc:  # el error vuelve al LLM como observación
            return {"error": f"{type(exc).__name__}: {exc}"}

    # ---------------- loop agéntico ----------------
    def _client(self):
        load_dotenv()
        key = os.getenv("LLM_API_KEY", "")
        base = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
        if not key and "localhost" not in base and "127.0.0.1" not in base:
            raise LLMConfigError(
                "Falta configurar el LLM: defina LLM_API_KEY (y opcionalmente LLM_BASE_URL y LLM_MODEL) en el "
                "archivo .env (vea .env.example). El mapa y la comparación de rutas funcionan sin LLM.")
        from openai import OpenAI

        return OpenAI(api_key=key or "ollama", base_url=base, timeout=60), os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")

    def run(self, question: str, history: list | None = None) -> AgentResult:
        client, model = self._client()
        messages = [{"role": "system", "content": system_prompt(self.today, self.hour)}]
        messages += list(history or [])
        messages.append({"role": "user", "content": question})
        result = AgentResult(answer="")
        for it in range(1, self.t_max + 1):
            result.iterations = it
            resp = client.chat.completions.create(model=model, messages=messages, tools=TOOLS,
                                                  tool_choice="auto", temperature=0)
            msg = resp.choices[0].message
            if not msg.tool_calls:
                result.answer = msg.content or ""
                return result
            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                    obs = self.call_tool(tc.function.name, args)
                except json.JSONDecodeError as exc:
                    args, obs = {}, {"error": f"Argumentos JSON inválidos: {exc}"}
                result.tool_calls.append({"name": tc.function.name, "args": args, "result": obs})
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": json.dumps(obs, ensure_ascii=False, default=str)[:6000]})
        result.stopped_by_tmax = True
        result.answer = (f"Se alcanzó el máximo de {self.t_max} iteraciones del agente sin una respuesta final. "
                         "Reformule la pregunta de forma más específica.")
        return result
