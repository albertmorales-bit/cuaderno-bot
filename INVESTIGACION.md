# Investigación previa (Fase 1b)

> Dinero ficticio, no es asesoramiento financiero, resultados pasados no garantizan nada.

Revisión breve, con fuentes, de las familias de estrategias candidatas, antes
de diseñar nada más. Fecha: 2026-10-04.

**Advertencia de partida.** Ningún resultado publicado garantiza nada hoy.
McLean y Pontiff (2016) estiman que las anomalías publicadas rinden un 26 %
menos fuera de muestra y un 58 % menos después de publicarse. Además, cada
paper que se cita aquí es, a su vez, el superviviente de muchas pruebas que no
se publicaron. Las cifras de la literatura se usan para ordenar prioridades,
no como expectativa de rentabilidad.

## Cómo se califica la evidencia

| Nivel | Significado |
|-------|-------------|
| **A** | Varias décadas, muchos mercados, réplicas independientes, mecanismo plausible |
| **B** | Positiva pero con críticas serias, muestras cortas o dependencia de un solo periodo |
| **C** | Débil, contradictoria o solo en activos que no son los nuestros |
| **F** | Folclore de trading: popular, sin respaldo robusto |

## 1. Momentum de series temporales y seguimiento de tendencia

**Qué dice la evidencia.**
- Moskowitz, Ooi y Pedersen (2012) documentan momentum de series temporales en
  los 58 futuros líquidos que estudian (índices, divisas, materias primas,
  bonos): la rentabilidad de 1 a 12 meses persiste y luego revierte en parte.
  [SSRN](https://papers.ssrn.com/abstract=2089463)
- Hurst, Ooi y Pedersen (2017) lo extienden a datos desde 1880: rentabilidad
  positiva y baja correlación con los activos tradicionales durante más de un
  siglo. [AQR](https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing)
- **Críticas.** Huang, Li, Wang y Zhou (2020) encuentran poca evidencia activo
  por activo, y el beneficio de la estrategia es prácticamente igual al de una
  regla basada solo en la media histórica (es decir, buena parte viene de
  estar largo en activos que suben).
  [JFE 135(3)](https://ideas.repec.org/a/eee/jfinec/v135y2020i3p774-794.html)
  Kim, Tse y Wald (2016) muestran que el alfa mensual cae del 1,27 % al 0,41 %
  sin el escalado por volatilidad: gran parte del resultado es el escalado, no
  la señal. [JFM 30](https://works.bepress.com/yiuman-tse/10)

**En cripto.**
- Liu y Tsyvinski (2021) encuentran un efecto de momentum de series temporales
  fuerte en cripto, y que la atención de los inversores predice rentabilidades.
  [RFS 34(6)](https://ideas.repec.org/a/oup/rfinst/v34y2021i6p2689-2727..html)
- Detzel, Liu, Strauss, Zhou y Zhu (2021): el cociente precio / media móvil
  predice la rentabilidad diaria de bitcoin dentro y fuera de muestra.
  [Financial Management 50(1)](https://ideas.repec.org/a/bla/finmgt/v50y2021i1p107-137.html)
- Hudson y Urquhart (2021) prueban casi 15.000 reglas técnicas con
  correcciones por data snooping: hay predictibilidad, **pero no para bitcoin
  en su periodo fuera de muestra** (sí en otras criptos).
  [Annals of OR](https://link.springer.com/article/10.1007/s10479-019-03357-1)
- Zarattini, Pagani y Barbon (2025), documento de trabajo del Swiss Finance
  Institute: un conjunto de canales de Donchian con varias ventanas y tamaño
  por volatilidad, en una cartera rotatoria de las 20 criptos más líquidas,
  da Sharpe superior a 1,5 neto de costes según los autores. Aún no está
  revisado por pares, y su universo (20 monedas rotando) no es el nuestro.
  [IDEAS](https://ideas.repec.org/p/chf/rpseri/rp2580.html)

**Costes y riesgos.** Pocas operaciones (bueno con un 0,80 % de comisión),
pero muchas pequeñas pérdidas en mercados laterales y gran dependencia de unas
pocas tendencias largas. Con ~10 años de historia cripto hay 2-3 ciclos
completos: muestra corta para una estrategia que gana pocas veces y mucho.

**Compatibilidad.** Total: diario, solo largos, contado, 10.000 €.

**Nivel: A en futuros tradicionales; B en cripto** (muestra corta y resultados
mixtos para bitcoin en particular).

## 2. Objetivo de volatilidad (escalar la exposición)

**Qué dice la evidencia.**
- Moreira y Muir (2017): reducir la exposición cuando la volatilidad es alta
  aumenta el Sharpe de muchos factores y del carry de divisas.
  [NBER](https://www.nber.org/papers/22208)
- Harvey, Hoyle, Korgaonkar, Rattray, Sargaison y Van Hemert (2018), 60 activos
  desde 1926: sube el Sharpe en activos de riesgo (acciones, crédito), casi no
  cambia en bonos, divisas y materias primas, y **reduce las colas extremas en
  todos**. [JPM 45(1)](https://scholars.duke.edu/publication/1370354)
- **Crítica.** Cederburg, O'Doherty, Wang y Yan (2020): en comparación directa,
  las carteras gestionadas por volatilidad no baten sistemáticamente a las no
  gestionadas fuera de muestra. JFE 138(1), 95-117.

**En cripto.** No he encontrado evidencia revisada por pares específica de
BTC/ETH que pueda citar con seguridad. Se trata como hipótesis.

**Costes y riesgos.** Reajustar la posición cada día con un 0,80 % de comisión
sería ruinoso: hace falta reajustar solo cuando la desviación supere una
banda. Sin apalancamiento, solo puede reducir exposición, nunca subirla por
encima del 100 %.

**Compatibilidad.** Alta.

**Nivel: A como control del riesgo de cola; B como mejora de rentabilidad
ajustada.**

### Hallazgo propio que afecta a esto

Con el sizing actual (1 % de riesgo por operación, stop a 2xATR), calculado
**solo en el tramo de desarrollo**:

| Activo | ATR14 diario mediano | Exposición por operación (mediana, p10-p90) | Volatilidad anual |
|--------|---------------------:|--------------------------------------------:|------------------:|
| BTC/EUR | 5,1 % | 10 % (5-19 %) | 78 % |
| ETH/EUR | 6,5 % | 8 % (5-11 %) | 99 % |

Con dos activos, cada uno con medio capital, una operación abierta compromete
alrededor del **4-5 % de los 10.000 €**. La curva del bot sería casi plana
frente a comprar y mantener (100 % invertido). Comparar rentabilidades sería
engañoso en cualquier sentido. Hay dos remedios, no excluyentes:
1. Definir el tamaño por objetivo de volatilidad en vez de por distancia al stop.
2. Comparar también contra un benchmark de **comprar y mantener con la misma
   exposición media**, además de comprar y mantener al 100 % y del efectivo.

## 3. Combinar estrategias poco correlacionadas

**Qué dice la evidencia.** Diversificar entre fuentes de rentabilidad poco
correlacionadas mejora el Sharpe de la cartera (teoría clásica de carteras);
Asness, Moskowitz y Pedersen (2013, JF) documentan que valor y momentum están
negativamente correlacionados en muchos mercados.

**En nuestro universo.**
- BTC y ETH están muy correlacionados: diversificar entre ellos aporta poco.
- Diversificar entre **horizontes** de la misma señal (varias ventanas de
  Donchian a la vez, como hace Zarattini et al.) reduce la dependencia de
  haber elegido un parámetro concreto. Eso sí ayuda contra el sobreajuste.
- **Reversión a la media en BTC/ETH:** Zaremba, Bilgin, Long, Mercik y
  Szczygielski (2021, International Review of Financial Analysis 78, 101908)
  encuentran que la reversión diaria en cripto viene de las monedas ilíquidas;
  **las más grandes y negociables muestran momentum diario, no reversión**.
  Eso va en contra de la premisa de la Fase 3 para nuestros dos activos.

**Nivel: A para combinar ventanas de una misma señal; C para reversión a la
media diaria en BTC/ETH.**

## 4. Carry y funding en cripto

**Qué dice la evidencia.** Schmeling, Schrimpf y Todorov (BIS Working Paper
1087, 2023, revisado en 2025): el carry (diferencia futuro - contado, sobre
todo vía la tasa de funding de los perpetuos) ha llegado a superar el 40 %
anual, impulsado por inversores minoristas que persiguen la tendencia con
apalancamiento y por el poco capital de arbitraje. En la versión revisada, el
Sharpe de la estrategia cae en 2024 y **es negativo en 2025**.
[BIS](https://www.bis.org/publ/work1087.pdf)

**Riesgos.**
- Contraparte: el colapso de FTX (noviembre de 2022) borró saldos de clientes.
- Liquidación de la pata corta del perpetuo en subidas bruscas si el margen no
  alcanza.
- Base y funding que se dan la vuelta.
- Regulatorio: disponibilidad de perpetuos para minoristas en la UE, por
  verificar.

**Compatibilidad.** Baja. Necesita cuenta de derivados y margen, y no es swing
trading. Choca con la decisión D-003 (solo contado).

**Nivel: B históricamente, con rendimiento decreciente.** La tasa de funding
podría servir más adelante como **indicador de régimen** (largos apalancados
saturados), sin operar con ella; sería una variante más a contar.

## 5. Folclore de trading

Umbrales fijos de RSI (70/30), Fibonacci, ondas de Elliott, patrones de velas
y cruces de medias como señal aislada.
- Park e Irwin (2007) revisan la literatura: los estudios antiguos eran
  rentables, pero muchos tienen problemas de data snooping y los beneficios
  decaen con el tiempo. [J. Econ. Surveys 21(4)](https://ideas.repec.org/a/bla/jecsur/v21y2007i4p786-826.html)
- Sullivan, Timmermann y White (1999): al corregir por el universo completo de
  reglas probadas, la mejor regla sobre 100 años del Dow Jones deja de ser
  significativa en el periodo posterior.
  [JF 54](https://www.fmg.ac.uk/sites/default/files/2020-11/dp303.pdf)
- Nuestros propios resultados v1-v4 (cruces de EMA, 6 variantes, PF 0,70-1,00)
  encajan con esto, aunque con muestra corta.
- Los parámetros "Turtle" 20/10 no tienen nada de especial: vienen de la
  práctica de los años 80, no de un estudio. La familia (ruptura de canal) es
  seguimiento de tendencia; los números concretos, no.

**Nivel: F.**

## 6. Corrección por pruebas múltiples

Bailey y López de Prado (2014, JPM) proponen el Sharpe deflactado, que
descuenta el número de variantes probadas; Harvey, Liu y Zhu (2016, RFS)
proponen exigir t > 3 para un factor nuevo. Ya está en `validacion/` y el
contador de variantes va por 7.

*Nota: las tres referencias de esta sección y la de Asness et al. (2013) se
citan por su referencia bibliográfica, sin enlace verificado en esta sesión.*

## Recomendación priorizada

1. **Núcleo: seguimiento de tendencia diario en BTC/EUR y ETH/EUR, solo
   largos.** Mantener la ruptura de Donchian, pero como **conjunto de ventanas
   fijado de antemano** (por ejemplo los dos sistemas Turtle originales, 20/10
   y 55/20, más uno lento de 100/50), no como un 20/10 elegido. Ventanas decididas por la
   literatura y la práctica, **no ajustadas con nuestros datos**.
2. **Tamaño por objetivo de volatilidad** en vez de por distancia al stop, con
   tope del 100 % (sin apalancamiento) y bandas de reajuste para no pagar
   comisiones a diario. El stop por ATR se mantiene como protección.
3. **Fase 2 (regímenes) tal como estaba previsto**, sobre el tramo de
   desarrollo: ¿rinde la tendencia distinto según la volatilidad y la
   posición frente a la media de 200? Incluye "no operar" como régimen.
4. **Fase 3 (reversión a la media): prioridad baja.** La evidencia para BTC/ETH
   diario va en contra. Solo si la Fase 2 encuentra un régimen claro en el que
   la tendencia pierde, y dejando escrito que el punto de partida es escéptico.
5. **Carry: excluido** como estrategia (contraparte, derivados, rendimiento en
   descenso). Quizá en el futuro como indicador de régimen.
6. **Folclore: excluido.**

**Expectativa honesta.** El mejor caso realista, según la literatura, es una
rentabilidad parecida o menor que comprar y mantener, con caídas máximas
sensiblemente menores. Incluso eso puede no aparecer en nuestros datos, y 90
días de paper trading no bastan para demostrarlo: demostrarán el proceso.
