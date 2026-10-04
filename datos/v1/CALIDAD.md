# Calidad de datos · versión v1

Creada 2026-10-04T09:34:10Z con el commit `094a4a84a0`. Rango pedido 2014-01-01 → 2026-10-01 (exclusiva), velas 1d, marca de tiempo = apertura de vela, UTC; solo velas cerradas. Fuente principal **coinbase**, respaldo **bitstamp**. Checksums SHA-256 en `MANIFIESTO.json`.

> Dinero ficticio, no es asesoramiento financiero, resultados pasados no garantizan nada.

## BTC/EUR

### Fuentes

| Fuente | Proveedor | Velas | Desde | Hasta | Huecos | OHLC incoherente | Volumen 0 | Movimientos > 25 % |
|--------|-----------|------:|-------|-------|-------:|-----------------:|----------:|-------------------|
| coinbase | `coinbaseexchange:BTC/EUR` | 4176 | 2015-04-23 | 2026-09-30 | 3 | 0 | 0 | 2020-03-12 (-47%) |
| bitstamp | `bitstamp:BTC/EUR` | 3820 | 2016-04-16 | 2026-09-30 | 0 | 0 | 6 | 2020-03-12 (-48%) |
| yfinance | `yfinance:BTC-EUR` | 4397 | 2014-09-17 | 2026-09-30 | 0 | 296 | 0 | 2020-03-12 (-46%) |
| kraken | `kraken:BTC/EUR` | 717 | 2024-10-14 | 2026-09-30 | 0 | 0 | 0 | — |

### Comparación de cierres contra coinbase

| Fuente | Días comunes | Mediana | p95 | Máximo | Días > 2 % | Peores días |
|--------|-------------:|--------:|----:|-------:|-----------:|-------------|
| bitstamp | 3819 | 0.048 % | 0.861 % | 8.45 % | 63 | 2017-12-22 (8.5 %), 2017-12-23 (8.0 %), 2016-04-24 (7.6 %), 2017-12-06 (6.9 %) |
| yfinance | 4176 | 0.135 % | 1.342 % | 17.33 % | 79 | 2015-08-18 (17.3 %), 2017-12-22 (8.2 %), 2017-12-23 (6.4 %), 2017-12-24 (6.0 %) |
| kraken | 717 | 0.018 % | 0.083 % | 0.21 % | 0 | 2024-12-15 (0.2 %), 2024-11-13 (0.2 %), 2024-11-20 (0.2 %), 2024-12-16 (0.2 %) |

### Incidencias de la serie limpia

- 2015-04-25 · hueco: SIN DATO (hueco que permanece)
- 2015-04-26 · hueco: SIN DATO (hueco que permanece)
- 2016-07-12 · hueco: rellenado con bitstamp
- 2015-04-27 · recorte_inicio: serie recortada para empezar el 2015-04-27 (2 velas iniciales fuera por huecos de arranque)

Serie limpia: 4175 velas, 2015-04-27 → 2026-09-30, huecos 0, OHLC incoherente 0, filas por fuente {'coinbase': 4174, 'bitstamp': 1}.

### Cobertura de los tramos de la partición

Con 400 velas de calentamiento (D-010), el primer día operable es **2016-05-31**.

| Tramo | Fechas | Velas | Velas operables |
|-------|--------|------:|----------------:|
| Desarrollo | 2015-01-01 → 2022-01-01 | 2441 | 2041 |
| Validación | 2022-01-01 → 2024-07-01 | 912 | 912 |
| Reserva final | 2024-07-01 → 2026-05-01 | 669 | 669 |
| Contaminado (v1-v4) | 2026-05-01 → 2026-10-01 | 153 | 153 |

### Mapa descriptivo de épocas

Solo describe precios; no se ha usado para ajustar nada. Ojo: describir el tramo de validación y la reserva no los contamina para la estrategia mientras ninguna regla se elija mirándolos; aun así se deja constancia.

| Año | Rentabilidad | Volatilidad anualizada | Caída máx. en el año | Cierre > SMA200 |
|-----|-------------:|-----------------------:|---------------------:|----------------:|
| 2015 (parcial) | +89% | 52% | -33% | 20% |
| 2016 | +130% | 51% | -31% | 100% |
| 2017 | +1180% | 91% | -38% | 100% |
| 2018 | -73% | 84% | -80% | 17% |
| 2019 | +91% | 69% | -48% | 54% |
| 2020 | +270% | 79% | -54% | 77% |
| 2021 | +69% | 80% | -52% | 74% |
| 2022 | -63% | 62% | -64% | 1% |
| 2023 | +148% | 43% | -18% | 83% |
| 2024 | +125% | 52% | -27% | 78% |
| 2025 | -18% | 42% | -32% | 68% |
| 2026 (parcial) | -2% | 45% | -38% | 15% |

Ciclos de caída desde máximo histórico de más del 20%:

