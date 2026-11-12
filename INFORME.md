# Copiloto de movilidad del Valle de Aburrá: rutas con A\* y asistente RAG

**SI3003 Inteligencia Artificial, Universidad EAFIT, 2026-1.** Equipo: *[nombres de los integrantes]*. Repositorio: *[URL de GitHub]*.

## 1. Problema

Una persona que se mueve entre el Centro, Laureles y El Poblado de Medellín tiene que elegir modo (carro, bus o bicicleta) y ruta según el tiempo, el costo, las emisiones y restricciones como el pico y placa. La información está dispersa: mapas por un lado, normas y tarifas en noticias y sitios oficiales por otro. Construimos un MVP que (i) calcula y compara rutas con un algoritmo de búsqueda propio sobre la red vial real y (ii) ofrece un asistente conversacional que combina esas rutas con un corpus documental citado.

## 2. Datos

| Dato | Fuente | Tipo |
|---|---|---|
| Red vehicular (5.811 nodos, 12.421 arcos dirigidos) y red peatonal (19.371 nodos, 59.926 arcos) | OpenStreetMap, API 0.6, 12 recuadros del área (lon −75,600 a −75,555; lat 6,195 a 6,272), procesados con OSMnx | Observado |
| 17 estaciones de Metro y Metroplús | OpenStreetMap (`network=Metro de Medellín`) | Observado |
| Gasolina: $16.251/galón | Circular CREG 371/2026 (Medellín, noviembre de 2026) | Oficial |
| Tarifas: bus $3.000, Metro $3.820 | Prensa, enero de 2026 (Publimetro, Valora Analitik) | Secundario |
| Pico y placa 2026-2 | Alcaldía de Medellín y prensa local | Oficial y secundario |
| Velocidades base, congestión, consumos, factores de CO₂, ocupación del bus | Supuestos del equipo (CO₂ cercano a IPCC 2006) | **Supuesto ajustable** |

**Acceso y plan B.** El servidor Overpass que OSMnx usa por defecto devolvió 502 (saturación) durante el desarrollo. Por eso descargamos la red con la API principal de OSM en recuadros y replicamos los filtros de los tipos de red `drive` y `walk` de OSMnx. Versionamos una instantánea comprimida (3,9 MB en `data/`) que la app usa si la descarga falla. Una prueba automática lo verifica.

## 3. Método de la Parte 1: búsqueda A\* multiobjetivo

**Grafo.** Convertimos el grafo de OSMnx a una lista de adyacencia propia. Carro y bus usan la red vehicular dirigida (respeta sentidos). La bicicleta usa la red peatonal bidireccional. Los algoritmos no usan networkx.

**Costo por arco.** Para un arco de longitud $L$, clase de vía $c$, modo $m$ y hora $h$:

- Velocidad $v = v^{base}_{m,c}\cdot f(h)$, con $f(h)=0{,}55$ en pico (6–8 h y 17–19 h), $0{,}8$ en horas intermedias y $1$ en el resto.
- Tiempo $t=L/v$. Combustible $= L\cdot\text{consumo}/100$. Costo del carro = litros × precio. CO₂ = litros × factor (en el bus, dividido entre la ocupación).
- Costo escalar $c = w_d\,\text{km} + w_t\,\text{min} + w_c\,\text{kCOP} + w_e\,(100\,\text{g CO}_2)$, con $w\ge 0$ (validado). La tarifa del bus es fija, así que se suma al final y no afecta la ruta. La bicicleta minimiza la distancia.

**Heurística.** $h(n)=\alpha\cdot k_{min}\cdot d_{hav}(n,\text{meta})$, donde $k_{min}=\min_e c_e/L_e$ es el menor costo por metro de todo el grafo. Como $L_{uv}\ge d_{hav}(u,v)$, se cumple $c_{uv}\ge k_{min}L_{uv}\ge k_{min}\,[d_{hav}(u,g)-d_{hav}(v,g)]$. Por tanto $h$ es **consistente** (y admisible) para $\alpha\in[0,1]$. La interfaz limita $\alpha$ a ese rango y no ofrece variantes no admisibles. La construcción sirve para cualquier combinación de pesos, porque $k_{min}$ se recalcula cada vez que cambian los parámetros.

**Líneas base.** Dijkstra/UCS (A\* con $h=0$, óptimo) y BFS (minimiza el número de tramos, sin pesos).

**Resultados.** Usamos 100 pares origen-destino aleatorios por escenario (semilla 7, distancia en línea recta ≥ 1 km, mediana 3,4 km), 1.600 búsquedas en total ([eval/results/benchmark_summary.md](eval/results/benchmark_summary.md)):

