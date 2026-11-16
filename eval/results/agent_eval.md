# Evaluación del agente

Fecha de referencia: 2026-11-12. Preguntas: 14.

- Herramienta correcta: 14/14
- Cita de la fuente: 13/14
- Contenido clave: 11/14

| id   | categoria                  | herramientas_llamadas              | herramienta_correcta   | cita_fuente   | contenido_clave   |   errores_herramienta |   iteraciones |   segundos |
|:-----|:---------------------------|:-----------------------------------|:-----------------------|:--------------|:------------------|----------------------:|--------------:|-----------:|
| Q01  | ruta                       | plan_route, search_docs            | True                   | True          | True              |                     0 |             3 |        8.1 |
| Q02  | comparación                | compare_modes                      | True                   | True          | True              |                     0 |             2 |       10.4 |
| Q03  | normativa                  | search_docs, search_docs           | True                   | True          | True              |                     0 |             3 |       20   |
| Q04  | herramienta determinística | check_pico_y_placa                 | True                   | True          | False             |                     0 |             2 |       11.9 |
| Q05  | tarifas                    | search_docs, search_docs           | True                   | True          | False             |                     0 |             3 |       34   |
| Q06  | Metro                      | nearest_metro_station, search_docs | True                   | True          | True              |                     0 |             3 |       23.3 |
| Q07  | encadenamiento             | check_pico_y_placa, plan_route     | True                   | True          | True              |                     0 |             3 |       27.8 |
| Q08  | supuestos                  | search_docs                        | True                   | True          | True              |                     0 |             2 |       11.4 |
| Q09  | supuestos                  | search_docs                        | True                   | True          | False             |                     0 |             2 |       14   |
| Q10  | optimización               | plan_route                         | True                   | True          | True              |                     0 |             2 |      305.8 |
| Q11  | exención                   | check_pico_y_placa                 | True                   | True          | True              |                     0 |             2 |        1.4 |
| Q12  | bicicleta pública          | search_docs                        | True                   | True          | True              |                     0 |             2 |        2.1 |
| Q13  | modo no soportado          |                                    | True                   | False         | True              |                     0 |             1 |        0.9 |
| Q14  | fuera de corpus            | search_docs                        | True                   | True          | True              |                     0 |             2 |        1.7 |

## Respuestas

### Q01 – ¿Cuánto me demoro en carro desde la Universidad EAFIT hasta la Universidad de Antioquia saliendo a las 8 a. m.?

Según el cálculo A* sobre la red de OpenStreetMap (con velocidades estimadas según la hora pico) el recorrido en carro entre la **Universidad EAFIT** y la **Universidad de Antioquia** saliendo a las 8:00 a.m. tiene:

- **Tiempo estimado:** **≈ 15,6 min** (≈ 16 min)  
- **Distancia:** 8,17 km  
- **Costo de combustible estimado:** 2 806 COP  
- **Emisiones de CO₂:** 1,51 kg  

Estos valores provienen del algoritmo A* aplicado a la red vial de OSM y a los factores de velocidad por tipo de vía y hora del día (pico 8 h) descritos en la metodología del proyecto [metodologia_rutas.md § Datos] y [metodologia_rutas.md § Velocidades estimadas y tráfico].

### Q02 – Compara carro y bicicleta para ir de Parque Berrío a Parque Lleras a las 6 de la tarde. ¿Cuál emite menos CO2?

**Comparación (cálculo A* sobre OpenStreetMap, con velocidades y consumos estimados)**  

| Modo | Distancia (km) | Tiempo (min) | Costo (COP) | CO₂ emitido (kg) |
|------|----------------|--------------|-------------|------------------|
| Carro | 6.18 | 16.9 | 2 123 | **1.14** |
| Bicicleta | 5.11 | 20.4 | 0 | **0.00** |

**Resultado:** la bicicleta emite **menos CO₂** (0 kg) que el carro (≈1.14 kg).  

*Los valores provienen del cálculo A* sobre la red OSM con velocidades y consumos estimados (ver metodología en `metodologia_rutas.md`).*

### Q03 – ¿Qué placas tienen pico y placa los miércoles en Medellín y en qué horario?

Los miércoles la restricción de pico y placa en Medellín se aplica **de 5:00 a.m. a 8:00 p.m.** [​pico_y_placa_2026_2.md § Horario].

- **Carros (y demás vehículos de cuatro ruedas)**: no pueden circular si el **último dígito de la placa termina en 0 o 2** [​pico_y_placa_2026_2.md § Rotación de dígitos].
- **Motocicletas (y ciclomotores, etc.)**: la restricción se basa en el **primer número de la placa**; tampoco pueden circular si ese número es **0 o 2** [​pico_y_placa_2026_2.md § Rotación de dígitos].

