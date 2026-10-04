"""
=============================================================================
 BOT-PREDICT · MÓDULO 2 (v5): Estrategia — ruptura de canal de Donchian
             (Turtle 20/10) por defecto; PULLBACK (v4) y CRUCE EMA (v3)
             conservados para comparar + filtros de régimen (EMA200, ADX)

Cambios de la v5 (Fase 0, ver DECISIONES.md)
--------------------------------------------
- Nuevo disparador "ruptura_donchian" con canal calculado con shift(1).
- La señal ya no es un ffill de eventos: `ensamblar_estado` separa salidas
  de largos y de cortos, y se expone la columna `entrada` (evento filtrado)
  para que el motor no reabra posición tras un stop sin señal nueva.
- Calentamiento explícito (`calentamiento_ok`) para que el resultado no
  dependa de la fecha de inicio de la descarga.
- Filtro RSI opcional (`usar_filtro_rsi`).

Lo que sigue es la documentación histórica de la v4, que sigue vigente
para los disparadores "pullback" y "cruce_ema".
=============================================================================

Objetivo del módulo
--------------------
Convertir el DataFrame OHLCV estandarizado del Módulo 1 en una serie de
señales discretas mediante una única función parametrizada y VECTORIZADA
(sin bucles fila a fila en Python):

    1  -> Señal de compra / mantener largo
   -1  -> Señal de venta en corto (solo si permitir_cortos=True)
    0  -> Neutral / sin posición

Por qué esta versión existe: el veredicto de 4 backtests reales
-------------------------------------------------------------------
La v3 (cruce EMA 20/50 + filtro de régimen EMA200/ADX) se validó con 4
backtests reales independientes, de composición muy distinta (un activo
sin filtro, un activo con filtro, cesta de 5 activos, cesta de 8 activos;
12 meses y 3 años): en los tres casos con muestra informativa, el
resultado convergió sistemáticamente a Win Rate 35-38% y Profit Factor
alrededor de 1.00 (nunca claramente por encima) — ni ventaja real ni
pérdida catastrófica, un sistema que empata con el mercado antes de
comisiones. El diagnóstico de esa convergencia: los FILTROS DE RÉGIMEN
(EMA200 + ADX) no fueron señalados como la causa — se mantienen en esta
versión. El problema está en el DISPARADOR de entrada: el cruce de EMA
20/50 es, por construcción, una señal REZAGADA — dos medias que ya se
cruzaron implican que el movimiento que las cruzó ya ocurrió. En un
activo tan líquido y vigilado como BTC/USDT, es de las señales técnicas
más conocidas y más arbitradas que existen.

Qué cambia en la v4: entrada por PULLBACK, no por cruce
------------------------------------------------------------
En vez de esperar a que la EMA rápida cruce a la EMA lenta (evento lento,
doble suavizado), esta versión separa dos cosas que la v3 mezclaba en un
solo evento:

1. ESTRUCTURA de tendencia (estado, no evento): `ema_rapida > ema_lenta`
   para largos (`ema_rapida < ema_lenta` para cortos). Sustituye al
   "cruce" como confirmación de que la tendencia de corto/medio plazo
   sigue vigente, pero ahora se consulta como un ESTADO sostenido, no
   como el disparador en sí.
2. DISPARADOR de entrada (evento): un "reclamo" de la EMA rápida — el
   precio de cierre vuelve a superarla tras haber estado por debajo
   (`Close > ema_rapida` y `Close_prev <= ema_rapida_prev`), MIENTRAS la
   estructura de tendencia (1) sigue intacta. Esto es, en esencia,
   "comprar el retroceso dentro de una tendencia alcista ya establecida"
   en vez de "comprar en cuanto las dos medias se tocan" — se espera que
   entre más cerca del origen de la continuación del movimiento, no
   después de que ya se haya confirmado con el doble suavizado de la EMA
   lenta.

El antiguo cruce EMA-EMA no desaparece: pasa a ser la señal de SALIDA por
ruptura de estructura (si `ema_rapida` cruza a `ema_lenta` en contra de la
posición abierta, se cierra — la tendencia que sostenía la entrada ya no
existe). Los filtros de régimen (EMA200 + ADX) siguen aplicándose
ÚNICAMENTE a las entradas, exactamente igual que en la v3.

Para permitir una comparación A/B honesta contra la v3 (y no simplemente
asumir que el cambio es una mejora), se añade el parámetro
`disparador_entrada`: `"pullback"` (nuevo, por defecto) o `"cruce_ema"`
(comportamiento idéntico a la v3, conservado tal cual). Así, cualquier
resultado real de esta versión puede contrastarse contra la v3 sobre
EXACTAMENTE el mismo dato, cambiando un solo parámetro.

Limitación conocida, dicha sin rodeos
------------------------------------------
El "reclamo" de la EMA rápida es un evento más frecuente que el cruce de
dos EMAs (una sola media reacciona más rápido que dos), así que sin el
filtro de ADX podría generar más whipsaws en tramos donde el precio
oscila alrededor de la EMA rápida sin tendencia real. El filtro de ADX
existente debería filtrar la mayoría de esos casos, pero si un backtest
real muestra de nuevo muchas operaciones de baja calidad, el siguiente
paso razonable sería añadir un periodo de "enfriamiento" mínimo entre
reclamos consecutivos — no se implementa preventivamente aquí para no
añadir un parámetro más sin evidencia real que lo justifique.

Nota técnica: riesgo asimétrico largo vs. corto
--------------------------------------------------
Sin cambios respecto a la v3: el módulo sigue calculando una distancia de
stop-loss base asimétrica (ATR x2.0 en largo, ATR x1.5 en corto).
`permitir_cortos=False` por defecto, heredado de la prueba de estrés
post-auditoría 1.
=============================================================================
"""

