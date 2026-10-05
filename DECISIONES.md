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

**D-019b · Corte de la reserva corregido a 2026-05-01** (sustituye a D-019).
El usuario confirmó que las pruebas fueron después de marzo de 2026, y los
accesos directos de Windows (`%APPDATA%\Microsoft\Windows\Recent`) fechan las
7 versiones del cuaderno el 2026-09-04 entre las 20:48 y las 22:27, coherente
con que la v4 terminara sus datos el 2026-09-04 20:00. Todas las variantes
usaron la ventana de 720 velas de 4h 2026-05-07 → 2026-09-04. La reserva pasa a
2024-07-01 → 2026-05-01 (669 velas). Supuesto declarado: no hubo ejecuciones en
Colab anteriores a ese día que no dejaran rastro local.

## Fase 1b (2026-10-04)

**D-021 · Prioridades de investigación** (detalle y fuentes en
`INVESTIGACION.md`): núcleo de seguimiento de tendencia; tamaño por objetivo
de volatilidad; reversión a la media con prioridad baja (la evidencia para
BTC/ETH diario apunta a momentum, no a reversión); carry excluido; folclore
excluido.

**D-022 · Hallazgo sobre el tamaño de posición.** Con 1 % de riesgo y stop a
2xATR, la exposición mediana por operación en el tramo de desarrollo es del
10 % (BTC) y del 8 % (ETH) del capital del activo, unos 4-5 % del total con dos
activos. Pendiente de decisión del usuario: cómo dimensionar.

## Fase 2 (2026-10-04)

**D-023 · Candidata principal: conjunto Donchian + objetivo de volatilidad**
(aceptado por el usuario como "sigue" a las recomendaciones de la Fase 1b).
Tres sistemas solo largos con ventanas fijadas de antemano, 20/10 y 55/20 (los
dos sistemas Turtle originales) y 100/50; exposición = fracción de sistemas en
tendencia x min(1; 40 % / volatilidad realizada de 30 días). Sin filtro EMA200
en la candidata, para poder medirla en todos los regímenes. La v5 original se
mantiene como variante 7 de comparación.

**D-024 · Motor por exposición objetivo** (`modulo_4b_exposicion.py`).
Exposición decidida al cierre y ejecutada en la apertura siguiente; reajuste
solo si la desviación supera 10 puntos; entradas y salidas completas siempre;
compras limitadas por el efectivo; cada orden se registra con su precio de
referencia, comisión y slippage. Sin stop por ATR en la candidata: el canal de
salida de cada sistema hace de stop y el escalado por volatilidad limita el
riesgo. Calentamiento común de 400 velas para estrategias y benchmarks.

**D-025 · Regímenes con reglas simples y causales** (`modulo_5_regimenes.py`):
tendencia (SMA200 y pendiente), volatilidad (terciles del percentil
expansivo) y fuerza (ratio de eficiencia frente a su mediana expansiva). La
rentabilidad del día t se atribuye al régimen al cierre de t-1. Criterios de
la fase fijados antes de ejecutar en `informes/fase2/CRITERIOS.md`.

**D-026 · Resultado de la Fase 2** (`informes/fase2/RESULTADOS.md`). Según
los criterios pre-registrados, la Fase 3 queda JUSTIFICADA: (A) se cumple en
volatilidad (alta < baja) y en fuerza (fuerte > débil). (B) no se cumple en
ningún régimen. Parte del efecto (A) es mecánica (más exposición en baja
volatilidad y en tendencia fuerte). Cómo seguir: decisión del usuario.

## Fase 4 (2026-10-04)

**D-027 · Sin Fase 3.** El usuario eligió seguir con la recomendación (c):
pasar a la Fase 4 con la V8, sin segunda estrategia ni router. El contador de
variantes se queda en 8.

**D-028 · Criterios de aceptación v1** (`informes/fase4/CRITERIOS_ACEPTACION.md`),
commiteados antes de ejecutar nada de la Fase 4. Unidad de evaluación: cartera
50/50 en rentabilidades diarias (no operaciones: habrá menos de 30). Siete
condiciones (rentabilidad, caída, Sharpe frente a los dos benchmarks,
coherencia por activo, costes x2, meseta, regímenes) y dos pruebas
estadísticas (Sharpe deflactado y bootstrap emparejado) que separan APTO de
APTO CON RESERVAS. "Walk-forward": como ningún parámetro se ajusta con datos,
no hay nada que reajustar por ventanas; se evalúan ventanas anuales
independientes en desarrollo y la validación de una sola vez.

**D-029 · El test de repetición (backtest = vivo) pasa a la Fase 5**, donde se
construye el motor en vivo. Será condición para arrancar el día 1.

**D-030 · Veredicto de la validación: NO APTO** (2026-10-04, commit de
apertura e594140). Falla C4 (coherencia por activo: en BTC no bate a comprar y
mantener con la misma exposición). No se modifica ningún criterio ni parámetro
a posteriori. La reserva final sigue cerrada. Cómo seguir: decisión del usuario.

## Fase 5 (2026-10-04)

**D-031 · Paper trading con la V8 etiquetada NO APTO** (decisión del usuario)
y una cartera de comparación FIJO30 (30 % fijo en cada activo, mismos costes y
banda). No se cambia nada de la estrategia validada.

