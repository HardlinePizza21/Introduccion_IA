# Copiloto de movilidad del Valle de Aburrá: rutas con A* y asistente RAG

Proyecto final SI3003, Inteligencia Artificial, Universidad EAFIT, 2026-1 (idea 3.2).

El usuario elige origen, destino, hora de salida, modos de ruta (carro, bicicleta/a pie o caminata + Metro Línea A) y sus preferencias (tiempo, distancia, costo, emisiones). La aplicación calcula alternativas con un **A\* propio** sobre las redes vehicular y peatonal de **OpenStreetMap**, las compara en dos vistas del mapa (ganadora y todas las rutas) y en una tabla, y ofrece un **agente LLM con RAG** que responde preguntas sobre rutas, pico y placa, tarifas y Metro, y cita sus fuentes. El itinerario Metro conecta caminatas hasta y desde estaciones con la Línea A disponible en el área. No se ofrecen rutas de bus porque no hay información centralizada de recorridos.

| Componente | Implementación |
|---|---|
| Parte 1 (técnica clásica) | A\*, Dijkstra (UCS) y BFS propios ([src/movilidad/search.py](src/movilidad/search.py)), costo multiobjetivo ([src/movilidad/planner.py](src/movilidad/planner.py)), heurística admisible y consistente |
| Parte 2 (IA moderna) | Loop agéntico manual con *tool calling* sobre un endpoint compatible con OpenAI ([src/movilidad/agent.py](src/movilidad/agent.py)), RAG con fastembed + FAISS ([src/movilidad/rag.py](src/movilidad/rag.py)), 5 herramientas |
| Dashboard | Streamlit ([app.py](app.py)): vistas de mapa para la ruta ganadora y todas las rutas, estaciones y trazo esquemático de Línea A, tabla y gráfico comparativo, perfil por hora, detalle por tramo, chat y evaluación |

## 1. Instalación

Requiere Python 3.11 o superior (probado con 3.14 en Windows 11, solo CPU).

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    |    Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Configurar el LLM (opcional para rutas, necesario para el chat)

```bash
cp .env.example .env      # Windows: copy .env.example .env
```

Complete `LLM_API_KEY` en `.env`. Por defecto se usa Groq (capa gratuita, `llama-3.3-70b-versatile`). También sirven NVIDIA NIM u Ollama cambiando `LLM_BASE_URL` y `LLM_MODEL` (vea `.env.example`). Sin clave, el mapa, la comparación y la evaluación funcionan; el chat muestra un mensaje explicando qué falta configurar.

## 3. Ejecutar

```bash
streamlit run app.py
```

La primera ejecución descarga la red de OpenStreetMap (unos 12 recuadros de la API oficial, alrededor de 1 minuto) y el modelo de embeddings (unos 220 MB). Ambos quedan en `cache/` y las ejecuciones siguientes arrancan en segundos.

**Plan B de datos.** Si no hay conexión o la API de OSM falla, la app usa la instantánea versionada en [data/](data/) (`drive.graphml.gz`, `walk.graphml.gz`, `metro_stations.json`, descargadas el 12-nov-2026) y lo indica en la barra lateral. Si el modelo de embeddings no se puede descargar, el RAG usa TF-IDF automáticamente.

### Despliegue en Streamlit Community Cloud

1. Entrar a https://share.streamlit.io con la cuenta de GitHub dueña del repositorio y elegir **Create app → Deploy a public app from GitHub**.
2. Repositorio `HardlinePizza21/Introduccion_IA`, rama `main`, archivo principal `app.py`.
3. En **Advanced settings**, elegir Python 3.13 o una versión más reciente y pegar los *secrets* de [.streamlit/secrets.toml.example](.streamlit/secrets.toml.example) con su clave.

Los *secrets* `OSM_SOURCE="snapshot"` y `RAG_BACKEND="tfidf"` mantienen la app por debajo de 1 GB de RAM, el límite del plan gratuito (alrededor de 620 MB frente a 1,2 GB con el modelo de embeddings neuronal), y evitan descargar de OSM en cada arranque en frío. En local se usan la descarga en vivo y los embeddings neuronales.

## 4. Reproducir la evaluación

```bash
pytest -q                                  # pruebas: optimalidad, heurística, costos, pico y placa, RAG, Metro, loop del agente, plan B
python eval/benchmark_search.py --pairs 100   # A* vs Dijkstra vs BFS -> eval/results/benchmark_*.{csv,md}
python eval/run_agent_eval.py              # 14 preguntas fijas al agente (requiere LLM_API_KEY) -> eval/results/agent_eval.{csv,md}
```