from __future__ import annotations

import logging
from typing import Literal

import numpy as np
import pandas as pd

logger = logging.getLogger("bot_predict.estrategia")


# -----------------------------------------------------------------------
# Indicadores técnicos: pandas nativo (.ewm), sin dependencias externas.
# -----------------------------------------------------------------------

def calcular_ema(serie: pd.Series, periodo: int) -> pd.Series:
    """Media móvil exponencial (pondera más los precios recientes).

    `adjust=False` reproduce la fórmula recursiva clásica
    EMA_t = precio_t * alpha + EMA_{t-1} * (1 - alpha), la convención
    estándar en trading (en vez de la media ponderada exacta que usa
    pandas por defecto con adjust=True).
    """
    return serie.ewm(span=periodo, adjust=False).mean()


def _rango_verdadero(df: pd.DataFrame) -> pd.Series:
    """True Range de cada vela (incluye huecos frente al cierre anterior).

    Factorizado como helper independiente porque tanto `calcular_atr`
    como `calcular_adx` lo necesitan como paso intermedio — evita
    calcularlo dos veces con lógica duplicada.
    """
    high_low = df["High"] - df["Low"]
    high_cierre_prev = (df["High"] - df["Close"].shift(1)).abs()
    low_cierre_prev = (df["Low"] - df["Close"].shift(1)).abs()
    return pd.concat([high_low, high_cierre_prev, low_cierre_prev], axis=1).max(axis=1)


def calcular_atr(df: pd.DataFrame, periodo: int) -> pd.Series:
    """Average True Range: volatilidad absoluta reciente, incluyendo
    los huecos (gaps) entre el cierre anterior y la vela actual.
    """
    # Suavizado de Wilder: equivalente a una EMA con alpha = 1/periodo.
    return _rango_verdadero(df).ewm(alpha=1 / periodo, adjust=False).mean()


