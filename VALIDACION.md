# Validación

> Dinero ficticio, no es asesoramiento financiero, resultados pasados no garantizan nada.

Estado: **sin resultados válidos todavía.** Los criterios de aceptación se
fijarán y versionarán aquí ANTES de abrir el tramo de validación (Fase 4).

## Contador de variantes evaluadas

Cada configuración distinta que se evalúe con datos reales suma una. Este
número es el que se pasa a `significancia.py --variantes`.

| # | Variante | Datos | Resultado | Fecha |
|---|----------|-------|-----------|-------|
| 1-6 | v1-v4: cruce EMA20/50 con/sin filtro, umbrales ADX, 1/5/8 activos, pullback | Kraken 4h, **~120 días reales** (se pedían 3 años; la API solo da 720 velas) | PF 0,70-1,00, WR 30-38 %; última (v4, 8 activos): 60 operaciones, PF 0,70, -1,30 % | antes de 2026-10-04 |
| 7 | v5: Donchian 20/10 + EMA200, solo largos | (pendiente) | (pendiente) | — |

**Total actual: 7.** Las variantes 1-6 compartieron una ventana de ~4 meses y
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
| Reserva final | 2024-07-01 → 2026-03-01 | 608 / 608 | Corrección de 2024, tendencia hasta ene-2025, caída de -32 % a abr-2025, nuevo máximo oct-2025 y caída posterior | Se abre UNA vez, después del pre-registro |
| Contaminado | 2026-03-01 → 2026-10-01 | 214 / 214 | Ventanas de ~120 días de las variantes 1-6 (la v4 cubrió 2026-05-07 → 2026-09-04; las anteriores, antes) | No cuenta como fuera de muestra |
| Paper trading | 90 días en vivo | — | — | Única prueba totalmente limpia |

El corte de la reserva en 2026-03-01 es conservador: no se sabe la fecha
exacta de las primeras ejecuciones v1-v3. Si se conoce, puede ampliarse.

Límite: conocer de antemano la forma general de la validación y la reserva
(p. ej. "2022 fue bajista") es una contaminación leve e inevitable, que se
declara. Ninguna regla se elige mirando esos tramos.