## 5. Estructura

```
app.py                      Dashboard Streamlit
src/movilidad/
  config.py                 Parámetros del entorno, pesos y controles del algoritmo (con procedencia)
  data.py                   Descarga OSM por recuadros, grafo propio, estaciones Metro, plan B
  search.py                 A*, Dijkstra, BFS y heurística (implementación propia)
  planner.py                Métricas por tramo, costo ponderado, planificación por modo
  pico_placa.py             Reglas de pico y placa 2026-2 (herramienta determinística)
  rag.py                    Fragmentación, embeddings, índice FAISS
  agent.py                  Herramientas y loop agéntico con T_max
corpus/                     Documentos del RAG (con fuentes y fecha de consulta)
data/                       Instantánea OSM para el plan B
eval/                       Benchmark de búsqueda, preguntas y evaluación del agente
tests/                      Pruebas automáticas
INFORME.md                  Informe del proyecto (máx. 4 páginas)
DECLARACION_IA.md           Declaración de uso de IA generativa
```

## 6. Herramientas del agente

| Herramienta | Qué hace |
|---|---|
| `plan_route(origin, destination, mode, hour, optimize)` | A\* para carro y bicicleta/a pie; A\* multimodal con caminata y abordaje opcional de la Línea A |
| `compare_modes(origin, destination, hour)` | Compara carro, bicicleta/a pie y una ruta multimodal que puede usar o no el Metro |
| `search_docs(query)` | Recupera los 4 fragmentos más similares del corpus, con su cita `[archivo § sección]` |
| `check_pico_y_placa(plate, date, hour, vehicle, fuel)` | Aplica la rotación 2026-2 de forma determinística |
| `nearest_metro_station(place)` | Estación de Metro/Metroplús más cercana según OSM |

Los errores de las herramientas (lugar desconocido, fuera del área, argumentos inválidos) se devuelven al LLM como observación. El loop se corta tras `AGENT_T_MAX` iteraciones (6 por defecto).

## 7. Fuentes de datos

- **Red vial y estaciones:** © colaboradores de OpenStreetMap, licencia ODbL, mediante la API 0.6 (`api.openstreetmap.org`), procesada con OSMnx. La capa de estaciones también incluye el respaldo versionado para paradas cercanas al borde del área, como Aguacatala, Ayurá y Envigado; se normalizan nombres OSM como «Estación del Metro Aguacatala».
- **Precio de la gasolina:** Circular CREG 371 de 2026: $16.251 por galón en Medellín (noviembre de 2026).
- **Tarifas 2026 (referencia documental):** Publimetro y Valora Analitik (enero de 2026): Metro $3.820 (frecuente), bus urbano $3.000. La tarifa Metro frecuente se usa como referencia ajustable en la alternativa multimodal; la tarifa de bus no se usa.
- **Pico y placa 2026-2:** Alcaldía de Medellín, El Colombiano y Telemedellín.
- **Supuestos (no medidos):** velocidades base por tipo de vía, factores de congestión, consumo y factor de emisión del carro (aproximación IPCC), velocidad informativa de bicicleta, velocidad al caminar, velocidad promedio Metro y espera de abordaje. Los parámetros aplicables son ajustables desde el dashboard y están rotulados como supuestos en [src/movilidad/config.py](src/movilidad/config.py) y en el detalle por tramo.

Las URL completas están en cada documento de [corpus/](corpus/).

## 8. Limitaciones

- No hay tráfico real: la hora de salida solo cambia un factor de congestión supuesto.
- No se calculan rutas de bus por falta de una fuente centralizada de recorridos. La capa Metro incluye estaciones cercanas al borde del área; las caminatas siguen limitadas por la cobertura de la red peatonal descargada. A\* busca sobre la red peatonal con enlaces esquemáticos entre estaciones de Línea A y solo aborda si reduce el costo ponderado. No hay geometría ferroviaria oficial, horarios, transbordos ni otras líneas; velocidad y espera son supuestos.
- La opción bicicleta/a pie usa la red peatonal de OSM, sin ciclorrutas ni pendientes. Su velocidad es una estimación de bicicleta; no representa un perfil peatonal independiente. En una ciudad de ladera como Medellín, la pendiente importa.
- El área cubierta es Centro, Laureles y El Poblado (aproximadamente 5 × 8,5 km). Puntos a más de 400 m de la red se rechazan.
- El corpus es un resumen hecho por el equipo a partir de fuentes de prensa y oficiales. Puede quedar desactualizado y no reemplaza la norma.
- **No es consejo legal, de seguridad vial ni de navegación.**