| Escenario | Nodos expandidos A\* | Dijkstra | BFS | Reducción A\* vs Dijkstra | % óptimo A\* | Sobrecosto BFS |
|---|---:|---:|---:|---:|---:|---:|
| Carro, tiempo, 8 h | 1.336 | 3.242 | 3.238 | 61,0 % | 100 % | +25,0 % |
| Carro, multiobjetivo, 14 h | 1.035 | 3.250 | 3.238 | 70,3 % | 100 % | +20,5 % |
| Bus, tiempo, 18 h | 1.324 | 3.246 | 3.238 | 61,5 % | 100 % | +21,2 % |
| Bicicleta, distancia, 10 h | 2.246 | 9.889 | 10.137 | 78,8 % | 100 % | +34,9 % |

A\* encontró siempre el costo óptimo de Dijkstra y expandió entre 61 % y 79 % menos nodos. Con $\alpha=0{,}5$ la reducción cae aproximadamente a la mitad, como era de esperar. BFS solo coincide con el óptimo en el 0–5 % de los casos y produce rutas entre 20 % y 35 % más costosas. La ganancia es mayor en distancia ($k_{min}$ ajustado, porque el costo es proporcional a la longitud) que en tiempo, donde $k_{min}$ lo fija la vía más rápida y la cota queda más holgada. Las pruebas unitarias verifican la consistencia arco por arco, la igualdad de costos A\*/Dijkstra en 150 consultas sobre grillas y el rechazo de pesos negativos y de $\alpha>1$.

*Ejemplo (EAFIT → U. de Antioquia, 8 h):* carro 8,17 km, 15,6 min, $2.806 y 1,51 kg CO₂; bus 23,3 min, $3.000 y 0,26 kg; bicicleta 7,96 km, 31,8 min, sin emisiones. A las 3 h el carro tarda 8,6 min. Si se optimizan emisiones, el carro toma una ruta de 7,72 km (1,43 kg CO₂, 17,0 min).

## 4. Diseño del agente y del RAG

**Loop.** Implementamos un loop manual (sin LangGraph) sobre un endpoint compatible con OpenAI (Groq por defecto, configurable a NVIDIA NIM u Ollama) con `temperature=0`. En cada iteración el LLM responde o pide herramientas. Cada herramienta se ejecuta y su resultado, o su error como `{"error": ...}`, vuelve como mensaje `tool`. El loop se corta en $T_{max}=6$. El prompt de sistema incluye la fecha y la hora elegidas en el dashboard, exige usar herramientas para cualquier cifra y pide citar en formato `[archivo.md § sección]`. El agente usa los mismos parámetros y pesos que el usuario ve en la interfaz.

**Herramientas (5).** `plan_route` y `compare_modes` (A\* de la Parte 1), `search_docs` (RAG), `check_pico_y_placa` (reglas determinísticas, para que el LLM no tenga que hacer aritmética de dígitos ni de fechas) y `nearest_metro_station`. Las consultas encadenadas, como "¿puedo ir en carro el jueves? si no, ¿qué es más rápido?", combinan `check_pico_y_placa` con `compare_modes`.

**RAG.** El corpus son 6 documentos en `corpus/`: pico y placa 2026-2, tarifas 2026, sistema Metro, EnCicla, combustible y emisiones, y metodología del copiloto. Los redactó el equipo a partir de las fuentes citadas, que van al inicio de cada archivo. Se fragmentan por sección (34 fragmentos), se vectorizan con `paraphrase-multilingual-MiniLM-L12-v2` (fastembed, ONNX en CPU) y se indexan en FAISS con similitud coseno. Si el modelo no se puede descargar, se usa TF-IDF. Cada fragmento lleva su cita. En pruebas manuales, el documento correcto quedó primero en 5 de 5 consultas típicas, y la sección exacta en 3 de 5 (por ejemplo, "horario del metro domingo" → `sistema_metro.md § Horario`, con similitud 0,78; para "factor de emisión gasolina" la sección correcta quedó segunda). Por eso `search_docs` devuelve 4 fragmentos.

## 5. Evaluación del agente

Usamos 14 preguntas fijas ([eval/agent_questions.json](eval/agent_questions.json)), con fecha de referencia 12-nov-2026 (jueves), evaluadas automáticamente por [eval/run_agent_eval.py](eval/run_agent_eval.py). Para cada pregunta se verifica: (a) **herramienta correcta**, es decir, si se llamaron las herramientas esperadas; (b) **cita**, si la respuesta menciona el documento esperado, o OpenStreetMap/A\* en el caso de cifras calculadas; y (c) **contenido clave**, si aparecen los datos esperados.

