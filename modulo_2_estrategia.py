"""
=============================================================================
 BOT-PREDICT · MÓDULO 2 (v4): Estrategia — entrada por PULLBACK en tendencia
             (sustituye al disparador de cruce de EMA de la v3) + ATR/RSI
             + filtro de régimen (EMA200 + ADX)
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


# -----------------------------------------------------------------------
# Generador de señales: función única, parametrizada y vectorizada.
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
    disparador_entrada: Literal["pullback", "cruce_ema"] = "pullback",
) -> pd.DataFrame:
    """Genera indicadores y señales de trading, con filtro de régimen.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame con columnas ``Open, High, Low, Close, Volume`` (esquema
        estandarizado del Módulo 1) e índice temporal ordenado.
    ema_rapida, ema_lenta : int
        Periodos de las EMA que definen la estructura de tendencia. 20/50
        por defecto (ver docstring del módulo). Con
        `disparador_entrada="pullback"` actúan como un ESTADO (¿sigue la
        tendencia intacta?), no como el evento que dispara la entrada.
    periodo_atr, periodo_rsi : int
        Ventanas de cálculo del ATR y el RSI.
    rsi_sobrecompra, rsi_sobreventa : float
        Umbrales que BLOQUEAN una nueva entrada por sobrecompra/sobreventa.
    rsi_agotamiento_largo, rsi_agotamiento_corto : float
        Umbrales que FUERZAN el cierre de una posición abierta.
    atr_pct_minimo : float
        ATR mínimo (como fracción del precio) para permitir operar.
    permitir_cortos : bool
        Si True, genera también señales en corto (-1). **Por defecto
        False** en esta versión: la prueba de estrés post-auditoría aísla
        la rentabilidad del lado comprador, dado que los cortos
        concentraron la mayoría de las pérdidas en la v2.
    atr_mult_stop_largo, atr_mult_stop_corto : float
        Multiplicadores de ATR para la distancia de stop-loss base.
    usar_filtro_macro : bool
        Activa el filtro de tendencia macro (régimen nº 1). Si False, se
        ignora `periodo_ema_macro` por completo (útil para comparar
        con/sin filtro sin recurrir a valores de periodo artificiales).
    periodo_ema_macro : int
        Periodo de la EMA de tendencia de fondo (filtro de régimen nº 1).
        Una entrada larga solo es válida con Close > EMA_macro; una corta,
        solo con Close < EMA_macro. 200 por defecto.
    usar_adx : bool
        Activa el filtro de fuerza direccional (régimen nº 2). Si False,
        se ignora el ADX por completo (útil para comparar con/sin filtro).
    periodo_adx : int
        Ventana de cálculo del ADX (suavizado de Wilder doble).
    umbral_adx : float
        ADX mínimo para aceptar una entrada. Por debajo de este umbral se
        interpreta que el mercado no tiene una tendencia lo bastante
        definida como para operar con confianza.
    disparador_entrada : "pullback" | "cruce_ema"
        Mecanismo que dispara la entrada (ver docstring del módulo para el
        razonamiento completo):
        - "pullback" (v4, por defecto): entra cuando el precio "reclama"
          la EMA rápida (cierre vuelve a superarla tras haber estado
          debajo) MIENTRAS la estructura `ema_rapida`/`ema_lenta` sigue
          alineada con la tendencia. El cruce EMA-EMA pasa a ser señal de
          SALIDA por ruptura de estructura, no de entrada.
        - "cruce_ema" (v3, conservado para comparación A/B): comportamiento
          idéntico a la versión anterior — entra en el instante exacto en
          que `ema_rapida` cruza a `ema_lenta`.
        En ambos casos los filtros de régimen (macro + ADX) y de calidad
        (RSI + volatilidad) se aplican igual, solo a las entradas.

    Returns
    -------
    pd.DataFrame
        Copia de `df` con las columnas de indicadores añadidas (incluye
        `ema_macro` y, si `usar_adx=True`, `adx`) y una columna final
        `senal` (1 / -1 / 0).
    """
    df = df.copy()

    # 1) Indicadores base (idénticos a la v2).
    df["ema_rapida"] = calcular_ema(df["Close"], ema_rapida)
    df["ema_lenta"] = calcular_ema(df["Close"], ema_lenta)
    df["atr"] = calcular_atr(df, periodo_atr)
    df["atr_pct"] = df["atr"] / df["Close"]
    df["rsi"] = calcular_rsi(df["Close"], periodo_rsi)

    # 1b) Indicadores de RÉGIMEN (nuevos en esta versión).
    if usar_filtro_macro:
        df["ema_macro"] = calcular_ema(df["Close"], periodo_ema_macro)
        # Enmascarado EXPLÍCITO del periodo de calentamiento: aunque
        # `.ewm()` produce un valor desde la primera vela (no NaN "de
        # fábrica"), una EMA de 200 periodos calculada sobre menos de 200
        # velas no es estadísticamente lo que dice ser -> la anulamos a
        # propósito durante las primeras `periodo_ema_macro` velas, para
        # que el filtro de tendencia macro NUNCA autorice una entrada con
        # datos insuficientes (una comparación contra NaN se evalúa como
        # False, así que estas velas quedan automáticamente excluidas).
        df.loc[df.index[:periodo_ema_macro], "ema_macro"] = np.nan

    if usar_adx:
        df["adx"] = calcular_adx(df, periodo_adx)
        # El ADX encadena dos suavizados de Wilder (DM/TR, y DX->ADX): su
        # calentamiento fiable requiere más velas que un solo suavizado.
        # Enmascaramos el doble del periodo, mismo criterio explícito que
        # con la EMA macro.
        velas_calentamiento_adx = periodo_adx * 2
        df.loc[df.index[:velas_calentamiento_adx], "adx"] = np.nan
        filtro_adx = df["adx"] >= umbral_adx
    else:
        filtro_adx = pd.Series(True, index=df.index)

    # 2) Estructura de tendencia (estado sostenido) + eventos de cruce
    #    EMA-EMA. En "pullback" (v4), la estructura filtra la entrada y el
    #    cruce se usa como salida por ruptura; en "cruce_ema" (v3), el
    #    cruce se usa directamente como disparador de entrada.
    estructura_alcista = df["ema_rapida"] > df["ema_lenta"]
    estructura_bajista = df["ema_rapida"] < df["ema_lenta"]
    cruce_alcista = estructura_alcista & (
        df["ema_rapida"].shift(1) <= df["ema_lenta"].shift(1)
    )
    cruce_bajista = estructura_bajista & (
        df["ema_rapida"].shift(1) >= df["ema_lenta"].shift(1)
    )

    # 2b) Evento de "reclamo" de la EMA rápida (disparador de la v4): el
    #     cierre vuelve a superarla (o a perderla, para cortos) tras haber
    #     estado al otro lado en la vela anterior — la firma de un
    #     retroceso ("pullback") que se resuelve a favor de la tendencia.
    reclamo_alcista = (df["Close"] > df["ema_rapida"]) & (
        df["Close"].shift(1) <= df["ema_rapida"].shift(1)
    )
    reclamo_bajista = (df["Close"] < df["ema_rapida"]) & (
        df["Close"].shift(1) >= df["ema_rapida"].shift(1)
    )

    if disparador_entrada == "pullback":
        evento_entrada_largo = reclamo_alcista & estructura_alcista
        evento_entrada_corto = reclamo_bajista & estructura_bajista
    elif disparador_entrada == "cruce_ema":
        evento_entrada_largo = cruce_alcista
        evento_entrada_corto = cruce_bajista
    else:
        raise ValueError(
            f"disparador_entrada debe ser 'pullback' o 'cruce_ema', recibido: "
            f"'{disparador_entrada}'."
        )

    # 3) Filtros de calidad sobre las entradas (RSI + volatilidad, v2).
    filtro_volatilidad = df["atr_pct"] >= atr_pct_minimo
    filtro_rsi_largo = df["rsi"] < rsi_sobrecompra
    filtro_rsi_corto = df["rsi"] > rsi_sobreventa

    # 3b) Filtros de RÉGIMEN: tendencia macro + fuerza direccional.
    # Comparaciones con NaN (periodo de calentamiento) se evalúan como
    # False en pandas -> no autorizan entrada, sin necesidad de lógica
    # adicional.
    if usar_filtro_macro:
        filtro_tendencia_macro_largo = df["Close"] > df["ema_macro"]
        filtro_tendencia_macro_corto = df["Close"] < df["ema_macro"]
    else:
        filtro_tendencia_macro_largo = pd.Series(True, index=df.index)
        filtro_tendencia_macro_corto = pd.Series(True, index=df.index)

    entrada_larga = (
        evento_entrada_largo
        & filtro_rsi_largo
        & filtro_volatilidad
        & filtro_tendencia_macro_largo
        & filtro_adx
    )
    entrada_corta = (
        permitir_cortos
        & evento_entrada_corto
        & filtro_rsi_corto
        & filtro_volatilidad
        & filtro_tendencia_macro_corto
        & filtro_adx
    )

    # 4) Eventos de salida forzada. La ruptura de ESTRUCTURA (cruce EMA-EMA
    #    en contra de la posición) cierra siempre, sea cual sea el
    #    disparador de entrada usado — si la tendencia que sostenía la
    #    entrada ya no existe, la razón para seguir dentro tampoco.
    #    El agotamiento por RSI es idéntico a la v3: el filtro de régimen
    #    aplica solo a la decisión de ENTRAR, nunca a la de salir -> una
    #    vez dentro, la gestión de riesgo manda.
    salida_larga_rsi = (df["rsi"] > rsi_agotamiento_largo) & (
        df["rsi"].shift(1) <= rsi_agotamiento_largo
    )
    salida_corta_rsi = (df["rsi"] < rsi_agotamiento_corto) & (
        df["rsi"].shift(1) >= rsi_agotamiento_corto
    )

    # 5) Ensamblado vectorizado de la señal como estado sostenido (ffill
    #    de eventos), igual que en versiones anteriores.
    senal_bruta = pd.Series(np.nan, index=df.index)
    senal_bruta.loc[salida_larga_rsi] = 0
    senal_bruta.loc[salida_corta_rsi] = 0
    senal_bruta.loc[cruce_bajista & ~permitir_cortos] = 0  # sin cortos: solo cerrar largo
    senal_bruta.loc[entrada_larga] = 1
    senal_bruta.loc[entrada_corta] = -1

    df["senal"] = senal_bruta.ffill().fillna(0).astype(int)

    # 6) Distancia de stop-loss base (asimétrica), previsualización del
    #    Módulo 3.
    df["distancia_stop_atr"] = calcular_distancia_stop_atr(
        df["atr"], df["senal"], atr_mult_stop_largo, atr_mult_stop_corto
    )

    logger.info(
        "Señales generadas (con filtro de régimen): %d velas largas, "
        "%d cortas, %d planas.",
        (df["senal"] == 1).sum(),
        (df["senal"] == -1).sum(),
        (df["senal"] == 0).sum(),
    )
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