def calcular_rsi(serie: pd.Series, periodo: int) -> pd.Series:
    """Relative Strength Index (0-100): fuerza relativa de subidas vs.
    bajadas. >70 se interpreta como sobrecompra, <30 como sobreventa.
    """
    delta = serie.diff()
    ganancia = delta.clip(lower=0)
    perdida = -delta.clip(upper=0)

    media_ganancia = ganancia.ewm(alpha=1 / periodo, adjust=False).mean()
    media_perdida = perdida.ewm(alpha=1 / periodo, adjust=False).mean()

    fuerza_relativa = media_ganancia / media_perdida.replace(0, np.nan)
    rsi = 100 - (100 / (1 + fuerza_relativa))
    return rsi.fillna(100)  # Sin pérdidas en la ventana -> RSI = 100.


def calcular_adx(df: pd.DataFrame, periodo: int = 14) -> pd.Series:
    """Average Directional Index (0-100): fuerza de la tendencia, SIN
    indicar dirección (a diferencia de +DI/-DI, que sí son direccionales).

    Implementación clásica de Wilder, vectorizada con pandas/numpy:

    1. Movimiento direccional de cada vela:
       +DM = max(High_t - High_{t-1}, 0)  si supera al -DM, si no 0.
       -DM = max(Low_{t-1} - Low_t, 0)    si supera al +DM, si no 0.
    2. Se suavizan +DM, -DM y el True Range con el mismo suavizado de
       Wilder que ya usamos en ATR/RSI (alpha = 1/periodo).
    3. +DI = 100 * (+DM suavizado / TR suavizado); -DI análogo.
    4. DX = 100 * |+DI - -DI| / (+DI + -DI)  (asimetría direccional, 0-100).
    5. ADX = suavizado de Wilder de DX.

    Al ser un indicador con DOS suavizados encadenados (DM/TR, y luego
    DX->ADX), su fase de calentamiento es más larga que la de un
    indicador de un solo suavizado como el RSI — ver el enmascarado
    explícito de NaN en `generar_senales`.
    """
    subida_high = df["High"].diff()
    bajada_low = -df["Low"].diff()  # Low_{t-1} - Low_t, positivo si el mínimo baja.

    dm_mas = np.where((subida_high > bajada_low) & (subida_high > 0), subida_high, 0.0)
    dm_menos = np.where((bajada_low > subida_high) & (bajada_low > 0), bajada_low, 0.0)

    tr_suavizado = _rango_verdadero(df).ewm(alpha=1 / periodo, adjust=False).mean()
    dm_mas_suavizado = pd.Series(dm_mas, index=df.index).ewm(alpha=1 / periodo, adjust=False).mean()
    dm_menos_suavizado = pd.Series(dm_menos, index=df.index).ewm(alpha=1 / periodo, adjust=False).mean()

    di_mas = 100 * (dm_mas_suavizado / tr_suavizado.replace(0, np.nan))
    di_menos = 100 * (dm_menos_suavizado / tr_suavizado.replace(0, np.nan))

    suma_di = (di_mas + di_menos).replace(0, np.nan)
    dx = 100 * (di_mas - di_menos).abs() / suma_di
    dx = dx.fillna(0)  # Sin movimiento direccional neto -> DX = 0 (no NaN).

    adx = dx.ewm(alpha=1 / periodo, adjust=False).mean()
    return adx


def calcular_distancia_stop_atr(
    atr: pd.Series,
    direccion: pd.Series,
    atr_mult_largo: float = 2.0,
    atr_mult_corto: float = 1.5,
) -> pd.Series:
    """Lógica BASE del stop-loss asimétrico (se completa en el Módulo 3).

    Devuelve, para cada vela, la DISTANCIA en unidades de precio entre el
    precio de entrada y el stop-loss, según la dirección de la posición:
        - Largo -> atr * atr_mult_largo   (p.ej. 2.0x ATR)
        - Corto -> atr * atr_mult_corto   (p.ej. 1.5x ATR, más ceñido)
    """
    multiplicador = np.select(
        [direccion == 1, direccion == -1],
        [atr_mult_largo, atr_mult_corto],
        default=np.nan,
    )
    return atr * multiplicador


Disparador = Literal["pullback", "cruce_ema", "ruptura_donchian"]


