# Declaración de uso de IA generativa

Proyecto final SI3003, Universidad EAFIT, 2026-1. Equipo: *[nombres de los integrantes]*.

| Herramienta | Uso | Partes del proyecto |
|---|---|---|
| GitHub Copilot | Ayuda para redactar el plan inicial del proyecto (`PLAN.md`) | Planeación |
| Claude Code (Anthropic, modelo Claude Opus) | Generación asistida del código a partir del plan del equipo: módulos de datos, A\*/Dijkstra/BFS, modelo de costos, RAG, agente, dashboard, pruebas y scripts de evaluación; búsqueda web de fuentes (pico y placa 2026-2, tarifas 2026, precio de la gasolina); borradores del corpus RAG, el README, este informe y las preguntas de evaluación | Código, corpus, documentación |
| LLM del agente (Llama 3.3 70B vía Groq u otro endpoint configurado) | Componente del producto: razonamiento y redacción de las respuestas del asistente en tiempo de ejecución | Aplicación |

**Verificación hecha por el equipo.** *[Completar y ajustar con lo que efectivamente hizo cada integrante.]* Antes de entregar, cada integrante debe poder explicar:

- Por qué la heurística $k_{min}\cdot d_{hav}$ es consistente y qué pasaría con $\alpha>1$.
- Cómo se construye el costo multiobjetivo y qué parámetros son supuestos y cuáles provienen de fuentes.
- Cómo funciona el loop agéntico (mensajes `tool`, $T_{max}$, errores como observación) y el RAG (fragmentación, embeddings, FAISS).

**Contenido revisado.** Los resultados numéricos del informe salen de ejecutar `eval/benchmark_search.py` y las pruebas (`pytest`), no de texto generado. Las cifras del corpus se tomaron de las fuentes citadas en cada documento, y las discrepancias entre fuentes se dejaron explícitas. El equipo debe revisar el corpus contra las fuentes oficiales antes de la entrega.

**Responsabilidad.** El uso de IA generativa no reemplaza la comprensión del trabajo entregado. El equipo asume la autoría y la responsabilidad del contenido.
