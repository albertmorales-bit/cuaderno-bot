# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Seguidores en X de @cuadernoalbert** (El Cuaderno de Albert) que siguen la serie "Día N de 90 con
  10.000 € ficticios": gente interesada en inversión y cripto. Llegan desde un tuit o una captura de
  pantalla y deciden en segundos si la serie es seria.
- **Posibles clientes del Auditor Anti-Overfitting** (kalculia.com/auditor): personas con estrategias
  sistemáticas que evalúan si Albert trabaja con rigor. El panel les sirve de prueba de método.
- **Albert**, que hace capturas de pantalla del panel en ordenador y las publica en X: la vista de
  escritorio debe entenderse de un vistazo en una sola captura.

## Product Purpose

Panel público de transparencia de un experimento de paper trading de 90 días (BTC/EUR y ETH/EUR, dinero
ficticio). Muestra cada día, recalculado en el navegador a partir de un registro encadenado con SHA-256,
el capital de tres carteras (V8, 30 % fijo y comprar y mantener), la curva completa, todas las órdenes
con sus costes, el motivo de cada decisión y el pre-registro. Éxito: que cualquiera pueda comprobar que
nada se ha maquillado ni retocado a posteriori, y que el seguimiento diario sea fácil de leer y de
compartir.

## Positioning

La estrategia está etiquetada NO APTO por su propia validación y se publica igual. El valor no es la
rentabilidad: es la transparencia verificable (botón "Verificar" que recalcula la cadena en el navegador,
pre-registro con hash anclado en X, motor que se niega a ejecutarse si cambia la configuración).

## Operating Context

- Se actualiza solo cada día (GitHub Actions) tras la ejecución del bot; GitHub Pages sirve el sitio.
- Se consulta sobre todo en escritorio para capturas y en móvil desde X.
- Lo leen tanto aficionados como gente con formación cuantitativa.

## Capabilities and Constraints

- Sitio estático (HTML, CSS y JavaScript a mano), sin frameworks ni dependencias de JavaScript: el código
  debe ser auditable. Todo se recalcula desde `registro.jsonl`.
- Los archivos de la web tienen huella SHA-256 en el pre-registro: cualquier cambio se documenta en
  `CAMBIOS.md` con los hashes de antes y de después.
- El cálculo de cifras debe coincidir exactamente con Python (`modulo_9_salidas.py`); hay test de paridad.

## Brand Commitments

- Identidad visual del Auditor Anti-Overfitting (kalculia.com/auditor), por decisión del usuario.
- Voz: honesta, clara y algo gamberra, nunca promesas de rentabilidad.
- Obligatorio y visible: "Dinero ficticio, no es asesoramiento financiero, resultados pasados no
  garantizan nada", la etiqueta NO APTO y que 90 días no demuestran rentabilidad.

## Evidence on Hand

Solo los datos reales del registro (`vivo/registro.jsonl`), el pre-registro y los informes del
repositorio. No hay testimonios, clientes, prensa ni métricas de terceros, y no deben inventarse.

## Product Principles

1. Las pérdidas se muestran con el mismo peso que las ganancias; siempre capital total y curva completa.
2. Todo número visible se puede verificar desde el registro público.
3. Legible de un vistazo en una captura de escritorio; el detalle, debajo.
4. Rigor sin frialdad: técnico pero comprensible para un aficionado.