def calcular_canal_donchian(df: pd.DataFrame, periodo: int) -> tuple[pd.Series, pd.Series]:
    """Canal de Donchian SIN lookahead: (máximo de High, mínimo de Low) de las
    `periodo` velas ANTERIORES a la actual.

    El `shift(1)` es la pieza crítica: sin él, el máximo incluiría el High de
    la propia vela que se está evaluando, y "Close > máximo" no podría darse
    nunca (o, con High en vez de Close, se daría con información que solo
    existe al cerrar esa vela). Con `shift(1)`, en la vela `i` el canal solo
    usa las velas `i-periodo .. i-1`, todas ya cerradas.
    """
    alto = df["High"].rolling(periodo, min_periods=periodo).max().shift(1)
    bajo = df["Low"].rolling(periodo, min_periods=periodo).min().shift(1)
    return alto, bajo


def ensamblar_estado(
    entrada_larga: np.ndarray,
    entrada_corta: np.ndarray,
    salida_larga: np.ndarray,
    salida_corta: np.ndarray,
) -> np.ndarray:
    """Máquina de estados de la señal (1 largo, -1 corto, 0 plano).

    Sustituye al antiguo `ffill` de eventos, que tenía dos fallos (auditoría
    Fase 0, P4 y P10): mezclaba en una sola serie las salidas de largos y de
    cortos (una salida de corto podía cerrar un largo) y dependía de
    `~permitir_cortos` sobre un bool de Python (~False == -1). Aquí cada
    salida solo afecta a su propia dirección, y una entrada en la vela
    manda sobre una salida en la misma vela (mismo criterio que la v4).

    Es un bucle de Python a propósito: con unas pocas decenas de miles de
    velas tarda milisegundos y es trivial de auditar.
    """
    n = len(entrada_larga)
    estado = np.zeros(n, dtype=int)
    actual = 0
    for i in range(n):
        if actual == 1 and salida_larga[i]:
            actual = 0
        elif actual == -1 and salida_corta[i]:
            actual = 0
        if entrada_larga[i]:
            actual = 1
        elif entrada_corta[i]:
            actual = -1
        estado[i] = actual
    return estado


def velas_de_calentamiento(
    disparador_entrada: str,
    ema_lenta: int,
    periodo_atr: int,
    periodo_rsi: int,
    usar_filtro_macro: bool,
    periodo_ema_macro: int,
    usar_adx: bool,
    periodo_adx: int,
    periodo_ruptura_entrada: int,
    factor_calentamiento_ema: float,
) -> int:
    """Número de velas iniciales en las que NO se permite entrar.

    Auditoría Fase 0 (P8): una EMA recursiva arrastra el valor de la primera
    vela descargada con peso (1 - alpha)^k. Con EMA200 y k=200 ese peso es
    ~13 %: el filtro dependería de la fecha en que empieza la descarga, y el
    motor en vivo (otra ventana) no reproduciría el backtest. Con
    `factor_calentamiento_ema=2` el peso residual baja a ~1,8 %; con 3, a
    ~0,25 %. Los indicadores de ventana finita (Donchian) solo necesitan su
    propia ventana.
    """
    periodos_ema = [periodo_atr, periodo_rsi]
    if disparador_entrada in ("pullback", "cruce_ema"):
        periodos_ema.append(ema_lenta)
    if usar_filtro_macro:
        periodos_ema.append(periodo_ema_macro)
    if usar_adx:
        periodos_ema.append(2 * periodo_adx)
    calentamiento = int(np.ceil(factor_calentamiento_ema * max(periodos_ema)))
    if disparador_entrada == "ruptura_donchian":
        calentamiento = max(calentamiento, periodo_ruptura_entrada + 1)
    return calentamiento


# -----------------------------------------------------------------------
# Generador de señales: función única, parametrizada.
# -----------------------------------------------------------------------

