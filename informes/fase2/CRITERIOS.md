# Fase 2 · Criterios fijados ANTES de ver resultados

> Dinero ficticio, no es asesoramiento financiero, resultados pasados no garantizan nada.

Escritos y commiteados el 2026-10-04, antes de ejecutar
`scripts/fase2_regimenes.py` sobre datos reales. El commit que añade este
archivo es anterior al que añade los resultados.

## Pregunta

¿Rinde la estrategia de forma distinta según el régimen de mercado, de manera
**estable** (entre activos y entre mitades del periodo)? Si no, la idea de
regímenes no aporta y la Fase 3 (segunda estrategia y router) no se justifica.

## Datos y estrategias

- Solo el **tramo de desarrollo** de `datos/v1`: hasta el 2022-01-01
  (exclusiva). Primer día operable: BTC 2016-05-31, ETH 2018-07-03.
- **Variante 8 (candidata principal):** conjunto Donchian 20/10, 55/20 y 100/50,
  solo largos, exposición = fracción de sistemas en tendencia x
  min(1; 40 % / volatilidad de 30 días), banda de reajuste de 10 puntos,
  comisión 0,80 % y slippage 0,10 %. Sin filtro EMA200, para poder medirla en
  todos los regímenes.
- **Variante 7 (v5 original):** Donchian 20/10 + EMA200, 1 % de riesgo con stop
  2xATR. Se informa, pero el criterio se aplica a la variante 8 (la 7 está
  fuera del mercado por construcción cuando el precio está bajo la EMA200).
- Benchmarks: comprar y mantener al 100 %, comprar y mantener con la misma
  exposición media que la variante 8, y efectivo.

Contador de variantes tras esta fase: **8**.

## Regímenes (`modulo_5_regimenes.py`, reglas fijas)

- Tendencia: alcista / bajista / mixto (SMA200 y su pendiente a 20 días).
- Volatilidad: baja / media / alta (terciles del percentil expansivo de la
  volatilidad de 30 días).
- Fuerza: fuerte / débil (ratio de eficiencia de 50 días frente a su mediana
  expansiva).

La rentabilidad diaria del día t se atribuye al régimen al cierre de t-1.

## Métrica y prueba

- Métrica: rentabilidad media diaria neta de la estrategia, anualizada (x365),
  en los días de cada régimen.
- Intervalos: bootstrap circular por bloques de 20 días, 5.000 remuestreos,
  semilla 12345, intervalo del 90 %.
- "Conjunto": las series de BTC y ETH concatenadas.
- Mitades: cada activo se parte por la fecha central de su tramo operable de
  desarrollo.
- Mínimo: 60 días por régimen en cada activo y cada mitad. Si no se alcanza, ese
  régimen es "insuficiente para concluir".

## Criterios

**(A) Diferencia estable** entre los pares fijados de antemano (alcista frente
a bajista, alta frente a baja volatilidad, fuerte frente a débil) si se cumplen
las tres condiciones:
1. el intervalo del 90 % de la diferencia en el conjunto excluye el 0;
2. la diferencia tiene el mismo signo en BTC y en ETH por separado;
3. y el mismo signo en las dos mitades de cada activo.

**(B) Régimen "apagable"**: la media de la estrategia es negativa con el
intervalo del 90 % del conjunto por debajo de 0, y negativa en cada activo y en
cada mitad.

**Decisión:** la Fase 3 se justifica solo si se cumple **(B)** en algún régimen,
o **(A)** en la dimensión de volatilidad o de fuerza. Un (A) en la dimensión de
tendencia sola se considera esperable por construcción (un sistema de tendencia
apenas está invertido en régimen bajista) y no basta.

Cualquier router o filtro que salga de esta fase será una variante nueva que
sumará al contador.