| Máximo | Mínimo | Caída | Recupera el máximo |
|--------|--------|------:|--------------------|
| 2015-07-12 | 2015-08-24 | -33% | 2015-10-29 |
| 2015-11-04 | 2015-11-11 | -23% | 2015-12-08 |
| 2015-12-18 | 2016-01-15 | -23% | 2016-05-28 |
| 2016-06-16 | 2016-08-02 | -31% | 2016-11-18 |
| 2017-01-04 | 2017-01-11 | -31% | 2017-02-23 |
| 2017-03-03 | 2017-03-24 | -29% | 2017-04-27 |
| 2017-06-11 | 2017-07-16 | -38% | 2017-08-05 |
| 2017-09-01 | 2017-09-14 | -35% | 2017-10-12 |
| 2017-11-05 | 2017-11-12 | -21% | 2017-11-16 |
| 2017-12-16 | 2018-12-15 | -83% | 2020-12-16 |
| 2021-01-08 | 2021-01-27 | -24% | 2021-02-08 |
| 2021-02-21 | 2021-02-28 | -21% | 2021-03-11 |
| 2021-04-13 | 2021-07-20 | -52% | 2021-10-18 |
| 2021-11-08 | 2022-11-21 | -74% | 2024-03-04 |
| 2024-03-13 | 2024-09-06 | -27% | 2024-10-29 |
| 2025-01-21 | 2025-04-08 | -32% | 2025-07-14 |
| 2025-10-06 | 2026-06-30 | -52% | aún no |

## ETH/EUR

### Fuentes

| Fuente | Proveedor | Velas | Desde | Hasta | Huecos | OHLC incoherente | Volumen 0 | Movimientos > 25 % |
|--------|-----------|------:|-------|-------|-------:|-----------------:|----------:|-------------------|
| coinbase | `coinbaseexchange:ETH/EUR` | 3416 | 2017-05-23 | 2026-09-30 | 2 | 0 | 0 | 2017-12-12 (+29%), 2020-03-12 (-54%), 2021-05-19 (-32%) |
| bitstamp | `bitstamp:ETH/EUR` | 3333 | 2017-08-16 | 2026-09-30 | 0 | 0 | 0 | 2020-03-12 (-57%), 2021-05-19 (-32%) |
| yfinance | `yfinance:ETH-EUR` | 3246 | 2017-11-11 | 2026-09-30 | 0 | 82 | 0 | 2020-03-12 (-54%), 2021-05-19 (-31%) |
| kraken | `kraken:ETH/EUR` | 717 | 2024-10-14 | 2026-09-30 | 0 | 0 | 0 | — |

### Comparación de cierres contra coinbase

| Fuente | Días comunes | Mediana | p95 | Máximo | Días > 2 % | Peores días |
|--------|-------------:|--------:|----:|-------:|-----------:|-------------|
| bitstamp | 3333 | 0.052 % | 0.549 % | 9.04 % | 40 | 2017-12-23 (9.0 %), 2017-12-12 (7.6 %), 2017-12-10 (7.4 %), 2017-12-22 (7.4 %) |
| yfinance | 3246 | 0.111 % | 1.172 % | 5.79 % | 43 | 2017-12-23 (5.8 %), 2021-11-25 (5.6 %), 2017-12-22 (5.5 %), 2021-01-03 (4.9 %) |
| kraken | 717 | 0.022 % | 0.097 % | 0.24 % | 0 | 2026-02-07 (0.2 %), 2026-06-21 (0.2 %), 2025-10-10 (0.2 %), 2024-11-12 (0.2 %) |

### Incidencias de la serie limpia

- 2017-05-27 · hueco: SIN DATO (hueco que permanece)
- 2017-05-28 · hueco: SIN DATO (hueco que permanece)
- 2017-05-29 · recorte_inicio: serie recortada para empezar el 2017-05-29 (4 velas iniciales fuera por huecos de arranque)

Serie limpia: 3412 velas, 2017-05-29 → 2026-09-30, huecos 0, OHLC incoherente 0, filas por fuente {'coinbase': 3412}.

### Cobertura de los tramos de la partición

Con 400 velas de calentamiento (D-010), el primer día operable es **2018-07-03**.

| Tramo | Fechas | Velas | Velas operables |
|-------|--------|------:|----------------:|
| Desarrollo | 2015-01-01 → 2022-01-01 | 1678 | 1278 |
| Validación | 2022-01-01 → 2024-07-01 | 912 | 912 |
| Reserva final | 2024-07-01 → 2026-05-01 | 669 | 669 |
| Contaminado (v1-v4) | 2026-05-01 → 2026-10-01 | 153 | 153 |

### Mapa descriptivo de épocas

Solo describe precios; no se ha usado para ajustar nada. Ojo: describir el tramo de validación y la reserva no los contamina para la estrategia mientras ninguna regla se elija mirándolos; aun así se deja constancia.

| Año | Rentabilidad | Volatilidad anualizada | Caída máx. en el año | Cierre > SMA200 |
|-----|-------------:|-----------------------:|---------------------:|----------------:|
| 2017 (parcial) | +266% | 125% | -62% | 8% |
| 2018 | -83% | 110% | -94% | 27% |
| 2019 | -6% | 81% | -63% | 39% |
| 2020 | +419% | 102% | -62% | 83% |
| 2021 | +441% | 107% | -56% | 97% |
| 2022 | -66% | 85% | -72% | 4% |
| 2023 | +85% | 46% | -25% | 78% |
| 2024 | +51% | 63% | -46% | 70% |
| 2025 | -22% | 75% | -62% | 43% |
| 2026 (parcial) | -7% | 61% | -53% | 16% |

Ciclos de caída desde máximo histórico de más del 20%:

| Máximo | Mínimo | Caída | Recupera el máximo |
|--------|--------|------:|--------------------|
| 2017-06-12 | 2017-07-16 | -62% | 2017-11-24 |
| 2018-01-13 | 2018-12-14 | -94% | 2021-01-24 |
| 2021-02-19 | 2021-02-28 | -27% | 2021-03-31 |
| 2021-05-11 | 2021-07-20 | -56% | 2021-10-20 |
| 2021-11-08 | 2022-06-18 | -77% | aún no |
