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

## Tramos de datos (propuesta pendiente de aprobación)

| Tramo | Fechas | Uso |
|-------|--------|-----|
| Desarrollo | 2015-01 → 2021-12 | Todo el ajuste y el diagnóstico por regímenes |
| Validación | 2022-01 → 2024-06 | Se abre UNA vez, con criterios congelados |
| Reserva final | 2024-07 → 2026-06 | Se abre UNA vez, después del pre-registro |
| Contaminado | ~jun-oct 2026 | Ventana de las variantes 1-6; no cuenta como fuera de muestra |
| Paper trading | 90 días en vivo | Única prueba totalmente limpia |
