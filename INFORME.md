# Copiloto de movilidad del Valle de Aburrá: rutas con A\* y asistente RAG

**SI3003 Inteligencia Artificial, Universidad EAFIT, 2026-1.** Equipo: *Samuel Madrid y Jose Miguel Saldarriaga*. Repositorio: https://github.com/HardlinePizza21/Introduccion_IA.

## 1. Problema

Una persona que se mueve entre el Centro, Laureles y El Poblado de Medellín tiene que elegir entre carro, bicicleta/a pie y Metro, según el tiempo, costo, emisiones y restricciones como el pico y placa. La información está dispersa: mapas por un lado, normas y tarifas en noticias y sitios oficiales por otro. Construimos un MVP que (i) calcula y compara rutas con un A\* propio sobre redes de OpenStreetMap para carro y bicicleta/a pie, además de una alternativa multimodal con caminata y abordaje opcional de la Línea A, y (ii) ofrece un asistente conversacional que combina esas rutas con un corpus documental citado. No hay información centralizada de los recorridos de bus, así que el MVP no calcula rutas de bus.

## 2. Datos

| Dato | Fuente | Tipo |
|---|---|---|
| Red vehicular (5.811 nodos, 12.421 arcos dirigidos) y red peatonal (19.371 nodos, 59.926 arcos) | OpenStreetMap, API 0.6, 12 recuadros del área (lon −75,600 a −75,555; lat 6,195 a 6,272), procesados con OSMnx | Observado |
| Estaciones de Metro y Metroplús, incluidas Aguacatala, Ayurá, Envigado, Itagüí y Santa Lucía | OpenStreetMap (`network=Metro de Medellín`/Metroplús) | Observado |
| Gasolina: $16.251/galón | Circular CREG 371/2026 (Medellín, noviembre de 2026) | Oficial |
| Tarifas: Metro $3.820 (usada en la ruta Metro); bus $3.000 (solo informativa en el RAG) | Prensa, enero de 2026 (Publimetro, Valora Analitik) | Secundario |
| Pico y placa 2026-2 | Alcaldía de Medellín y prensa local | Oficial y secundario |
| Velocidades de carro, bicicleta y caminata, congestión, consumo, factor de CO₂, velocidad y espera del Metro | Supuestos del equipo (CO₂ cercano a IPCC 2006) | **Supuesto ajustable** |

**Acceso y plan B.** El servidor Overpass que OSMnx usa por defecto devolvió 502 (saturación) durante el desarrollo. Por eso descargamos la red con la API principal de OSM en recuadros y replicamos los filtros de los tipos de red `drive` y `walk` de OSMnx. Versionamos una instantánea comprimida (3,9 MB en `data/`) que la app usa si la descarga falla. Una prueba automática lo verifica.

## 3. Método de la Parte 1: búsqueda A\* multiobjetivo

**Grafo.** Convertimos el grafo de OSMnx a una lista de adyacencia propia. El carro usa la red vehicular dirigida (respeta sentidos). La bicicleta/a pie usa la red peatonal bidireccional. Los algoritmos no usan networkx.

**Costo por arco.** Para un arco de longitud $L$, clase de vía $c$, modo $m$ y hora $h$:

- Para carro, la velocidad es $v = v^{base}_{c}\cdot f(h)$, con $f(h)=0{,}55$ en pico (6–8 h y 17–19 h), $0{,}8$ en horas intermedias y $1$ en el resto.
- Tiempo $t=L/v$. Combustible $= L\cdot\text{consumo}/100$. Costo del carro = litros × precio; CO₂ = litros × factor de emisión. La bicicleta/a pie usa una velocidad informativa constante y minimiza la distancia.
- La alternativa Metro ejecuta A\* en un grafo combinado: conserva los tramos peatonales OSM y agrega enlaces esquemáticos entre estaciones de Línea A, con acciones de abordaje/descenso. El tren es opcional; la búsqueda puede devolver un itinerario solo a pie si tiene menor costo ponderado. Usa velocidad Metro 35 km/h y 5 minutos de espera supuestos; cobra la tarifa frecuente de referencia $3.820 al abordar. El trazo entre estaciones es esquemático y no modela horarios ni emisiones eléctricas.
- Costo escalar $c = w_d\,\text{km} + w_t\,\text{min} + w_c\,\text{kCOP} + w_e\,(100\,\text{g CO}_2)$, con $w\ge 0$ (validado).