def generar_senales(
    df: pd.DataFrame,
    ema_rapida: int = 20,
    ema_lenta: int = 50,
    periodo_atr: int = 14,
    periodo_rsi: int = 14,
    rsi_sobrecompra: float = 70.0,
    rsi_sobreventa: float = 30.0,
    rsi_agotamiento_largo: float = 80.0,
    rsi_agotamiento_corto: float = 20.0,
    atr_pct_minimo: float = 0.0,
    permitir_cortos: bool = False,
    atr_mult_stop_largo: float = 2.0,
    atr_mult_stop_corto: float = 1.5,
    usar_filtro_macro: bool = True,
    periodo_ema_macro: int = 200,
    usar_adx: bool = True,
    periodo_adx: int = 14,
    umbral_adx: float = 22.0,
    disparador_entrada: Disparador = "pullback",
    periodo_ruptura_entrada: int = 20,
    periodo_ruptura_salida: int = 10,
    usar_filtro_rsi: bool = True,
    factor_calentamiento_ema: float = 2.0,
) -> pd.DataFrame:
    """Genera indicadores, eventos de entrada y la señal de estado.

    Parameters
    ----------
    df : pd.DataFrame
        Columnas ``Open, High, Low, Close, Volume`` (esquema del Módulo 1) e
        índice temporal ordenado. Solo velas CERRADAS.
    ema_rapida, ema_lenta : int
        EMAs de estructura (disparadores "pullback" y "cruce_ema").
    periodo_atr, periodo_rsi : int
        Ventanas del ATR (stop) y del RSI (filtro opcional).
    rsi_sobrecompra, rsi_sobreventa, rsi_agotamiento_largo, rsi_agotamiento_corto : float
        Umbrales del filtro RSI; solo actúan si `usar_filtro_rsi=True`.
    atr_pct_minimo : float
        ATR mínimo (fracción del precio) para permitir una entrada.
    permitir_cortos : bool
        Genera también señales en corto (-1). False por defecto.
    atr_mult_stop_largo, atr_mult_stop_corto : float
        Multiplicadores de ATR para la distancia de stop-loss base.
    usar_filtro_macro, periodo_ema_macro : bool, int
        Filtro de tendencia de fondo: largos solo con Close > EMA_macro.
    usar_adx, periodo_adx, umbral_adx : bool, int, float
        Filtro de fuerza de tendencia: entradas solo con ADX >= umbral.
    disparador_entrada : "pullback" | "cruce_ema" | "ruptura_donchian"
        - "pullback" (v4): el cierre reclama la EMA rápida dentro de la
          estructura EMA rápida/lenta. Sale por cruce EMA en contra.
        - "cruce_ema" (v3): entra en el cruce EMA rápida/lenta. Sale por
          cruce en contra.
        - "ruptura_donchian" (v5): entra cuando el CIERRE supera el máximo
          de las `periodo_ruptura_entrada` velas anteriores (sistema Turtle
          clásico, 20). Sale cuando el cierre pierde el mínimo de las
          `periodo_ruptura_salida` velas anteriores (10). Se usa el cierre
          (no un toque intravela) para que la señal se confirme con la vela
          cerrada y se ejecute en la apertura siguiente.
    periodo_ruptura_entrada, periodo_ruptura_salida : int
        Ventanas del canal de Donchian de entrada y de salida.
    usar_filtro_rsi : bool
        Si True (comportamiento v3/v4), bloquea entradas en sobrecompra /
        sobreventa y fuerza salidas por agotamiento. En una ruptura el RSI
        suele estar alto por definición, así que la v5 lo desactiva.
    factor_calentamiento_ema : float
        Ver `velas_de_calentamiento`.

    Returns
    -------
    pd.DataFrame
        Copia de `df` con indicadores y, además:
        - ``evento_entrada_largo``: evento bruto de entrada larga, sin filtros
          (para el diagnóstico de embudo de `main.py`).
        - ``entrada``: evento de entrada YA filtrado (1 / -1 / 0). El motor de
          backtest solo abre posición con este evento, nunca con el estado:
          así no se reabre tras un stop sin una señal nueva (auditoría P4).
        - ``senal``: estado sostenido (1 / -1 / 0) para cerrar por señal.
        - ``calentamiento_ok``: False en las velas de calentamiento.
    """
    if disparador_entrada not in ("pullback", "cruce_ema", "ruptura_donchian"):
        raise ValueError(
            "disparador_entrada debe ser 'pullback', 'cruce_ema' o 'ruptura_donchian', "
            f"recibido: '{disparador_entrada}'."
        )
    df = df.copy()
    indice = df.index

    # 1) Indicadores base. Todos son causales (EMA recursiva, diff, shift).
    df["ema_rapida"] = calcular_ema(df["Close"], ema_rapida)
    df["ema_lenta"] = calcular_ema(df["Close"], ema_lenta)
    df["atr"] = calcular_atr(df, periodo_atr)
    df["atr_pct"] = df["atr"] / df["Close"]
    df["rsi"] = calcular_rsi(df["Close"], periodo_rsi)

    n_calentamiento = velas_de_calentamiento(
        disparador_entrada, ema_lenta, periodo_atr, periodo_rsi, usar_filtro_macro,
        periodo_ema_macro, usar_adx, periodo_adx, periodo_ruptura_entrada,
        factor_calentamiento_ema,
    )
    calentamiento_ok = pd.Series(np.arange(len(df)) >= n_calentamiento, index=indice)
    df["calentamiento_ok"] = calentamiento_ok

    # 2) Filtros de régimen (solo sobre ENTRADAS).
    verdadero = pd.Series(True, index=indice)
    if usar_filtro_macro:
        df["ema_macro"] = calcular_ema(df["Close"], periodo_ema_macro)
        filtro_macro_largo = df["Close"] > df["ema_macro"]
        filtro_macro_corto = df["Close"] < df["ema_macro"]
    else:
        filtro_macro_largo = filtro_macro_corto = verdadero
    if usar_adx:
        df["adx"] = calcular_adx(df, periodo_adx)
        filtro_adx = df["adx"] >= umbral_adx
    else:
        filtro_adx = verdadero

    # 3) Eventos de entrada brutos y salidas propias de cada disparador.
    estructura_alcista = df["ema_rapida"] > df["ema_lenta"]
    estructura_bajista = df["ema_rapida"] < df["ema_lenta"]
    cruce_alcista = estructura_alcista & (df["ema_rapida"].shift(1) <= df["ema_lenta"].shift(1))
    cruce_bajista = estructura_bajista & (df["ema_rapida"].shift(1) >= df["ema_lenta"].shift(1))

    if disparador_entrada == "pullback":
        reclamo_alcista = (df["Close"] > df["ema_rapida"]) & (
            df["Close"].shift(1) <= df["ema_rapida"].shift(1)
        )
        reclamo_bajista = (df["Close"] < df["ema_rapida"]) & (
            df["Close"].shift(1) >= df["ema_rapida"].shift(1)
        )
        evento_largo = reclamo_alcista & estructura_alcista
        evento_corto = reclamo_bajista & estructura_bajista
        salida_larga = cruce_bajista
        salida_corta = cruce_alcista
    elif disparador_entrada == "cruce_ema":
        evento_largo = cruce_alcista
        evento_corto = cruce_bajista
        salida_larga = cruce_bajista
        salida_corta = cruce_alcista
    else:  # ruptura_donchian
        alto_entrada, bajo_entrada = calcular_canal_donchian(df, periodo_ruptura_entrada)
        alto_salida, bajo_salida = calcular_canal_donchian(df, periodo_ruptura_salida)
        df["donchian_alto_entrada"] = alto_entrada
        df["donchian_bajo_entrada"] = bajo_entrada
        df["donchian_alto_salida"] = alto_salida
        df["donchian_bajo_salida"] = bajo_salida
        # Comparaciones contra NaN (inicio del canal) dan False: no hay evento.
        evento_largo = df["Close"] > alto_entrada
        evento_corto = df["Close"] < bajo_entrada
        salida_larga = df["Close"] < bajo_salida
        salida_corta = df["Close"] > alto_salida

    # 4) Filtros de calidad (opcionales) y salidas por agotamiento de RSI.
    filtro_volatilidad = df["atr_pct"] >= atr_pct_minimo
    if usar_filtro_rsi:
        filtro_rsi_largo = df["rsi"] < rsi_sobrecompra
        filtro_rsi_corto = df["rsi"] > rsi_sobreventa
        salida_larga = salida_larga | (
            (df["rsi"] > rsi_agotamiento_largo) & (df["rsi"].shift(1) <= rsi_agotamiento_largo)
        )
        salida_corta = salida_corta | (
            (df["rsi"] < rsi_agotamiento_corto) & (df["rsi"].shift(1) >= rsi_agotamiento_corto)
        )
    else:
        filtro_rsi_largo = filtro_rsi_corto = verdadero

    entrada_larga = (
        evento_largo & filtro_rsi_largo & filtro_volatilidad & filtro_macro_largo
        & filtro_adx & calentamiento_ok
    )
    entrada_corta = (
        evento_corto & filtro_rsi_corto & filtro_volatilidad & filtro_macro_corto
        & filtro_adx & calentamiento_ok
    )
    if not permitir_cortos:
        entrada_corta = pd.Series(False, index=indice)

    # 5) Columnas de salida: evento bruto, evento filtrado y estado.
    df["evento_entrada_largo"] = evento_largo.fillna(False).astype(bool)
    df["entrada"] = np.where(entrada_larga, 1, np.where(entrada_corta, -1, 0))
    df["senal"] = ensamblar_estado(
        entrada_larga.to_numpy(dtype=bool),
        entrada_corta.to_numpy(dtype=bool),
        salida_larga.fillna(False).to_numpy(dtype=bool),
        salida_corta.fillna(False).to_numpy(dtype=bool),
    )

    # 6) Distancia de stop-loss base (asimétrica), previsualización del Módulo 3.
    df["distancia_stop_atr"] = calcular_distancia_stop_atr(
        df["atr"], df["senal"], atr_mult_stop_largo, atr_mult_stop_corto
    )

    logger.info(
        "Señales (%s): %d entradas largas, %d cortas | %d velas de calentamiento.",
        disparador_entrada, int((df["entrada"] == 1).sum()),
        int((df["entrada"] == -1).sum()), n_calentamiento,
    )
    return df


