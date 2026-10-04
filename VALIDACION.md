# Validación

> Dinero ficticio, no es asesoramiento financiero, resultados pasados no garantizan nada.

Estado: **validación abierta el 2026-10-04 · veredicto NO APTO** (`informes/fase4/VALIDACION_RESULTADOS.md`). Criterios: `informes/fase4/CRITERIOS_ACEPTACION.md` v1. Reserva final sin abrir. Los criterios de aceptación se
fijarán y versionarán aquí ANTES de abrir el tramo de validación (Fase 4).

## Contador de variantes evaluadas

Cada configuración distinta que se evalúe con datos reales suma una. Este
número es el que se pasa a `significancia.py --variantes`.

| # | Variante | Datos | Resultado | Fecha |
|---|----------|-------|-----------|-------|
| 1-6 | v1-v4: cruce EMA20/50 con/sin filtro, umbrales ADX, 1/5/8 activos, pullback | Kraken 4h, **~120 días reales** (se pedían 3 años; la API solo da 720 velas) | PF 0,70-1,00, WR 30-38 %; última (v4, 8 activos): 60 operaciones, PF 0,70, -1,30 % | antes de 2026-10-04 |
| 7 | v5: Donchian 20/10 + EMA200, solo largos | datos/v1, desarrollo | BTC: CAGR +17 %, Sharpe 1,42, DD -11 %, 22 ops · ETH: +12 %, 1,10, -10 %, 13 ops | 2026-10-04 |
| 8 | Conjunto Donchian 20/10 + 55/20 + 100/50, objetivo de volatilidad 40 %, solo largos | datos/v1, desarrollo | BTC: CAGR +60 %, Sharpe 1,66, DD -35 %, 13 episodios · ETH: +52 %, 1,53, -21 %, 9 episodios (B&H: Sharpe 1,41 / 1,11; DD -83 % / -83 %) | 2026-10-04 |

**Total actual: 8.**

### Validación de la variante 8 (2022-01-01 → 2024-07-01, cartera 50/50)

| | V8 | Comprar y mantener 100 % | Comprar y mantener ~30 % |
|---|---:|---:|---:|
| Rentabilidad total | +22,6 % | +15,7 % | +17,5 % |
| Sharpe | 0,48 | 0,39 | 0,46 |
| Caída máxima | -23 % | -66 % | -24 % |

C1, C2, C3, C5, C6 y C7 se cumplen; **C4 no** (BTC: Sharpe 0,46 frente a 0,59
de comprar y mantener con la misma exposición). Sharpe deflactado 0,24;
P(Sharpe > ~30 % fijo) = 0,49. **NO APTO.** Las variantes 1-6 compartieron una ventana de ~4 meses y
costes irreales (0,06 % + 0,02 %), así que su "NO APTO" es débil, pero se dan
por cerradas y NO se vuelven a ejecutar (cada nueva mirada contaría como otra
variante).

## Tramos de datos (aprobados el 2026-10-04)

Datos: `datos/v1` (diario, EUR, fuente principal Coinbase; ver
`datos/v1/CALIDAD.md`). Fechas de inicio inclusivas y de fin exclusivas. Con
400 velas de calentamiento, el primer día operable es el 2016-05-31 en BTC y
el 2018-07-03 en ETH.

| Tramo | Fechas | Velas operables BTC / ETH | Qué contiene (descriptivo) | Uso |
|-------|--------|---------------------------|----------------------------|-----|
| Desarrollo | 2015-01-01 → 2022-01-01 | 2041 / 1278 | Tendencia 2016-17, oso 2018 (BTC -83 %, ETH -94 %), recuperación y lateral 2019, crash covid mar-2020, tendencia 2020-21 con caída de -52 % en may-jul 2021 | Todo el ajuste y el diagnóstico por regímenes |
| Validación | 2022-01-01 → 2024-07-01 | 912 / 912 | Oso 2022 (BTC -64 % en el año), tendencia 2023 hasta el máximo de mar-2024 | Se abre UNA vez, con criterios congelados |
| Reserva final | 2024-07-01 → 2026-05-01 | 669 / 669 | Corrección de 2024, tendencia hasta ene-2025, caída de -32 % a abr-2025, nuevo máximo oct-2025 y caída posterior | Se abre UNA vez, después del pre-registro |
| Contaminado | 2026-05-01 → 2026-10-01 | 153 / 153 | Ventana de las variantes 1-6: 2026-05-07 → 2026-09-04 (todas ejecutadas el 2026-09-04) | No cuenta como fuera de muestra |
| Paper trading | 90 días en vivo | — | — | Única prueba totalmente limpia |

Fecha de las variantes 1-6: los accesos directos de Windows muestran que las
7 versiones del cuaderno se abrieron el 2026-09-04 entre las 20:48 y las 22:27,
y las salidas de la v4 cubren 2026-05-07 → 2026-09-04 20:00. El corte en
2026-05-01 deja una semana de margen (D-019).

Límite: conocer de antemano la forma general de la validación y la reserva
(p. ej. "2022 fue bajista") es una contaminación leve e inevitable, que se
declara. Ninguna regla se elige mirando esos tramos.
