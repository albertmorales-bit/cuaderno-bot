# Estado del proyecto

Última actualización: 2026-10-05 · **experimento en marcha (día 1 de 90).**

## Experimento en vivo

- Repositorio público: https://github.com/albertmorales-bit/cuaderno-bot ·
  web: https://albertmorales-bit.github.io/cuaderno-bot/
- Pre-registro: tag `v1.0-preregistro`, SHA-256
  `0bb34ef8951ef8814cb6ff3f451f7a39657217276479cefaea9ef84658de5354`.
- Día 0: 2026-10-04 18:24 UTC. Día 1: decisión del cierre del 04/10, órdenes
  en la apertura del 05/10 (la V8 entra al 100 % en BTC y ETH).
- Cambios posteriores al pre-registro: `CAMBIOS.md` (fe de erratas 1).

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

- **Fase 2 · Regímenes.** Conjunto Donchian + objetivo de volatilidad (V8),
  motor por exposición, clasificador de regímenes causal; criterios commiteados
  antes de ejecutar (`c02be78`). En desarrollo: (A) se cumple en volatilidad y
  fuerza, (B) en ninguno; la Fase 3 queda justificada por la regla
  (D-026). 71 tests.

- **Fase 4 (parte 1) · Robustez en desarrollo.** Criterios de aceptación v1
  commiteados antes de ejecutar (`06e7a06`). En desarrollo: meseta (C6 se
  cumple), resiste costes x3, Sharpe deflactado de 0,93, unas 1,3 entradas y
  10 órdenes esperadas en 90 días.
- **Fase 4 (parte 2) · Validación abierta una vez (2022-01 → 2024-07): NO APTO.**
  Gana dinero y recorta la caída a un tercio, pero no bate a tener un ~30 % fijo
  (C4 falla en BTC; DSR 0,24). Reserva final sin abrir (D-030).

- **Fase 5 · Motor en vivo.** Registro encadenado, motor idempotente con el mismo
  código que el backtest, test de repetición con igualdad exacta, reglas de
  seguridad y de parada, generador del pre-registro (con tuit verificado con
  `len()`), workflow de GitHub Actions con commit firmado vía API y sello
  OpenTimestamps, y `GUIA_PUBLICACION.md`. 95 tests. Probado contra Kraken real
  en un directorio temporal. D-031 a D-036.

- **Fase 6 · Salidas para X.** Resumen, tuit variable con doble control de
  longitud, comentario con enlaces, imagen e hilo semanal, generados cada día
  desde el registro (D-037). 102 tests.

- **Fase 7 · Web de transparencia.** Panel estático sin dependencias con botón
  "Verificar" (WebCrypto), verificación automática al cargar, curva completa,
  todas las operaciones, decisiones con régimen y motivo, avisos y
  pre-registro. Test de paridad JS-Python con Node. Despliegue de Pages en el
  mismo workflow (D-038, D-039). 106 tests.

### Añadido (Fase 0)

- v5 Donchian 20/10 (Turtle) con canal `shift(1)` (D-009).
- Partición dentro/fuera de muestra con embargo (`particionar_resultado`,
  `imprimir_reporte_particionado`), en el pipeline simple y en el multiactivo.
- Exportación para `significancia.py` y `pbo.py`.
- `requirements.txt`, `CLAUDE.md`, `DECISIONES.md`, `VALIDACION.md`, `README.md`.

## Falta

- Seguimiento diario de los 90 días (publicación manual en X con lo que deja
  el bot en `vivo/diario/`) y hilos semanales.
- Informe final al día 90 con lo pre-registrado (sección 4 de `PREREGISTRO.md`).
- El cuaderno de Colab es el de la v4: queda como histórico. Si hace falta, uno
  nuevo que use los `.py` del repositorio.
- Reserva final (2024-07 → 2026-05) sin abrir, guardada para una versión futura.

## Decisiones abiertas (del usuario)

- Ninguna. Si GitHub dejara un día sin ejecutar (vela perdida), valorar añadir
  más horarios de reintento al workflow, documentándolo en `CAMBIOS.md`.

## Cómo retomar

```powershell
cd C:\Users\alber\OneDrive\Escritorio\cuaderno-bot
.venv\Scripts\python -m pytest -q
```