# -----------------------------------------------------------------------
# Conjunto de sistemas de ruptura (Fase 2, D-023)
# -----------------------------------------------------------------------

def generar_senales_conjunto(
    df: pd.DataFrame,
    sistemas: tuple[tuple[int, int], ...] = ((20, 10), (55, 20), (100, 50)),
    periodo_atr: int = 14,
    velas_calentamiento: int = 400,
) -> pd.DataFrame:
    """Conjunto de sistemas Donchian (solo largos), cada uno con su propia
    ventana de entrada y de salida, fijadas de antemano (no ajustadas).

    Cada sistema `k` es una máquina de estados 0/1: entra cuando el cierre
    supera el máximo de las `entrada_k` velas anteriores y sale cuando pierde
    el mínimo de las `salida_k` anteriores (canales con `shift(1)`). La
    columna `senal_conjunto` es la media de los estados (0, 1/3, 2/3, 1 con
    tres sistemas): la fracción de sistemas que están "en tendencia" al
    CIERRE de cada vela. Se ejecuta en la apertura siguiente (Módulo 4b).

    `velas_calentamiento` es fijo (no derivado de los sistemas) para que
    todas las variantes y los benchmarks empiecen el mismo día (D-010).
    """
    if len(df) <= velas_calentamiento:
        raise ValueError("No hay velas suficientes tras el calentamiento.")
    df = df.copy()
    falso = np.zeros(len(df), dtype=bool)
    estados = []
    for entrada, salida in sistemas:
        if salida >= entrada:
            raise ValueError(f"Sistema {entrada}/{salida}: la salida debe ser más corta que la entrada.")
        alto, _ = calcular_canal_donchian(df, entrada)
        _, bajo = calcular_canal_donchian(df, salida)
        estado = ensamblar_estado(
            (df["Close"] > alto).to_numpy(dtype=bool), falso,
            (df["Close"] < bajo).to_numpy(dtype=bool), falso,
        )
        columna = f"estado_{entrada}_{salida}"
        df[columna] = estado
        estados.append(columna)

    df["atr"] = calcular_atr(df, periodo_atr)
    df["calentamiento_ok"] = np.arange(len(df)) >= velas_calentamiento
    df["senal_conjunto"] = df[estados].mean(axis=1).where(df["calentamiento_ok"], 0.0)
    return df