Esta medida está vigente desde el 3 de agosto de 2026 hasta el 29 de enero de 2027 [​pico_y_placa_2026_2.md § Vigencia].

### Q04 – Mi carro tiene placa HTK236. ¿Puedo circular mañana a las 7 a. m.?

Sí, puedes circular mañana a las 7 a. m. con la placa **HTK236**; el dígito 6 no está restringido ese día. [pico_y_placa_2026_2.md]

### Q05 – ¿Cuánto cuesta un viaje en Metro con tarjeta Cívica frecuente y cuánto el bus urbano en 2026?

- **Metro (tarjeta Cívica – perfil frecuente)**: 3 820 pesos por viaje.  
  Fuente: [tarifas_transporte_2026.md § Metro de Medellín]  

- **Bus urbano (tarifa básica)**: 3 000 pesos por viaje (tarifa estándar para el bus y la buseta ejecutiva es 3 250 pesos).  
  Fuente: [tarifas_transporte_2026.md § Buses urbanos de Medellín]  

*Nota*: El copiloto solo usa la tarifa del Metro como referencia; la tarifa de bus se conserva como dato documental y no se emplea para calcular rutas.

### Q06 – ¿Cuál es la estación de Metro más cercana a Plaza Mayor y a qué hora abre el Metro los domingos?

La estación de Metro más cercana a **Plaza Mayor** es **Alpujarra** (línea A), a unos 560 m de distancia, lo que equivale a unos 9 min de caminata [estaciones de OpenStreetMap; caminata estimada con supuestos (sistema_metro.md)].

En los **domingos** el Metro de Medellín abre aproximadamente a las **5:00 a.m.** y cierra a las 10:00 p.m. [sistema_metro.md § Horario general de operación].

### Q07 – Tengo un carro de placa terminada en 6 y quiero ir de Ciudad del Río al Estadio el próximo jueves 19 de noviembre de 2026 a las 5 p. m. ¿Puedo ir en carro? Si no, ¿cuánto tarda la ruta en bicicleta/a pie?

**Pico y placa**  
Tu placa termina en **6** y el jueves 19 de noviembre de 2026 está restringida de **5:00 a 20:00** (dígitos 3 y 6). La restricción se aplica a la mayoría de las vías de la ciudad y no hay indicación de que tu recorrido (Ciudad del Río → Estadio Atanasio Girardot) sea por una vía exenta. Por lo tanto, **no podrás circular en carro en ese horario**.  

> [pico_y_placa_2026_2.md § restricción jueves 5‑20 h, dígitos 3‑6]

**Alternativa en bicicleta**  
La ruta óptima calculada con el algoritmo A* sobre OpenStreetMap es:

- **Distancia:** 4.95 km  
- **Tiempo estimado:** **≈ 20 min** (19.8 min)  

> [Cálculo A* propio sobre red OpenStreetMap; velocidades y consumos estimados (metodologia_rutas.md)]

Así que, si decides ir en bicicleta, llegarás al estadio en unos 20 minutos. ¡Buen viaje!

### Q08 – ¿Cómo calcula el copiloto el tráfico en hora pico? ¿Usa datos en tiempo real?

El copiloto **no usa datos de tráfico en tiempo real**.  
Para el cálculo de la velocidad del carro se parte de una velocidad base (según el tipo de vía: 60 km/h, 45 km/h, 35 km/h o 25 km/h) y se le aplica un **factor de congestión** que depende de la hora de salida. En las horas pico (6 h, 7 h, 8 h, 17 h, 18 h y 19 h) el factor es **0,55**; en horas intermedias (9 h, 12 h, 13 h, 16 h y 20 h) es **0,8**; y en el resto es **1,0**. Estas velocidades son supuestos estáticos que alimentan el algoritmo A* (no mediciones reales) y se usan para estimar tiempo, costo y emisiones.  

> “No se usa tráfico en tiempo real. La velocidad del carro es una velocidad base … multiplicada por un factor de congestión según la hora de salida. Por defecto, en horas pico … el factor es 0,55 …” [metodologia_rutas.md § Velocidades estimadas y tráfico]

### Q09 – ¿Qué precio de gasolina y qué factor de emisión usa la herramienta para el carro, y de dónde salen?

La herramienta calcula el costo del viaje en carro usando:

* **Precio de la gasolina:** 4 293 pesos por litro (equivalente a 16 251 pesos por galón).  
  Fuente: Comisión de Regulación de Energía y Gas (Circular CREG 371 de 2026) – dato oficial de referencia para Medellín. 【[combustible_y_emisiones.md § Precio de la gasolina (dato oficial)]】

* **Factor de emisión de CO₂:** 2,31 kg de CO₂ por litro de gasolina consumido.  
  Fuente: Parámetros del copiloto, basados en el factor del IPCC (2006) y publicados por la UPME. 【[combustible_y_emisiones.md § Factores de emisión de CO2 (supuestos ajustables)]】

