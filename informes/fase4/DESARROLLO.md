# Fase 4 · Robustez en el tramo de desarrollo

> Dinero ficticio, no es asesoramiento financiero, resultados pasados no garantizan nada.

Todo con datos anteriores al 2022-01-01. Criterios: [`CRITERIOS_ACEPTACION.md`](CRITERIOS_ACEPTACION.md). Cada ventana empieza SIN posición (como el paper trading).

## 1. Desarrollo completo

| Estrategia | Rent. total | CAGR | Vol. | Sharpe | Sortino | Máx. DD |
|---|---|---|---|---|---|---|
| BTC/EUR V8 | +1,265 % | +59.7 % | 31 % | 1.66 | 2.58 | -35 % |
| BTC/EUR BH100 | +8,273 % | +120.9 % | 78 % | 1.41 | 2.10 | -83 % |
| BTC/EUR BHigual (33%) | +552 % | +39.9 % | 26 % | 1.40 | 2.08 | -41 % |
| ETH/EUR V8 | +328 % | +51.5 % | 30 % | 1.53 | 2.44 | -21 % |
| ETH/EUR BH100 | +701 % | +81.3 % | 97 % | 1.11 | 1.61 | -83 % |
| ETH/EUR BHigual (23%) | +152 % | +30.3 % | 23 % | 1.28 | 1.91 | -28 % |
| Cartera 50/50 V8 | +283 % | +46.9 % | 27 % | 1.58 | 2.39 | -20 % |
| Cartera 50/50 BH100 | +658 % | +78.5 % | 78 % | 1.14 | 1.63 | -70 % |
| Cartera 50/50 BHigual | +139 % | +28.2 % | 22 % | 1.26 | 1.83 | -25 % |

Cartera 50/50 (2018-07-03 → 2022-01-01), intervalos del 90 % por bootstrap de bloques de 20 días:

- V8: Sharpe [0.58, 2.56], CAGR [+12 %, +96 %], caída máxima [-39 %, -16 %]
- BH100: Sharpe [0.26, 2.10], caída máxima [-89 %, -48 %]
- P(Sharpe V8 > BH100) = 0.85 · P(Sharpe V8 > BHigual) = 0.81
- Sharpe deflactado con 8 variantes: 0.93 (umbral de azar 0.79 anual); contando también las 27 de la rejilla: 0.79

## 2. Año a año (cada año empieza sin posición)

| Año y activo | V8 rent. | BH100 rent. | V8 Sharpe | BH100 Sharpe | V8 DD | BH100 DD | Exposición |
|---|---|---|---|---|---|---|---|
| 2017 BTC/EUR | +153 % | +1157 % | 2.40 | 3.22 | -22 % | -38 % | 43% |
| 2018 BTC/EUR | -22 % | -73 % | -2.34 | -1.17 | -26 % | -80 % | 6% |
| 2019 BTC/EUR | +72 % | +88 % | 1.88 | 1.25 | -18 % | -48 % | 27% |
| 2019 ETH/EUR | +2 % | -8 % | 0.20 | 0.31 | -21 % | -63 % | 14% |
| 2020 BTC/EUR | +92 % | +263 % | 2.29 | 2.14 | -16 % | -54 % | 43% |
| 2020 ETH/EUR | +104 % | +410 % | 2.24 | 2.19 | -21 % | -62 % | 32% |
| 2021 BTC/EUR | +19 % | +66 % | 0.74 | 1.03 | -19 % | -52 % | 32% |
| 2021 ETH/EUR | +122 % | +431 % | 2.34 | 2.11 | -14 % | -56 % | 32% |

## 3. Sensibilidad a costes (cartera 50/50)

| Estrategia | Rent. total | CAGR | Vol. | Sharpe | Sortino | Máx. DD |
|---|---|---|---|---|---|---|
| costes x0.5 (0.40% + 0.05%) | +303 % | +49.0 % | 27 % | 1.63 | 2.48 | -20 % |
| costes x1 (0.80% + 0.10%) | +283 % | +46.9 % | 27 % | 1.58 | 2.39 | -20 % |
| costes x2 (1.60% + 0.20%) | +246 % | +42.6 % | 27 % | 1.46 | 2.21 | -21 % |
| costes x3 (2.40% + 0.30%) | +207 % | +37.9 % | 27 % | 1.33 | 2.01 | -23 % |

## 4. Rejilla de parámetros (C6: meseta)

