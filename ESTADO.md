# Estado del proyecto

Última actualización: 2026-10-04, fin de la Fase 1b.

## Hecho

- **Fase 0 · Auditoría y arreglos.** 44 tests pytest sin red, todos en verde,
  más comprobación por mutación (se reintroducen a propósito 7 fallos y los
  tests los detectan todos).

### Hallazgos de la auditoría de la v4 y su arreglo

| # | Gravedad | Hallazgo | Arreglo |
|---|----------|----------|---------|
| P1 | Crítico | Kraken solo da 720 velas: todos los backtests "de 3 años" fueron de ~120 días | Aviso de truncado en la descarga + aborto si cobertura < 95 % (D-011) |
| P2 | Alto, optimista | Stop no comprobado en la vela de entrada | Se comprueba (D-007) |
| P3 | Alto, optimista | Hueco por debajo del stop ejecutado al precio del stop | Se ejecuta a la apertura (D-007) |
| P4 | Alto | Reentrada automática tras stop/TP sin pasar filtros | Entradas solo por evento (D-008) |
| P5 | Alto | Costes 0,06 % + 0,02 %, muy lejos de la realidad | 0,80 % taker + 0,10 % (D-005) |
| P6 | Medio | Stop/TP evaluado antes que la salida por señal en la apertura | Orden real de eventos (D-007) |
| P7 | Medio (crítico en vivo) | Se usaba la vela en curso | `descartar_vela_en_curso` |
| P8 | Medio | Resultado dependía de la fecha de inicio (EMA sin calentar) | Calentamiento explícito (D-010) |
| P9 | Medio | Ventana relativa a "hoy": no reproducible | `fecha_inicio` / `fecha_fin` |
| P10 | Bajo | `dropna` de calentamiento inútil, `~bool`, Sortino inflado, salidas cruzadas largo/corto, fin de datos sin marcar | Corregidos y testeados |

No se encontró lookahead en el cálculo de indicadores ni en la ejecución por
señal de la v4 (ya ejecutaba en la apertura siguiente con el ATR anterior).

- **Fase 1 · Datos largos.** `datos/v1`: BTC/EUR diario 2015-04-27 → 2026-09-30
  (4175 velas) y ETH/EUR 2017-05-29 → 2026-09-30 (3412), Coinbase como
  principal, contrastado con Bitstamp, yfinance y Kraken. Sin huecos, con
  checksums verificados y reproducibles. Informe en `datos/v1/CALIDAD.md`;
  decisiones D-016 a D-020. Durante la fase se encontró y corrigió un fallo del
  paginador de ccxt (un lote vacío antes del inicio de cotización cortaba la
  descarga).

- **Fase 1b · Investigación.** `INVESTIGACION.md`: evidencia citada de
  tendencia, objetivo de volatilidad, combinación, carry y folclore, con
  recomendación priorizada (D-021). Hallazgo: el sizing actual deja la cartera
  invertida al 4-5 % (D-022).

### Añadido (Fase 0)

- v5 Donchian 20/10 (Turtle) con canal `shift(1)` (D-009).
- Partición dentro/fuera de muestra con embargo (`particionar_resultado`,
  `imprimir_reporte_particionado`), en el pipeline simple y en el multiactivo.
- Exportación para `significancia.py` y `pbo.py`.
- `requirements.txt`, `CLAUDE.md`, `DECISIONES.md`, `VALIDACION.md`, `README.md`.

## Falta

- Fase 2 (regímenes),
  3 (condicional), 4 (validación dura), 5 (motor en vivo), 6 (salidas X),
  7 (web de transparencia).
- El cuaderno de Colab es el de la v4: queda como histórico. Habrá que hacer
  uno nuevo que use los `.py` del repositorio.

## Decisiones abiertas (del usuario)

1. Tamaño de posición (D-022): mantener 1 % de riesgo por stop, u objetivo de volatilidad (y cuál).
2. Núcleo de la estrategia: Donchian 20/10 solo, o conjunto de ventanas fijado de antemano.
3. Email público en los commits: cambiar a *noreply* de GitHub antes del primer push.

Cerradas el 2026-10-04: diario, BTC/ETH en EUR, solo largos en contado, Kraken
taker 0,80 %, tramos de `VALIDACION.md` (reserva hasta 2026-05-01).

## Cómo retomar

```powershell
cd C:\Users\alber\OneDrive\Escritorio\cuaderno-bot
.venv\Scripts\python -m pytest -q
```
