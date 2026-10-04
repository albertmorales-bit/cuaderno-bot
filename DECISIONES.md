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

## Fase 1 (2026-10-04)

**D-016 · Fuentes del histórico diario.** Sondeadas: yfinance, Coinbase
Exchange, Bitstamp, Bitfinex, Bitvavo, Gemini, Kraken. Elegidas:
- **Coinbase Exchange como principal**: exchange real en EUR con la historia más
  larga (BTC/EUR desde 2015-04-23, ETH/EUR desde 2017-05-23). Coincide con
  Kraken (el exchange del paper trading) en los 717 días comunes: mediana de
  diferencia de cierre 0,02 %, máximo 0,24 %.
- **Bitstamp como respaldo y contraste** (BTC desde 2016-04, ETH desde 2017-08).
- **yfinance solo como contraste**: es un agregado, no un mercado operable, y
  tiene 296 velas de BTC-EUR y 82 de ETH-EUR con OHLC incoherente (máximo por
  debajo del cierre, etc.).
- **Kraken solo como contraste** de los últimos 720 días.

**D-017 · Reglas de la serie limpia.** Nunca se interpola. Un hueco se rellena
con la vela del respaldo y queda marcado en la columna `fuente`. Los huecos sin
respaldo de los primeros 30 días (arranque del par) recortan el inicio. Un OHLC
incoherente se sustituiría por el respaldo (no hubo ninguno en Coinbase).
Resultado: BTC 4175 velas (1 rellenada con Bitstamp: 2016-07-12; inicio
recortado al 2015-04-27); ETH 3412 velas (inicio recortado al 2017-05-29).

**D-018 · Datos congelados y verificables.** `datos/v1` termina el 2026-10-01
(exclusiva). CSV deterministas (formato fijo, LF) con SHA-256 en
`MANIFIESTO.json`, que también registra el commit del código y si el árbol
estaba limpio. `cargar_historico` se niega a cargar un archivo que no coincida.
Una versión nunca se sobrescribe. Dos descargas independientes dieron los 10
checksums idénticos.

**D-019 · Tramos.** La reserva final termina el 2026-03-01 (no a mitad de 2026)
y desde ahí se marca como contaminado, porque las ventanas de ~120 días de las
variantes 1-6 acabaron, como tarde, el 2026-09-04 y empezaron antes del
2026-05-07 en las ejecuciones anteriores a la v4.

**D-020 · Limitaciones aceptadas de los datos.**
- Coinbase BTC/EUR era muy poco líquido en 2015 (volumen mediano ~61.000 €/día;
  el flash crash del 18-ago-2015 no aparece hasta el día siguiente). Ese año
  solo se usa como calentamiento: el primer día operable es el 2016-05-31.
- En diciembre de 2017 los exchanges en EUR divergieron hasta un 9 %: era una
  prima real entre mercados, no un error. Un backtest con precios de Coinbase
  en ese mes no habría tenido los mismos precios en Kraken.
- El volumen de Coinbase está en unidades del activo (BTC, ETH), no en EUR. La
  estrategia no lo usa.
- Sin histórico largo en 4h (D-001 se mantiene en diario).
