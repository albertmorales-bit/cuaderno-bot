# Decisiones técnicas

Cada decisión con su motivo. "Provisional" = recomendación aplicada por
defecto mientras el usuario no decida otra cosa.

## Fase 0 (2026-10-04)

**D-000 · Repositorio propio y LF.** Separado de las webs. `.gitattributes`
fuerza LF para que checksums y la cadena de hashes sean idénticos en Windows,
Colab y GitHub Actions.

**D-001 · Temporalidad diaria (provisional).** La API OHLC pública de Kraken
solo sirve 720 velas (4h = 120 días; 1d = ~2 años). No hay historia larga
gratuita y fiable en 4h desde Kraken; en diario sí hay varias fuentes desde
2014-15. Se revisará en la Fase 1 si los CSV históricos de Kraken permiten 4h.

**D-002 · Universo BTC/EUR y ETH/EUR (provisional).** Existen en Kraken
(comprobado vía ccxt), evitan conversión de divisa y minimizan el sesgo de
supervivencia que tendría una cesta de altcoins.

**D-003 · Solo largos, contado, sin apalancamiento (provisional).** Sin
funding, sin liquidaciones, sin riesgo de base. El carry queda como
investigación (Fase 1b).

**D-004 · Contador de variantes arranca en 7.** 6 configuraciones v1-v4
evaluadas + la v5. Ojo: las 6 se evaluaron sobre la MISMA ventana de ~120 días
(ver P1 en ESTADO.md), no sobre 3 años.

**D-005 · Costes por defecto: comisión 0,80 % y slippage 0,10 %.** Kraken Pro,
nivel 1 de volumen, tarifa oficial publicada el 9-jul-2026 (blog y página de
tarifas de Kraken, consultados el 2026-10-04): maker 0,40 %, taker 0,80 %. El
motor ejecuta a mercado en la apertura -> taker. Fuentes de terceros con cifras
más bajas (0,16/0,26 %) están desactualizadas; ccxt también trae esos valores
antiguos. El slippage del 0,10 % es una estimación pesimista para la apertura
diaria de BTC/EUR y ETH/EUR; la Fase 4 hará sensibilidad de 0,5x a 3x.
**Decisión abierta:** si se prefiere simular un exchange más barato, hay que
decidirlo antes del pre-registro.

**D-006 · Señal confirmada al cierre, ejecución en la apertura siguiente.** Ya
era así en la v4 (verificado). Se blinda con tests de mutación.

**D-007 · Orden de eventos dentro de la vela.** 1) cierre por señal o entrada
por evento a la apertura; 2) stop/take-profit dentro de la vela, incluida la de
entrada; 3) valoración al cierre. Con stop y TP en la misma vela, el stop
primero. Un hueco que abre más allá del stop se ejecuta a la apertura. El TP
nunca se ejecuta mejor que su nivel. Todo ello es deliberadamente pesimista.

**D-008 · Entradas por EVENTO, no por estado.** La v4 reabría en la vela
siguiente a un stop porque la señal seguía en 1 (estado arrastrado), sin
volver a pasar los filtros. Ahora el motor solo abre con la columna `entrada`
(evento ya filtrado). Cambia el número de operaciones respecto a la v4.

**D-009 · v5 = Turtle clásico.** Entrada: cierre > máximo de los `High` de las 20
velas anteriores (`shift(1)`). Salida: cierre < mínimo de los `Low` de las 10
anteriores, o stop a 2xATR. Sin take-profit (cortaría las tendencias largas,
que son la razón de ser del sistema) y sin filtro RSI (en una ruptura el RSI
está alto por definición; el filtro de sobrecompra bloquearía justo las
señales). Se usa el CIERRE para confirmar la ruptura, no el toque intravela,
para mantener "señal con vela cerrada, ejecución en la apertura siguiente".
Filtro EMA200 activo, ADX desactivado. Ambas opciones de RSI/TP quedan como
parámetros para comparar.

**D-010 · Calentamiento de 2x el periodo de la EMA más larga.** Una EMA
recursiva arrastra el valor de la primera vela con peso (1-alpha)^k: con
EMA200 y k=400 es ~1,8 %. Sin calentamiento, el resultado dependía de la fecha
de inicio de la descarga y el motor en vivo no reproduciría el backtest. En
diario cuesta 400 días de datos al principio. Además, el motor en vivo debe
calcular sobre el mismo histórico versionado (Fase 5).

**D-011 · Histórico truncado = error, no aviso.** Si la cobertura es menor del
95 % de lo pedido, el activo se aborta (la v4 avisaba y seguía).

**D-012 · `resultado_%` exportado = % sobre el capital de la cuenta.**
`significancia.py` compone esos porcentajes como curva de capital; la variación
del precio exageraría el riesgo real (cada posición es una fracción del capital).

**D-013 · Sortino con desviación a la baja estándar** (raíz de la media de
min(r,0)^2 sobre todos los periodos).

**D-014 · Redondeo del tamaño hacia abajo y tope con comisión.** `round()`
podía redondear hacia arriba y superar el riesgo objetivo. El tope sin
apalancamiento incluye la comisión de entrada. Se descartan órdenes por debajo
del mínimo del exchange (BTC 0,00005; ETH 0,001, Kraken vía ccxt).

**D-015 · No se ejecuta la v5 con datos reales en la Fase 0.** Los únicos datos
reales a mano (Kraken, ~2 años en diario) caen en el tramo que se propone
reservar como validación final; mirarlos ahora los contaminaría.
