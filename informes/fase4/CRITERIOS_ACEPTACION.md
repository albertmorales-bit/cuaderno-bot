# Criterios de aceptación · versión 1

> Dinero ficticio, no es asesoramiento financiero, resultados pasados no garantizan nada.

Fijados el 2026-10-04 y commiteados ANTES de abrir el tramo de validación.
Cualquier cambio posterior exige una versión 2 de este archivo, con el motivo,
antes de abrir la validación. Una vez abierta, no se cambian.

## Qué se evalúa

- **Estrategia:** variante 8 (`main.Configuracion()` en el commit de este
  archivo): conjunto Donchian 20/10, 55/20 y 100/50, solo largos, objetivo de
  volatilidad del 40 %, banda de reajuste de 10 puntos, comisión 0,80 % y
  slippage 0,10 % por orden, datos `datos/v1`.
- **Cartera:** 50 % BTC/EUR y 50 % ETH/EUR (5.000 € cada uno), sin rebalanceo
  entre activos, empezando **sin posición** el primer día de la ventana (como el
  paper trading). Los indicadores se calientan con la historia anterior.
- **Ventana de validación:** 2022-01-01 → 2024-07-01 (exclusiva). Se abre UNA
  sola vez con `scripts/fase4_validacion.py --abrir-validacion`.
- **Variantes probadas a la fecha:** 8 (para el Sharpe deflactado).
- **Benchmarks** en la misma ventana y con los mismos costes: comprar y mantener
  al 100 % (BH100), comprar y mantener con la exposición media de la estrategia
  (BHigual) y efectivo.

## Criterios

| # | Criterio | Dónde | Por qué |
|---|----------|-------|---------|
| C1 | Rentabilidad total de la cartera > 0 (bate al efectivo) | Validación | Un resultado que pierde dinero no es un éxito, se ajuste como se ajuste |
| C2 | Caída máxima de la cartera ≤ 50 % de la de BH100 | Validación | La promesa principal del seguimiento de tendencia es recortar las caídas |
| C3 | Sharpe de la cartera > Sharpe de BH100 **y** > Sharpe de BHigual | Validación | Exigencia del proyecto: mejorar al benchmark ajustado por riesgo |
| C4 | C1 y "Sharpe > BHigual" se cumplen también en BTC y en ETH por separado | Validación | Coherencia entre activos |
| C5 | C1 se sigue cumpliendo con costes x2 | Validación | Robustez ante costes peores de lo supuesto |
| C6 | Los 6 vecinos de la V8 en la rejilla (un paso en una sola dimensión) tienen un Sharpe ≥ 0,8 veces el de la V8 | Desarrollo | Meseta y no pico aislado |
| C7 | En días de régimen bajista, la V8 rinde más que BH100; en días alcistas, la V8 rinde más que 0 | Validación | Coherencia entre regímenes: protege en caídas y participa en subidas |

Rejilla de C6 (solo para medir robustez, nunca para elegir): objetivo de
volatilidad {30, 40, 50 %} x banda {5, 10, 20 puntos} x escala de ventanas
{0,75; 1; 1,25}. Cartera 50/50 en desarrollo, 2018-07-03 → 2022-01-01.

Estadística (no son condición de C1-C7, pero deciden el nivel del veredicto):
- **S1:** Sharpe deflactado de la cartera en validación, con 8 variantes, ≥ 0,90.
- **S2:** probabilidad por bootstrap emparejado (bloques de 20 días, 5.000
  remuestreos, semilla 12345) de que el Sharpe de la V8 supere al de BHigual ≥ 0,80.

## Veredicto

- **APTO**: C1-C7 y S1-S2.
- **APTO CON RESERVAS**: C1-C7 se cumplen, pero S1 o S2 no. Significa que el
  proceso es sólido y que la ventaja **no está demostrada estadísticamente**.
  Así se comunicaría.
- **NO APTO**: falla cualquiera de C1-C7. Se publica igual.

Además, si la validación tiene menos de 30 episodios (casi seguro), las
métricas por operación se declaran **insuficientes para concluir**, y el
veredicto se apoya en rentabilidades diarias.

## Qué pasa después

- APTO o APTO CON RESERVAS: Fase 5 (motor en vivo y pre-registro). El tramo de
  reserva (2024-07-01 → 2026-05-01) se abre una sola vez después del
  pre-registro, con C1-C5 y C7, y se publica sea cual sea el resultado.
- NO APTO: se publica el resultado. Decide el usuario: hacer el paper trading
  igualmente como demostración de transparencia (etiquetado NO APTO) o
  rediseñar. En ese caso la validación ya no es fuera de muestra, y solo
  quedarían la reserva y el paper trading.
