# Cambios después del pre-registro

> Dinero ficticio, no es asesoramiento financiero, resultados pasados no garantizan nada.

El pre-registro (`PREREGISTRO.md`, tag `v1.0-preregistro`) fija la estrategia,
la configuración, las reglas y las huellas SHA-256 de varios archivos. Aquí se
documenta, con su motivo, **cualquier** cambio posterior en un archivo con huella.
Ninguno de los cambios de esta lista toca la estrategia, la configuración
congelada, el motor ni el registro: el motor se niega a ejecutarse si cambia la
configuración, y su hash sigue siendo el del día 0
(`6ab80b0368056ab62a9311d46ce54101cae9062382968e4d59f603e785281cb4`).

## Fe de erratas 1 · 2026-10-05 · presentación de las cifras diarias

**Qué estaba mal.** El resumen, el tuit, la imagen y la web valoraban cada
cartera al **cierre** de la vela en la que se decidía, es decir, ANTES de
ejecutar la orden en la apertura siguiente, pero sumaban ya las comisiones de
esa orden. El día 1 mostraron "V8: 10.000 € (±0,00 % hoy)" con 79,37 € de
comisiones, cuando tras la compra la cartera valía 9.910,72 €. Las cuentas del
registro siempre fueron correctas: el fallo era solo de presentación.

**Corrección.** Cada día se valora cada cartera JUSTO DESPUÉS de ejecutar las
órdenes de la decisión, al precio de apertura al que se ejecutaron (comisiones
y slippage incluidos). Capital, resultado del día, caída, posiciones,
exposición y comisiones describen ahora el mismo instante. De paso, se amplía
el margen derecho de la imagen, donde una etiqueta se cortaba.

**Archivos con huella en el pre-registro que cambian:**

| Archivo | SHA-256 pre-registrado | SHA-256 nuevo |
|---|---|---|
| `modulo_9_salidas.py` | `2300febcaef2a53345536ebb405da3a4a385f643b2d0fb9ad8f6ed1a8d089c4d` | `5da7c3675712946e2fd307580e5477007d1a9eafbc20b40aa6a88d62cf045cae` |
| `web/app.js` | `3f5f1498a577ea56662a43be5f55fe15e5028185e0e00eaa425d94952e4f0678` | `d89253a52979cc1fe3796e44fb18405ed13b3b49553fd95eb853f90def0de2f7` |
| `web/index.html` | `8abd1e13eb4604f446db5e04e1da300fba734990a392817d3761f780d4b42d7e` | `d100f08bd2705d13cf464d8b76de5cc90160c44e4a35e9855f2b1233beb40f65` |

**Lo que no cambia:** estrategia, configuración (mismo hash), reglas de
seguridad, motor (`modulo_8_vivo.py`), registro encadenado
(`modulo_7_registro.py`) y verificación. No se reinicia el contador de días,
por decisión del usuario, porque el experimento (qué se decide, cuándo y a qué
precio) es idéntico.

**Lo que queda como estaba:** las salidas generadas por el bot el día 1
(`vivo/diario/2026-10-04/`) se conservan sin tocar, con el error, como
registro histórico. El tuit del día 1 se publicó con las cifras corregidas.

**Comprobación:** con el registro real del día 1, Python y la web (el mismo
JavaScript publicado, ejecutado con Node) dan exactamente V8 = 9.910,72 €,
30 % fijo = 9.972,98 €, comprar y mantener = 9.910,72 €. Hay tests de paridad.

## Cambio 2 · 2026-10-05 · rediseño visual de la web

**Qué cambia.** Solo la presentación de la web: identidad visual del Auditor
Anti-Overfitting (oscuro por defecto, Geist, acento dorado), una portada pensada
para leerse de un vistazo en una captura de escritorio (día N de 90 con pista de
90 casillas, valor de la V8 con resultado del día y caída, sus dos rivales,
curva completa, qué ve el bot hoy y sello de verificación calculado al cargar),
y el resto de secciones reordenadas. Pedido por el usuario.

**Lo que no cambia, comprobado:** las funciones `calcular()` y
`verificarCadena()` de `web/app.js` son idénticas carácter a carácter a las de
la fe de erratas 1, así que las cifras y la verificación son las mismas (test de
paridad con Python en verde). Estrategia, configuración, motor y registro, sin
cambios.

| Archivo | SHA-256 anterior (fe de erratas 1) | SHA-256 nuevo |
|---|---|---|
| `web/index.html` | `d100f08bd2705d13cf464d8b76de5cc90160c44e4a35e9855f2b1233beb40f65` | `4393b4067c58995f46c04b3df48aa99797c5f5d6677891db3633799bfcf2b9b0` |
| `web/styles.css` | `60023f2a74e42696438c93895f6a3e92af5b58581d421be07aab2aeff60becba` | `746b3ad3b96566f354ccbd91d3680105a90271cb6904815ae5957509ca5ddbc6` |
| `web/app.js` | `d89253a52979cc1fe3796e44fb18405ed13b3b49553fd95eb853f90def0de2f7` | `c72d3f37ed4fd2ee244c8f16a2ffd674abf422c3bf5b0e8f0976c0f159edc73e` |

La web carga la tipografía Geist desde Google Fonts, como la landing del Auditor.

## Observaciones operativas (sin cambios en ningún archivo)

- **2026-10-05:** GitHub no lanzó las ejecuciones programadas de las 00:17 ni de
  las 02:47 UTC; la única empezó a las 05:38 UTC. No cambia las cuentas: la
  decisión solo usa velas cerradas a las 00:00 UTC y la orden se simula en la
  apertura de las 00:00 UTC, como dice el pre-registro. Si algún día no llegara
  a ejecutarse, quedaría como vela perdida, a la vista en el panel.