Estos valores se emplean en las fórmulas del modelo (litros = km × consumo/100; costo = litros × precio; CO₂ = litros × factor). 【[combustible_y_emisiones.md § Fórmulas usadas]】

### Q10 – Dame la ruta en carro que menos CO2 emite desde Unicentro Medellín hasta Parque del Poblado a las 2 p. m. y dime por qué vías va.

**Ruta en carro con menor emisión de CO₂ (optimizada por emisiones)**  

- **Origen:** Unicentro Medellín  
- **Destino:** Parque del Poblado  
- **Hora de salida:** 14:00 (2 p. m.)  
- **Distancia:** 5.19 km  
- **Tiempo estimado:** 9 min  
- **CO₂ emitido:** **0.96 kg**  

**Vías principales del itinerario** (según el cálculo A* sobre OpenStreetMap):  
1. Calle 34B  
2. Carrera 66A  
3. Calle 34  
4. Carrera 66B  
5. Carrera 67  
6. Carrera 65G  
7. Avenida Calle 14  
8. Rotonda Aeropuerto Olaya Herrera  

**Por qué es la ruta con menos CO₂:**  
El algoritmo A* seleccionó el camino más corto y con mayor velocidad promedio estimada, lo que reduce el tiempo de motor encendido y, por ende, el consumo de combustible y la emisión de CO₂. Al optimizar específicamente por “emisiones”, se priorizan tramos con menor congestión y mayor fluidez, minimizando la cantidad de combustible quemado.

> *Datos obtenidos del cálculo A* sobre la red OpenStreetMap con velocidades y consumos estimados (metodología del copiloto).*

### Q11 – Tengo un carro híbrido con placa terminada en 5. ¿Me aplica el pico y placa el lunes 16 de noviembre de 2026?

No, el pico y placa no le aplica a su vehículo. Los automóviles híbridos están exentos de la restricción de circulación en Medellín【pico_y_placa_2026_2.md § exención】.

### Q12 – ¿Cómo funciona EnCicla y cuánto cuesta usarla? ¿La ruta en bicicleta del copiloto usa ciclorrutas?

**EnCicla** es el sistema de bicicletas públicas del Valle de Aburrá.  

- **Funcionamiento:** el usuario se registra en línea (con documento de identidad) y, una vez aprobado, puede retirar una bicicleta en cualquiera de las estaciones del sistema. El préstamo tiene un tiempo máximo por viaje; si se supera, se aplican sanciones de suspensión del servicio. Las estaciones operan en horarios diurnos y, en general, no funcionan durante la noche【[encicla.md § Uso]】.  
- **Costo:** el uso del servicio es **gratuito** para los usuarios registrados; no se cobra tarifa por cada viaje【[encicla.md § Uso]】. (Las tarifas que aparecen en la documentación se refieren al Metro, no a EnCicla.)

**Ruta en bicicleta del copiloto**  
Cuando se solicita una ruta en modo “bicicleta”, el copiloto calcula el itinerario con el algoritmo A* sobre los datos de OpenStreetMap. El cálculo incluye **ciclorrutas y carriles bici** que estén mapeados en OSM, de modo que la ruta prioriza la infraestructura ciclista disponible. Esta información proviene de la metodología de cálculo de rutas del copiloto, que indica que la bicicleta siempre minimiza distancia y utiliza la red de vías ciclistas presente en el mapa【[metodologia_rutas.md § Costo multiobjetivo]】.  

En resumen: EnCicla es un servicio gratuito para usuarios registrados y la ruta en bicicleta que genera el copiloto aprovecha las ciclorrutas y carriles bici que aparecen en OpenStreetMap.

### Q13 – ¿Cuánto me demoro en bus desde Rionegro hasta Plaza Mayor?

Lo siento, pero el sistema no dispone de información centralizada sobre recorridos ni tiempos de los buses intermunicipales, por lo que no puedo calcular cuánto tardarías en viajar en bus desde Rionegro hasta Plaza Mayor.  

Si lo deseas, puedo ofrecerte estimaciones de tiempo, costo y emisiones para otros modos disponibles (carro, bicicleta/a pie o caminata + Metro Línea A) usando los cálculos A* sobre OpenStreetMap, o bien buscar la tarifa del bus si necesitas ese dato. ¡Solo indícame cómo prefieres proceder!

### Q14 – ¿Cuál es la multa exacta por no respetar el pico y placa?

Según la documentación disponible, la sanción económica por infringir el pico y placa en Medellín (segundo semestre 2026) se sitúa entre **≈ 633 000 y ≈ 712 000 pesos**, y además puede incluir la inmovilización del vehículo. Las fuentes de prensa difieren en el valor exacto, por lo que se recomienda confirmar el monto preciso con la Secretaría de Movilidad [​pico_y_placa_2026_2.md § Sanciones].