| ID | Pregunta (resumen) | Herramienta(s) esperada(s) | Cita esperada |
|---|---|---|---|
| Q01 | Tiempo en carro de EAFIT a la U. de Antioquia a las 8 h | plan_route | OSM / A\* |
| Q02 | Comparar modos de Berrío a Lleras a las 18 h; ¿cuál emite menos? | compare_modes | OSM / A\* |
| Q03 | Dígitos y horario del miércoles | search_docs | pico_y_placa |
| Q04 | Placa HTK236, ¿puede circular mañana a las 7 h? (viernes: sí) | check_pico_y_placa | pico_y_placa |
| Q05 | Tarifa del Metro (Cívica frecuente) y del bus 2026 | search_docs | tarifas |
| Q06 | Estación más cercana a Plaza Mayor y horario dominical | nearest_metro_station + search_docs | sistema_metro |
| Q07 | Placa terminada en 6, jueves 19-nov a las 17 h; alternativa más rápida | check_pico_y_placa + compare_modes | pico_y_placa |
| Q08 | ¿Cómo se modela la hora pico? ¿Hay tráfico real? | search_docs | metodologia_rutas |
| Q09 | Precio de la gasolina y factor de CO₂ usados | search_docs | combustible_y_emisiones |
| Q10 | Ruta de carro con menos CO₂ de Unicentro a Parque del Poblado | plan_route (optimize=emisiones) | OSM / A\* |
| Q11 | Híbrido con placa terminada en 5, lunes 16-nov | check_pico_y_placa | pico_y_placa |
| Q12 | EnCicla: costo; ¿la ruta en bici usa ciclorrutas? | search_docs | encicla / metodologia |
| Q13 | Bus de Rionegro a Plaza Mayor (fuera del área: manejo de error) | plan_route | explica "fuera del área" |
| Q14 | Multa exacta del pico y placa (dato no confirmado en el corpus) | search_docs | pico_y_placa; remite a la Secretaría |

**Resultados:** *[completar con `eval/results/agent_eval.md` tras ejecutar `python eval/run_agent_eval.py` con la clave del LLM: X/14 herramienta correcta, Y/14 cita, Z/14 contenido]*. El loop, la ejecución de herramientas, el manejo de JSON inválido, el corte por $T_{max}$ y el error de configuración se verificaron con un LLM simulado en las pruebas automáticas (39/39 pruebas pasan).

## 6. Dashboard e interacción

En Streamlit, la barra lateral permite elegir origen y destino (12 lugares o coordenadas), la hora, los modos y tres grupos de controles explicados: (1) parámetros del entorno (velocidades por tipo de vía, factores de congestión, consumo, precio, tarifa y ocupación), (2) pesos de preferencias y (3) algoritmo e intensidad de la heurística. Cualquier cambio recalcula los costos y vuelve a ejecutar la búsqueda. Las pestañas son: **Rutas** (mapa Folium con las rutas por modo y las estaciones, tabla y gráfico comparativo de tiempo, costo y CO₂, A\* frente a Dijkstra y BFS para la consulta actual, y detalle por tramo con velocidad estimada y su procedencia), **Hora del día** (tiempo de carro y bus para las 24 horas de salida), **Asistente** (chat que muestra cada llamada a herramienta y su resultado) y **Evaluación**.

## 7. Limitaciones y uso responsable

- **Sin tráfico real.** La congestión es un factor horario supuesto. Los tiempos sirven para comparar alternativas, no como predicción. Los tiempos de bus omiten espera, paradas y trazado de rutas reales.
- El Metro no se enruta (solo se muestran estaciones y la más cercana). La bicicleta ignora ciclorrutas y pendientes, que en Medellín son relevantes.
- Factores de emisión y consumos aproximados. Deberían calibrarse con FECOC (UPME) y con datos de flota.
- El corpus resume fuentes de prensa y oficiales a noviembre de 2026. Algunas cifras difieren entre fuentes (por ejemplo, la multa) y el agente está instruido para decirlo. `check_pico_y_placa` no conoce los festivos.
- Las métricas del agente dependen del modelo LLM y del proveedor. Con la capa gratuita puede haber límites de uso.
- Los datos de OSM se usan bajo licencia ODbL y con atribución. No se procesan datos personales: la placa que escribe el usuario no se almacena.
- El sistema es académico. **No constituye consejo legal, de navegación ni de seguridad vial.**