**Heurística.** $h(n)=\alpha\cdot k_{min}\cdot d_{hav}(n,\text{meta})$, donde $k_{min}=\min_e c_e/L_e$ es el menor costo por metro de todo el grafo. Como $L_{uv}\ge d_{hav}(u,v)$, se cumple $c_{uv}\ge k_{min}L_{uv}\ge k_{min}\,[d_{hav}(u,g)-d_{hav}(v,g)]$. Por tanto $h$ es **consistente** (y admisible) para $\alpha\in[0,1]$. La interfaz limita $\alpha$ a ese rango y no ofrece variantes no admisibles. La construcción sirve para cualquier combinación de pesos, porque $k_{min}$ se recalcula cada vez que cambian los parámetros.

**Líneas base.** Dijkstra/UCS (A\* con $h=0$, óptimo) y BFS (minimiza el número de tramos, sin pesos).

**Resultados.** Usamos 100 pares origen-destino aleatorios por escenario (semilla 7, distancia en línea recta ≥ 1 km, mediana 3,4 km), 1.200 búsquedas en total ([eval/results/benchmark_summary.md](eval/results/benchmark_summary.md)):

| Escenario | Nodos expandidos A\* | Dijkstra | BFS | Reducción A\* vs Dijkstra | % óptimo A\* | Sobrecosto BFS |
|---|---:|---:|---:|---:|---:|---:|
| Carro, tiempo, 8 h | 1.102 | 2.959 | 2.859 | 64,8 % | 100 % | +20,9 % |
| Carro, multiobjetivo, 14 h | 859 | 2.992 | 2.859 | 72,9 % | 100 % | +15,7 % |
| Bicicleta, distancia, 10 h | 2.063 | 11.104 | 10.312 | 82,1 % | 100 % | +39,4 % |

A\* encontró siempre el costo óptimo de Dijkstra y expandió entre 64,8 % y 82,1 % menos nodos. Con $\alpha=0{,}5$ la reducción frente a Dijkstra cae a 31,5 %, 35,1 % y 38,2 %, respectivamente, como era de esperar con una cota menos informada. BFS solo coincide con el óptimo en el 0–7 % de los casos y produce rutas entre 15,7 % y 39,4 % más costosas. La ganancia es mayor en distancia ($k_{min}$ ajustado, porque el costo es proporcional a la longitud) que en tiempo, donde $k_{min}$ lo fija la vía más rápida y la cota queda más holgada. Las pruebas unitarias verifican la consistencia arco por arco, la igualdad de costos A\*/Dijkstra en 150 consultas sobre grillas y el rechazo de pesos negativos y de $\alpha>1$.

*Ejemplo (EAFIT → U. de Antioquia, 8 h):* carro 8,17 km, 15,6 min, $2.806 y 1,51 kg CO₂; bicicleta/a pie 7,96 km, 31,8 min y sin emisiones directas; caminata + Metro 8,84 km, 44,9 min y $3.820. A las 3 h el carro tarda 8,6 min. Si se optimizan emisiones, el carro toma una ruta de 7,72 km (1,43 kg CO₂, 17,0 min).

## 4. Diseño del agente y del RAG

**Loop.** Implementamos un loop manual (sin LangGraph) sobre un endpoint compatible con OpenAI (Groq por defecto, configurable a NVIDIA NIM u Ollama) con `temperature=0`. En cada iteración el LLM responde o pide herramientas. Cada herramienta se ejecuta y su resultado, o su error como `{"error": ...}`, vuelve como mensaje `tool`. El loop se corta en $T_{max}=6$. El prompt de sistema incluye la fecha y la hora elegidas en el dashboard, exige usar herramientas para cualquier cifra y pide citar en formato `[archivo.md § sección]`. El agente usa los mismos parámetros y pesos que el usuario ve en la interfaz.