# =============================================================================
# Bloque de auto-verificación: datos simulados (tendencia + tramo lateral)
# para comprobar que el filtro de régimen realmente reduce las señales en
# la parte sin tendencia, sin depender de red ni de las APIs del Módulo 1.
# =============================================================================
if __name__ == "__main__":
    rng = np.random.default_rng(42)
    n = 900
    indice = pd.date_range("2023-01-01", periods=n, freq="4h", tz="UTC")

    # Primer tercio: tendencia alcista clara. Segundo tercio: lateral puro
    # (ruido sin deriva). Tercer tercio: tendencia alcista de nuevo.
    tramo_tendencia_1 = np.linspace(0, 30, n // 3)
    tramo_lateral = np.zeros(n // 3)
    tramo_tendencia_2 = np.linspace(0, 25, n - 2 * (n // 3))
    deriva = np.concatenate([tramo_tendencia_1, tramo_lateral, tramo_tendencia_2])
    precio_base = 100 + np.cumsum(rng.normal(0, 1, n)) * 0.4 + deriva

    df_simulado = pd.DataFrame(
        {
            "Open": precio_base,
            "High": precio_base + rng.random(n) * 2,
            "Low": precio_base - rng.random(n) * 2,
            "Close": precio_base + rng.normal(0, 0.5, n),
            "Volume": rng.integers(100, 1000, n),
        },
        index=indice,
    )

    print(">>> SIN filtro de régimen (equivalente a la v2, solo largos):")
    resultado_sin_filtro = generar_senales(
        df_simulado, permitir_cortos=False, usar_adx=False, usar_filtro_macro=False,
    )
    n_entradas_sin_filtro = (
        (resultado_sin_filtro["senal"].diff() != 0) & (resultado_sin_filtro["senal"] == 1)
    ).sum()
    print(f"Entradas largas detectadas: {n_entradas_sin_filtro}")

    print("\n>>> CON filtro de régimen (EMA200 + ADX>=22), disparador CRUCE_EMA (v3):")
    resultado_cruce = generar_senales(
        df_simulado, permitir_cortos=False, disparador_entrada="cruce_ema",
    )
    n_entradas_cruce = (
        (resultado_cruce["senal"].diff() != 0) & (resultado_cruce["senal"] == 1)
    ).sum()
    print(f"Entradas largas detectadas: {n_entradas_cruce}")

    print("\n>>> CON filtro de régimen (EMA200 + ADX>=22), disparador PULLBACK (v4, nuevo):")
    resultado_pullback = generar_senales(
        df_simulado, permitir_cortos=False, disparador_entrada="pullback",
    )
    n_entradas_pullback = (
        (resultado_pullback["senal"].diff() != 0) & (resultado_pullback["senal"] == 1)
    ).sum()
    print(f"Entradas largas detectadas: {n_entradas_pullback}")
    print(
        "(Se espera más entradas que con 'cruce_ema': el reclamo de la EMA "
        "rápida es un evento más frecuente que el cruce de dos EMAs — el "
        "filtro de régimen es el que debe mantener la calidad, no la "
        "escasez del disparador.)"
    )

    columnas_a_mostrar = ["Close", "ema_macro", "adx", "senal"]
    print("\nÚltimas filas con el disparador 'pullback' activo:")
    print(resultado_pullback[columnas_a_mostrar].tail(10).to_string())