| Estrategia | Rent. total | CAGR | Vol. | Sharpe | Sortino | Máx. DD |
|---|---|---|---|---|---|---|
| vol 30 %, banda 5, ventanas x0.75 | +213 % | +38.6 % | 21 % | 1.65 | 2.64 | -16 % |
| vol 30 %, banda 5, ventanas x1.0 | +186 % | +35.1 % | 20 % | 1.60 | 2.45 | -16 % |
| vol 30 %, banda 5, ventanas x1.25 | +186 % | +35.1 % | 20 % | 1.57 | 2.39 | -21 % |
| vol 30 %, banda 10, ventanas x0.75 | +208 % | +38.0 % | 22 % | 1.60 | 2.54 | -17 % |
| vol 30 %, banda 10, ventanas x1.0 | +192 % | +35.9 % | 21 % | 1.59 | 2.44 | -17 % |
| vol 30 %, banda 10, ventanas x1.25 | +185 % | +34.9 % | 21 % | 1.53 | 2.29 | -23 % |
| vol 30 %, banda 20, ventanas x0.75 | +218 % | +39.2 % | 22 % | 1.60 | 2.49 | -16 % |
| vol 30 %, banda 20, ventanas x1.0 | +198 % | +36.7 % | 21 % | 1.57 | 2.37 | -17 % |
| vol 30 %, banda 20, ventanas x1.25 | +183 % | +34.6 % | 23 % | 1.42 | 2.08 | -27 % |
| vol 40 %, banda 5, ventanas x0.75 | +318 % | +50.5 % | 27 % | 1.63 | 2.56 | -21 % |
| vol 40 %, banda 5, ventanas x1.0 | +276 % | +46.1 % | 26 % | 1.57 | 2.38 | -20 % |
| vol 40 %, banda 5, ventanas x1.25 | +270 % | +45.3 % | 27 % | 1.53 | 2.29 | -28 % |
| vol 40 %, banda 10, ventanas x0.75 | +309 % | +49.6 % | 28 % | 1.60 | 2.50 | -22 % |
| vol 40 %, banda 10, ventanas x1.0 ← V8 | +283 % | +46.9 % | 27 % | 1.58 | 2.39 | -20 % |
| vol 40 %, banda 10, ventanas x1.25 | +288 % | +47.4 % | 27 % | 1.56 | 2.34 | -27 % |
| vol 40 %, banda 20, ventanas x0.75 | +289 % | +47.4 % | 28 % | 1.51 | 2.32 | -22 % |
| vol 40 %, banda 20, ventanas x1.0 | +299 % | +48.5 % | 28 % | 1.56 | 2.36 | -23 % |
| vol 40 %, banda 20, ventanas x1.25 | +293 % | +47.9 % | 28 % | 1.54 | 2.28 | -30 % |
| vol 50 %, banda 5, ventanas x0.75 | +428 % | +61.0 % | 33 % | 1.61 | 2.49 | -25 % |
| vol 50 %, banda 5, ventanas x1.0 | +387 % | +57.3 % | 32 % | 1.58 | 2.39 | -24 % |
| vol 50 %, banda 5, ventanas x1.25 | +381 % | +56.7 % | 33 % | 1.54 | 2.30 | -32 % |
| vol 50 %, banda 10, ventanas x0.75 | +418 % | +60.0 % | 33 % | 1.58 | 2.45 | -26 % |
| vol 50 %, banda 10, ventanas x1.0 | +382 % | +56.8 % | 32 % | 1.56 | 2.36 | -24 % |
| vol 50 %, banda 10, ventanas x1.25 | +388 % | +57.4 % | 33 % | 1.54 | 2.30 | -31 % |
| vol 50 %, banda 20, ventanas x0.75 | +376 % | +56.3 % | 33 % | 1.51 | 2.30 | -23 % |
| vol 50 %, banda 20, ventanas x1.0 | +373 % | +55.9 % | 33 % | 1.50 | 2.25 | -25 % |
| vol 50 %, banda 20, ventanas x1.25 | +359 % | +54.6 % | 34 % | 1.46 | 2.15 | -32 % |

Sharpe de la V8: 1.58. Rejilla: mínimo 1.42, mediana 1.57, máximo 1.65. Vecinos: (0.3, 0.1, 1.0) → 1.59, (0.5, 0.1, 1.0) → 1.56, (0.4, 0.05, 1.0) → 1.57, (0.4, 0.2, 1.0) → 1.56, (0.4, 0.1, 0.75) → 1.60, (0.4, 0.1, 1.25) → 1.56.

**C6 SE CUMPLE**: todos los vecinos con Sharpe ≥ 0,8 x 1.58 = 1.26.

PBO de la rejilla (CSCV, 16 bloques, 12870 combinaciones): **0.94**. Informativo: aquí no se eligió la mejor celda (la V8 se fijó antes); mide cuánto engañaría elegir "la mejor" de esta rejilla.

## 5. Actividad esperada en 90 días (cartera de 2 activos)

- Entradas nuevas (episodios): 1.3 de media, IC 90 % 0-3.
- Órdenes (entradas, reajustes y salidas): 10.1 de media, IC 90 % 5-16.
- Con tan pocas operaciones, 90 días **demuestran el proceso, no la rentabilidad**.


## Interpretación (escrita DESPUÉS de ver los resultados)

- **Meseta clara.** El Sharpe de la cartera va de 1,42 a 1,65 en las 27
  combinaciones; la V8 (1,58) está en la mediana. Los resultados no dependen
  de haber acertado los parámetros.
- **PBO de 0,94: se lee junto a la meseta.** Con una rejilla tan plana, qué
  celda sale "la mejor" en una mitad de los datos es ruido, y en la otra mitad
  suele quedar por debajo de la mediana. Conclusión: **optimizar estos
  parámetros sería sobreajustar**. La V8 se fijó antes de mirar y no se cambia.
- **Costes.** Con costes x3 (2,4 % + 0,3 % por orden) el Sharpe baja de 1,58 a
  1,33. La estrategia aguanta comisiones peores, por su baja rotación.
- **Año a año.** La V8 no bate siempre a comprar y mantener en rentabilidad
  (nunca lo hace en los años alcistas), pero su caída máxima anual va del -14 %
  al -26 %, frente al -38 % / -80 % de comprar y mantener.
- **Riesgo de arranque.** En 2018, BTC pierde un -22 % con solo un 6 % de
  exposición media. La ventana empieza sin posición el 1 de enero, cuando los
  sistemas seguían "en tendencia" por el rally de 2017, así que la V8 compra el
  primer día y se come parte del desplome de enero. **Esto mismo puede pasar el
  día 1 del paper trading**: si el mercado está en tendencia, la V8 comprará
  nada más arrancar.
- **Estadística en desarrollo.** Sharpe deflactado de 0,93 con 8 variantes
  (0,79 contando la rejilla) y probabilidad de 0,81 de batir a comprar y
  mantener con la misma exposición. Es desarrollo, no fuera de muestra.