**Herramientas (5).** `plan_route` y `compare_modes` (A\* de la Parte 1), `search_docs` (RAG), `check_pico_y_placa` (reglas determinísticas, para que el LLM no tenga que hacer aritmética de dígitos ni de fechas) y `nearest_metro_station`. Las consultas encadenadas, como "¿puedo ir en carro el jueves? si no, ¿cuánto tarda en bicicleta/a pie?", combinan `check_pico_y_placa` con `compare_modes`. El asistente no calcula ni inventa recorridos de bus. La ruta caminata + Metro sí la calcula, aclarando que el tramo en Metro es esquemático.

**RAG.** El corpus son 6 documentos en `corpus/`: pico y placa 2026-2, tarifas 2026, sistema Metro, EnCicla, combustible y emisiones, y metodología del copiloto. Los redactó el equipo a partir de las fuentes citadas, que van al inicio de cada archivo. Se fragmentan por sección (34 fragmentos), se vectorizan con `paraphrase-multilingual-MiniLM-L12-v2` (fastembed, ONNX en CPU) y se indexan en FAISS con similitud coseno. Si el modelo no se puede descargar, se usa TF-IDF. Cada fragmento lleva su cita. En pruebas manuales, el documento correcto quedó primero en 5 de 5 consultas típicas, y la sección exacta en 3 de 5 (por ejemplo, "horario del metro domingo" → `sistema_metro.md § Horario`, con similitud 0,78; para "factor de emisión gasolina" la sección correcta quedó segunda). Por eso `search_docs` devuelve 4 fragmentos.

## 5. Evaluación del agente

Usamos 14 preguntas fijas ([eval/agent_questions.json](eval/agent_questions.json)), con fecha de referencia 12-nov-2026 (jueves), evaluadas automáticamente por [eval/run_agent_eval.py](eval/run_agent_eval.py). Para cada pregunta se verifica: (a) **herramienta correcta**, es decir, si se llamaron las herramientas esperadas; (b) **cita**, si la respuesta menciona el documento esperado, o OpenStreetMap/A\* en el caso de cifras calculadas; y (c) **contenido clave**, si aparecen los datos esperados.

Las preguntas cubren rutas y comparación de modos (Q01, Q02, Q10: `plan_route`/`compare_modes`), normativa y tarifas (Q03, Q05, Q08, Q09, Q12, Q14: `search_docs`), pico y placa con la herramienta determinística (Q04, Q11), encadenamiento de herramientas (Q06: `nearest_metro_station` + `search_docs`; Q07: `check_pico_y_placa` + ruta en bicicleta) y dos casos de borde: un modo que no se ofrece (Q13, bus desde Rionegro: no debe llamar herramientas de ruta y debe explicar la limitación) y un dato no confirmado en el corpus (Q14, multa exacta: debe remitir a la Secretaría de Movilidad). La lista completa está en el JSON.

**Resultados** (`openai/gpt-oss-120b` vía Groq, `temperature=0`, 15-nov-2026; respuestas completas en [eval/results/agent_eval.md](eval/results/agent_eval.md)):

| Criterio | Automático | Tras revisión manual |
|---|---:|---:|
| Herramienta correcta | 14/14 | 14/14 |
| Cita de la fuente esperada | 13/14 | 14/14 |
| Contenido clave | 11/14 | 14/14 |

Ninguna herramienta devolvió error. La media fue de 2,3 iteraciones por pregunta (máximo 3), muy por debajo de $T_{max}=6$. Las dos preguntas encadenadas llamaron a ambas herramientas esperadas. En Q13 el agente no llamó herramientas de ruta, explicó que no hay información centralizada de buses y ofreció los modos disponibles. En Q14 no inventó la multa: dio el rango que reporta la prensa y remitió a la Secretaría. Análisis de las diferencias entre la medición automática y la manual:

- **Los 4 fallos automáticos son falsos negativos del verificador**, que busca texto literal. En Q04 respondió correctamente "puedes circular mañana", pero sin la palabra "viernes". En Q05 y Q09 escribió "3 820" y "16 251" con espacio en lugar de punto de miles. En Q13 parafraseó la frase esperada ("no dispone de información centralizada"). Un verificador más robusto normalizaría números y usaría varias formulaciones aceptables, o un LLM como juez.
- **Calidad de las citas.** De las 9 respuestas con cita `[archivo § sección]`, 8 nombran una sección real del corpus. La excepción es Q07 (`§ restricción jueves 5-20 h, dígitos 3-6`): el dato es correcto, pero la sección es inventada, porque `check_pico_y_placa` no devuelve una cita literal como sí lo hace `search_docs`. Agregar ese campo a la herramienta es una mejora directa.
- **Variabilidad.** Aun con `temperature=0`, las respuestas cambian entre corridas. En una corrida previa, con la versión anterior del sistema, Q07 confundió el horario de la restricción y varias citas traían secciones inventadas. Por eso las cifras deben leerse como una muestra, no como una tasa estable. Con 14 preguntas, la incertidumbre es amplia.
- **Capa gratuita.** Groq limita a 8.000 tokens/min. Una corrida previa perdió una pregunta por el error 429, y el script ahora reintenta solo ante ese error.

El loop, la ejecución de herramientas, el manejo de JSON inválido, el corte por $T_{max}$ y el error de configuración se verificaron además con un LLM simulado en las pruebas automáticas (44/44 pruebas pasan).

## 6. Dashboard e interacción

En Streamlit, la barra lateral permite elegir origen y destino (12 lugares o coordenadas), la hora, los modos de ruta (carro, bicicleta/a pie y caminata con Metro opcional) y tres grupos de controles explicados: (1) parámetros del entorno (velocidades, congestión, consumo y tarifas), (2) pesos de preferencias y (3) algoritmo e intensidad de la heurística. Cualquier cambio recalcula los costos y vuelve a ejecutar la búsqueda. La pestaña **Rutas** muestra dos mapas Folium (ruta ganadora por puntaje de preferencias y todas las rutas), estaciones y trazo esquemático de Línea A, tabla y gráfico comparativo, A\* frente a Dijkstra y BFS para los modos con red vial, y detalle por tramo. **Hora del día** compara carro y bicicleta/a pie para las 24 horas; la alternativa Metro queda constante porque no se modelan horarios. **Asistente** es el chat con el agente: muestra cada llamada a herramienta, sus argumentos y su resultado. **Evaluación** muestra el benchmark de búsqueda y los resultados del agente.

## 7. Limitaciones y uso responsable

- **Sin tráfico real.** La congestión es un factor horario supuesto. Los tiempos sirven para comparar alternativas, no como predicción.
- No se calculan rutas de bus porque no hay una fuente centralizada de recorridos. La alternativa Metro se limita a la Línea A y estaciones conectadas con la red peatonal; abordar es opcional y la geometría del tren es esquemática. No incluye horarios, transbordos ni otras líneas. La bicicleta/a pie usa la red peatonal de OSM y no considera ciclorrutas ni pendientes.
- Factores de emisión y consumos aproximados. Deberían calibrarse con FECOC (UPME) y con datos de flota.
- El corpus resume fuentes de prensa y oficiales a noviembre de 2026. Algunas cifras difieren entre fuentes (por ejemplo, la multa) y el agente está instruido para decirlo. `check_pico_y_placa` no conoce los festivos.
- Las métricas del agente dependen del modelo LLM y del proveedor. Con la capa gratuita puede haber límites de uso.
- Los datos de OSM se usan bajo licencia ODbL y con atribución. No se procesan datos personales: la placa que escribe el usuario no se almacena.
- El sistema es académico. **No constituye consejo legal, de navegación ni de seguridad vial.**