**D-032 · Registro encadenado** (`modulo_7_registro.py`). El hash se calcula
sobre el texto exacto de cada línea y el verificador no re-serializa, porque
Python y JavaScript escriben distinto algunos números (5000.0, 1e-05). Antes de
escribir, se verifica la cadena (con caché por tamaño y fecha de modificación).

**D-033 · Motor en vivo** (`modulo_8_vivo.py`). Usa exactamente las mismas
funciones que el backtest: `main.preparar_conjunto` para las señales y
`MotorExposicion.paso_apertura` para las órdenes. Es idempotente, registra la
decisión antes de ejecutar y no opera nunca sobre velas perdidas. El archivo
de velas parte de las 720 de Kraken: en desarrollo, arrancar con las últimas
720 velas da exactamente la misma exposición que la historia completa (0
diferencias en 269 días revisados). Test de repetición: igualdad exacta con el
backtest.

**D-034 · Reglas de seguridad** (`ReglasSeguridad`). Parada: caída del 35 % de la
cartera V8 (por encima del -23 % de validación y del -35 % del peor activo en
desarrollo), con liquidación en la siguiente apertura. Avisos sin efecto:
pérdida diaria del 10 %, semanal del 20 %, 3 días seguidos sin ejecutarse. Salto
de más del 50 % en una vela: ese día no se decide.

**D-035 · Ejecución en GitHub Actions**, con límites verificados en la
documentación oficial (2026-10-04): retrasos y ejecuciones perdidas en horas de
carga, cron desactivado tras 60 días sin actividad, eventos de `GITHUB_TOKEN`
que no crean otros workflows y pushes con `GITHUB_TOKEN` que no disparan Pages.
Solución: un único workflow (cron 00:17 y 02:47 UTC) que ejecuta, sella y hace
el commit; Pages se despliega desde el mismo workflow; commits por la API GraphQL
(`createCommitOnBranch`) para que salgan verificados, pendiente de comprobar en
el día 0.

**D-036 · OpenTimestamps: sí, como ancla adicional.** Gratis y sin cuenta; ancla
el hash del día en Bitcoin. Va en un paso que no bloquea si los calendarios
fallan. El cliente no funciona en Windows (libssl), así que en local el
pre-registro se sella desde la web de OpenTimestamps.

## Fase 6 (2026-10-04)

**D-037 · Salidas diarias desde el registro** (`modulo_9_salidas.py`), en
`vivo/diario/AAAA-MM-DD/`: resumen JSON y Markdown, tuit, comentario con los
enlaces, imagen y, los días 7, 14, 21... y el 90, un hilo semanal. El tuit
cambia cada día (8 plantillas rotatorias y una frase de contexto), pero siempre
lleva día N de 90, capital, resultado del día, caída y hash. Longitud doble:
`len()` con cada enlace a 23 y el peso real de X según twitter-text v3
(verificado en el repositorio oficial: "€", "…" o "→" cuentan 2). Imagen con la
paleta validada por el script del skill de visualización (todo PASS en claro
y oscuro), la curva completa desde el día 0 y la caída en un panel aparte.
Como referencia se añade comprar y mantener al 100 % (con los mismos costes),
que el pre-registro ya menciona. Los enlaces salen de `publicacion.json`, que no
forma parte de la configuración congelada.

## Fase 7 (2026-10-04)

**D-038 · Web de transparencia en GitHub Pages** (`web/`), HTML, CSS y JS a mano,
sin dependencias. La página recalcula todo a partir de `registro.jsonl`: día N
de 90, capital, resultado, caída actual y máxima de las tres carteras, curva
completa y caída con cursor y tooltip (también con el teclado) y tabla
equivalente, régimen y motivo de cada decisión, todas las órdenes con
comisión, slippage y funding, velas perdidas y avisos, y el pre-registro con su
SHA-256 calculado en el navegador. El botón "Verificar" recalcula la cadena con
WebCrypto; también se verifica al cargar, y si está rota aparece un aviso
destacado. Un test de paridad ejecuta el JavaScript real con Node y comprueba
que verifica y calcula exactamente lo mismo que Python. Probado en escritorio,
en móvil (375 px, sin scroll horizontal) y en modo oscuro, con una demostración
sintética marcada como tal (`scripts/construir_web.py --demo`).

**D-039 · Despliegue de Pages desde el mismo workflow** (límites verificados en
la documentación oficial el 2026-10-04: 1 GB, 100 GB/mes de tráfico, 10
minutos por despliegue; sin uso comercial). Trabajos `web` → `desplegar` con
`configure-pages@v5`, `upload-pages-artifact@v4` y `deploy-pages@v4`. La web se
publica aunque falle la ejecución del bot, y el checkout de `web` pide `main`
para recoger el commit que acaba de hacer el bot. El bot solo puede commitear en
`vivo/`.

## Experimento en marcha

**D-040 · Fe de erratas 1 (2026-10-05).** La presentación diaria pasa a valorar
cada cartera tras ejecutar las órdenes del día, a precio de apertura, para que
capital y comisiones describan el mismo instante. Cambian `modulo_9_salidas.py`,
`web/app.js` y `web/index.html`, que tienen huella en el pre-registro; detalle,
hashes y comprobación en `CAMBIOS.md`. Decisión del usuario: corregirlo con fe
de erratas pública, sin reiniciar el contador, porque la estrategia, la
configuración y el registro no cambian.
