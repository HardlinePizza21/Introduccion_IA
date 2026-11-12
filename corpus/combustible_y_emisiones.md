# Combustible, costo y emisiones: parámetros del copiloto

Resumen elaborado por el equipo; consultado el 12 de noviembre de 2026.

## Precio de la gasolina (dato oficial)
Fuente: Comisión de Regulación de Energía y Gas, Circular CREG 371 de 2026, precios de referencia vigentes desde el 1 de noviembre de 2026, https://gestornormativo.creg.gov.co/gestor/entorno/docs/originales/Circular_CREG_371_2026/ (también reportado por Portafolio).
- Gasolina corriente en Medellín: 16.251 pesos por galón. El gobierno mantuvo el precio estable frente a octubre de 2026.
- Conversión: 1 galón = 3,785 litros, por lo que 16.251 pesos por galón equivalen a unos 4.293 pesos por litro.
- El precio final en cada estación de servicio puede variar respecto al de referencia.

## Consumo de combustible (supuestos ajustables)
- Carro particular en ciudad: 8 litros por cada 100 km (equivalente a 12,5 km por litro, unos 47 km por galón). Es un supuesto, no un dato medido; el usuario puede cambiarlo en el dashboard.
- Bus urbano diésel: 35 litros por cada 100 km, con una ocupación promedio supuesta de 30 pasajeros.
- No se debe confundir consumo (litros por 100 km) con autonomía: la autonomía depende del tamaño del tanque y no es necesaria para comparar rutas cortas.

## Factores de emisión de CO2 (supuestos ajustables)
- Gasolina: 2,31 kg de CO2 por litro. Diésel: 2,68 kg de CO2 por litro. Valores cercanos a los factores por defecto del IPCC (2006).
- La UPME publica los factores colombianos FECOC y una calculadora oficial (https://app.upme.gov.co/Calculadora_Emisiones1/new/calculadora.html); se recomienda verificar allí el valor vigente.
- Las emisiones del bus se reparten entre los pasajeros (emisión del bus dividida por la ocupación). La bicicleta se considera sin emisiones directas.

## Fórmulas usadas
- Litros de combustible de un tramo = longitud en km × consumo / 100.
- Costo del carro = litros × precio por litro. Costo del bus = tarifa fija (3.000 pesos), sin importar la distancia.
- CO2 = litros × factor de emisión (para el bus, dividido por la ocupación).
