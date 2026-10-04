"""
=============================================================================
 BOT-PREDICT · main.py — Orquestador del pipeline completo
=============================================================================

Encadena los 4 módulos ya construidos, cada uno responsable de una única
capa del sistema (principio de responsabilidad única):

    ProveedorDatos (Módulo 1)
        -> generar_senales() (Módulo 2)
            -> MotorBacktest (Módulo 4, que invoca internamente
               calcular_gestion_riesgo() del Módulo 3, OPERACIÓN A OPERACIÓN)

Nota de arquitectura importante
--------------------------------
`calcular_gestion_riesgo()` (Módulo 3) NO se ejecuta aquí como un paso
global previo al backtest. Se invoca DENTRO del bucle de `MotorBacktest`,
una vez por cada señal de entrada, porque el tamaño de cada posición
depende de dos valores que solo se conocen en el instante de esa entrada
concreta: el ATR vigente en ese momento y el capital disponible en ese
momento (que cambia operación a operación si `interes_compuesto=True`).
Calcularlo de antemano para todo el histórico sería, de hecho, una forma
sutil de lookahead bias. Este `main.py` solo ORQUESTA: construye la
configuración, invoca cada módulo en su capa, y presenta el resultado.

Este script no contiene lógica de negocio propia — si necesitas cambiar
cómo se calcula un indicador, el sizing o las métricas, ese cambio vive en
su módulo correspondiente, no aquí.
=============================================================================
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from modulo_1_datos import (
    ParametrosDescarga,
    ProveedorDatos,
    TipoActivo,
    _parsear_periodo_a_dias,
)
from modulo_2_estrategia import generar_senales
from modulo_4_backtesting import (
    MotorBacktest,
    ParametrosBacktest,
    ResultadoBacktest,
    Trade,
    calcular_metricas,
    graficar_equity_drawdown,
    imprimir_reporte,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("bot_predict.main")


@dataclass
class Configuracion:
    """Configuración centralizada del pipeline. Edita aquí, no dentro de
    los módulos, para lanzar una ejecución distinta (otro activo, otro
    perfil de riesgo, etc.).
    """

    # --- Activo y temporalidad ---
    ticker: str = "BTC/USDT"
    tipo_activo: TipoActivo = TipoActivo.CRIPTO
    # "binance" devuelve HTTP 451 (bloqueo geográfico) desde los servidores
    # de Google Colab, con base en EE.UU. — Binance no permite servir su API
    # pública a IPs estadounidenses. "kraken" sí es accesible desde Colab y
    # también lista BTC/USDT. Si tu propio ordenador/región no tuviera este
    # bloqueo, podrías volver a "binance" sin cambiar nada más del código.
    exchange_id: str = "kraken"        # Solo aplica si tipo_activo es CRIPTO.
    intervalo: str = "4h"
    # Ampliado de "1y" a "3y" tras el segundo backtest real (v3, filtro de
    # régimen): con 12 meses y un solo activo, la exigencia simultánea de
    # EMA200 + ADX>=22 dejó pasar UNA sola operación en todo el año —
    # muestra estadísticamente inútil. 3 años (no 5) es un punto intermedio
    # deliberado: más muestra sin asumir que los parámetros de la estrategia
    # siguen siendo válidos en regímenes de mercado demasiado antiguos
    # (p. ej. el ciclo de 2017-2018 se comporta muy distinto al actual).
    periodo_historico: str = "3y"      # "Ny"/"Nmo"/"Nd". Usado por yfinance
                                        # (acciones) y por la paginación de
                                        # ccxt (cripto) del Módulo 1.
    # Cesta de activos para el backtest MULTIACTIVO (ver
    # `ejecutar_pipeline_multiactivo` más abajo). `ticker` (arriba) se
    # conserva para ejecuciones de un solo activo con `ejecutar_pipeline`;
    # esta lista es la que se usa por defecto en `if __name__ == "__main__"`.
    # Ampliada de 5 a 8 criptoactivos (segunda vuelta de "ampliar la
    # muestra", tras el resultado nº3 con n=11 operaciones combinadas).
    # XRP/USDT se retira: `diagnosticar_activo()` confirmó que Kraken solo
    # tiene ~4 meses de histórico real para ese par (no los 3 años
    # solicitados), así que no aportaba una muestra comparable al resto —
    # no se descarta por rendimiento, se descarta por profundidad de datos
    # insuficiente. Se añaden ADA, DOGE, DOT y LINK: todos llevan varios
    # años listados en Kraken con quote USDT, así que se espera (sin poder
    # verificarlo sin red desde este entorno) que sí cubran los 3 años
    # completos — si alguno no los cubre, `ejecutar_pipeline_multiactivo`
    # ahora avisa automáticamente en el log (ver más abajo), sin necesidad
    # de correr `diagnosticar_activo()` a mano para descubrirlo.
    # Si algún ticker no cotiza en el `exchange_id` configurado,
    # `ejecutar_pipeline_multiactivo` lo salta con un aviso en el log en
    # vez de abortar todo el backtest.
    activos: list[str] = field(
        default_factory=lambda: [
            "BTC/USDT", "ETH/USDT", "SOL/USDT", "LTC/USDT",
            "ADA/USDT", "DOGE/USDT", "DOT/USDT", "LINK/USDT",
        ]
    )

    # --- Capital y riesgo ---
    capital_inicial: float = 10_000.0
    riesgo_por_operacion: float = 0.01     # 1%.
    ratio_riesgo_beneficio: float = 2.0    # R:R 1:2.
    interes_compuesto: bool = True

    # --- Estrategia y filtros ---
    ema_rapida: int = 20
    ema_lenta: int = 50
    periodo_atr: int = 14
    periodo_rsi: int = 14
    # False por defecto: prueba de estrés post-auditoría que aísla el
    # lado comprador, tras confirmar que los cortos concentraron la
    # mayoría de las pérdidas reales (67% de las operaciones, ver roadmap).
    permitir_cortos: bool = False
    atr_mult_stop_largo: float = 2.0
    atr_mult_stop_corto: float = 1.5

    # --- Filtro de régimen de mercado (nuevo, post-auditoría) ---
    usar_filtro_macro: bool = True
    periodo_ema_macro: int = 200
    usar_adx: bool = True
    periodo_adx: int = 14
    # Relajado de 22.0 a 18.0 (segunda de las "tres combinadas" pedidas tras
    # el resultado de n=1 operación): sigue exigiendo una tendencia con
    # cierta fuerza direccional, pero dentro del rango 18-20 sugerido, para
    # dejar pasar más entradas sin volver a aceptar el régimen lateral que
    # motivó el filtro en primer lugar.
    umbral_adx: float = 18.0
    # v4 (tras el veredicto de 4 backtests reales convergiendo en ~sin
    # edge con el cruce EMA-EMA como disparador): "pullback" entra cuando
    # el precio reclama la EMA rápida dentro de una tendencia ya intacta,
    # en vez de esperar al cruce de dos EMAs (señal más lenta). "cruce_ema"
    # conserva el comportamiento de la v3, para A/B directo sobre el mismo
    # dato real — ver docstring de `generar_senales` en modulo_2_estrategia.py.
    disparador_entrada: Literal["pullback", "cruce_ema"] = "pullback"

    # --- Fricción de mercado ---
    comision_pct: float = 0.0006   # 0.06% por entrada y por salida.
    slippage_pct: float = 0.0002   # 0.02%.

    # --- Otros ---
    periodos_por_anio: int = 2190          # 4h, mercado 24/7 (cripto).
    unidades_fraccionables: bool = True
    permitir_apalancamiento: bool = False
    ruta_grafico: str = "equity_drawdown.png"


CONFIG = Configuracion()  # <- Único punto de edición para cambiar la ejecución.


def ejecutar_pipeline(config: Configuracion) -> ResultadoBacktest:
    """Ejecuta las 3 etapas del pipeline con la configuración dada.

    Devuelve el `ResultadoBacktest` completo (trades, curva de capital,
    métricas) para poder seguir explorándolo interactivamente, p. ej. en
    una celda de Colab tras la ejecución (`resultado.trades`,
    `resultado.curva_capital`, `resultado.metricas`).
    """

    # --- Etapa 1: Datos (Módulo 1) ---
    logger.info("Etapa 1/3: descargando datos de %s (%s, %s)...",
                config.ticker, config.tipo_activo.value, config.intervalo)
    proveedor = ProveedorDatos(exchange_id=config.exchange_id)
    datos = proveedor.obtener_datos(
        ParametrosDescarga(
            ticker=config.ticker,
            tipo=config.tipo_activo,
            intervalo=config.intervalo,
            periodo=config.periodo_historico,
            exchange_id=config.exchange_id,
        )
    )

    # --- Etapa 2: Señales de estrategia + filtro de régimen (Módulo 2) ---
    logger.info(
        "Etapa 2/3: generando señales (EMA %d/%d, RSI %d, ATR %d) | "
        "filtro régimen: EMA_macro=%s(%d) ADX=%s(>=%.1f)...",
        config.ema_rapida, config.ema_lenta, config.periodo_rsi, config.periodo_atr,
        config.usar_filtro_macro, config.periodo_ema_macro,
        config.usar_adx, config.umbral_adx,
    )
    df_senales = generar_senales(
        datos,
        ema_rapida=config.ema_rapida,
        ema_lenta=config.ema_lenta,
        periodo_atr=config.periodo_atr,
        periodo_rsi=config.periodo_rsi,
        permitir_cortos=config.permitir_cortos,
        atr_mult_stop_largo=config.atr_mult_stop_largo,
        atr_mult_stop_corto=config.atr_mult_stop_corto,
        usar_filtro_macro=config.usar_filtro_macro,
        periodo_ema_macro=config.periodo_ema_macro,
        usar_adx=config.usar_adx,
        periodo_adx=config.periodo_adx,
        umbral_adx=config.umbral_adx,
        disparador_entrada=config.disparador_entrada,
    )

    # --- Etapa 3: Backtest (Módulo 4, que usa el Módulo 3 internamente) ---
    logger.info("Etapa 3/3: ejecutando backtest (capital=$%.2f, riesgo=%.1f%%, "
                "interés compuesto=%s)...",
                config.capital_inicial, config.riesgo_por_operacion * 100,
                config.interes_compuesto)
    parametros_backtest = ParametrosBacktest(
        capital_inicial=config.capital_inicial,
        riesgo_por_operacion=config.riesgo_por_operacion,
        interes_compuesto=config.interes_compuesto,
        comision_pct=config.comision_pct,
        slippage_pct=config.slippage_pct,
        atr_mult_stop_largo=config.atr_mult_stop_largo,
        atr_mult_stop_corto=config.atr_mult_stop_corto,
        ratio_riesgo_beneficio=config.ratio_riesgo_beneficio,
        permitir_apalancamiento=config.permitir_apalancamiento,
        unidades_fraccionables=config.unidades_fraccionables,
        periodos_por_anio=config.periodos_por_anio,
    )
    motor = MotorBacktest(parametros_backtest)
    resultado = motor.ejecutar(df_senales)

    # --- Presentación de resultados ---
    imprimir_reporte(resultado)
    ruta_grafico = graficar_equity_drawdown(resultado, config.ruta_grafico)
    logger.info("Gráfico de equity/drawdown guardado en: %s", ruta_grafico)
    return resultado


# =============================================================================
# Backtest MULTIACTIVO — "las tres combinadas" (histórico ampliado + ADX
# relajado + varios activos) para ganar potencia estadística.
# =============================================================================
#
# SIMPLIFICACIÓN DE DISEÑO QUE DEBES CONOCER (no se oculta):
# Cada activo de `config.activos` se backtestea de forma COMPLETAMENTE
# INDEPENDIENTE, con una porción fija e igual del capital total
# (`capital_inicial / nº de activos`), sin apalancamiento cruzado, sin
# rebalanceo entre activos y sin un presupuesto de riesgo compartido. Esto
# equivale a simular N estrategias en paralelo, cada una con su propia
# hucha de capital — NO a un gestor de cartera real que reasignaría capital
# dinámicamente entre activos. Es una simplificación deliberada y razonable
# para el objetivo actual (ampliar la muestra de operaciones), pero tiene
# una consecuencia estadística importante: los criptoactivos suelen estar
# altamente correlacionados entre sí (cuando BTC cae con fuerza, la mayoría
# de las altcoins caen también, a menudo más). Eso significa que, aunque
# sumar activos SÍ aumenta el número de operaciones (bueno para Win
# Rate/Profit Factor), NO aporta la misma diversificación de riesgo que
# tendrían activos poco correlacionados — el Max Drawdown combinado puede
# seguir siendo alto si varios activos entran en pérdidas a la vez.


@dataclass
class ResultadoMultiActivo:
    """Salida completa del backtest multiactivo: el detalle por activo (para
    poder auditar cada uno por separado) y el resultado combinado (pool de
    operaciones de todos los activos + curva de capital agregada), que es
    el que aporta la muestra estadística ampliada.
    """

    resultados_por_activo: dict[str, ResultadoBacktest]
    resultado_combinado: ResultadoBacktest


def _combinar_curvas_equity(
    curvas: dict[str, pd.Series], capital_por_activo: float
) -> pd.Series:
    """Suma las curvas de equity (en $) de varios activos independientes en
    una única curva de capital de cartera.

    Cada activo empieza con `capital_por_activo` en su propia curva. Para
    fechas anteriores al inicio del histórico de un activo concreto (p. ej.
    un token que se listó más tarde que los demás), se asume que esa
    porción de capital sigue intacta y sin invertir — de ahí el
    `fillna(capital_por_activo)` tras el `ffill()`, en vez de dejar NaN.
    """
    indice_unido = None
    for serie in curvas.values():
        indice_unido = serie.index if indice_unido is None else indice_unido.union(serie.index)
    indice_unido = indice_unido.sort_values()

    curva_combinada = pd.Series(0.0, index=indice_unido)
    for serie in curvas.values():
        serie_extendida = serie.reindex(indice_unido).ffill().fillna(capital_por_activo)
        curva_combinada = curva_combinada.add(serie_extendida, fill_value=0.0)
    curva_combinada.name = "equity_combinada"
    return curva_combinada


def _cobertura_historica(datos: pd.DataFrame, config: Configuracion) -> tuple[int, int, float]:
    """Compara el histórico REALMENTE descargado para un activo contra el
    solicitado en `config.periodo_historico`.

    Factorizado como función compartida (usada por `ejecutar_pipeline_multiactivo`
    y por `diagnosticar_activo`) tras descubrir, con datos reales, que un
    exchange puede devolver datos sin error y sin velas planas, pero
    empezando mucho más tarde de lo pedido (p. ej. XRP/USDT en Kraken: solo
    ~120 días reales pese a pedir "3y") — un fallo silencioso que ni un
    `try/except` ni un chequeo de calidad de precio detectan por sí solos.

    Devuelve (días solicitados, días cubiertos, % de cobertura) para que
    cada llamador decida cómo presentarlo (log, print, etc.).
    """
    dias_solicitados = _parsear_periodo_a_dias(config.periodo_historico)
    dias_cubiertos = (datos.index.max() - datos.index.min()).days
    pct_cobertura = (dias_cubiertos / dias_solicitados * 100) if dias_solicitados else 0.0
    return dias_solicitados, dias_cubiertos, pct_cobertura


def ejecutar_pipeline_multiactivo(config: Configuracion) -> ResultadoMultiActivo:
    """Ejecuta el pipeline completo (Módulos 1-2-3-4) de forma independiente
    para cada ticker de `config.activos`, y agrega los resultados en un
    único pool estadístico combinado.

    Un fallo al descargar o procesar UN activo concreto (ticker no listado
    en el exchange, histórico insuficiente tras el warm-up de indicadores,
    etc.) se registra como aviso y ese activo se omite — no aborta el
    backtest completo de los demás activos.

    DISEÑO EN DOS FASES (importante para que el capital cuadre): el reparto
    de capital (`capital_inicial / nº de activos`) se calcula sobre los
    activos que DE VERDAD pudieron descargarse y señalizarse, no sobre la
    longitud de `config.activos`. Si se repartiera sobre la lista
    configurada y luego un ticker fallara, la porción de capital asignada a
    ese ticker fallido desaparecería silenciosamente de la curva de equity
    combinada — haciendo que el "capital inicial" declarado ($10,000, p.
    ej.) no coincidiera con lo realmente invertido (p. ej. $8,000 si 1 de 5
    activos falla), y ensuciando la rentabilidad % reportada con un efecto
    que no tiene nada que ver con la estrategia, solo con un fallo de datos.
    Por eso primero se intenta descargar + señalizar TODOS los activos
    (fase 1, sin necesidad todavía de saber el capital), y solo cuando se
    sabe cuántos sobrevivieron se decide el reparto de capital y se
    ejecuta el backtest de cada uno (fase 2).
    """
    if len(config.activos) == 0:
        raise ValueError("`config.activos` está vacío: no hay ningún activo que backtestear.")

    # --- Fase 1: descarga + señales por activo (no depende del capital) ---
    senales_por_activo: dict[str, pd.DataFrame] = {}
    for ticker in config.activos:
        logger.info("=== Descargando y señalizando %s ===", ticker)
        try:
            proveedor = ProveedorDatos(exchange_id=config.exchange_id)
            datos = proveedor.obtener_datos(
                ParametrosDescarga(
                    ticker=ticker,
                    tipo=config.tipo_activo,
                    intervalo=config.intervalo,
                    periodo=config.periodo_historico,
                    exchange_id=config.exchange_id,
                )
            )
            dias_solicitados, dias_cubiertos, pct_cobertura = _cobertura_historica(datos, config)
            if pct_cobertura < 80.0:
                logger.warning(
                    "%s: histórico real cubre solo ~%d de ~%d días solicitados "
                    "(%.1f%%) — probablemente el par no tiene %s de antigüedad "
                    "en '%s'. Se incluye igualmente en el backtest, pero con "
                    "menos muestra que el resto de la cesta (ver diagnosticar_activo() "
                    "para el detalle filtro a filtro).",
                    ticker, dias_cubiertos, dias_solicitados, pct_cobertura,
                    config.periodo_historico, config.exchange_id,
                )
            senales_por_activo[ticker] = generar_senales(
                datos,
                ema_rapida=config.ema_rapida,
                ema_lenta=config.ema_lenta,
                periodo_atr=config.periodo_atr,
                periodo_rsi=config.periodo_rsi,
                permitir_cortos=config.permitir_cortos,
                atr_mult_stop_largo=config.atr_mult_stop_largo,
                atr_mult_stop_corto=config.atr_mult_stop_corto,
                usar_filtro_macro=config.usar_filtro_macro,
                periodo_ema_macro=config.periodo_ema_macro,
                usar_adx=config.usar_adx,
                periodo_adx=config.periodo_adx,
                umbral_adx=config.umbral_adx,
                disparador_entrada=config.disparador_entrada,
            )
        except Exception:
            logger.warning(
                "Activo %s omitido del backtest combinado (fallo en descarga o "
                "procesamiento; revisa si '%s' cotiza en el exchange '%s').",
                ticker, ticker, config.exchange_id, exc_info=True,
            )
            continue

    if not senales_por_activo:
        raise RuntimeError(
            "Ningún activo de la cesta pudo backtestearse con éxito. Revisa "
            "conectividad, `exchange_id` y que los tickers de `config.activos` "
            "coticen ahí."
        )

    # --- Fase 2: ahora sí, reparto de capital SOLO entre los supervivientes ---
    capital_por_activo = config.capital_inicial / len(senales_por_activo)

    resultados_por_activo: dict[str, ResultadoBacktest] = {}
    for ticker, df_senales in senales_por_activo.items():
        logger.info("=== Backtesteando %s (capital asignado: $%.2f) ===",
                    ticker, capital_por_activo)
        parametros_backtest = ParametrosBacktest(
            capital_inicial=capital_por_activo,
            riesgo_por_operacion=config.riesgo_por_operacion,
            interes_compuesto=config.interes_compuesto,
            comision_pct=config.comision_pct,
            slippage_pct=config.slippage_pct,
            atr_mult_stop_largo=config.atr_mult_stop_largo,
            atr_mult_stop_corto=config.atr_mult_stop_corto,
            ratio_riesgo_beneficio=config.ratio_riesgo_beneficio,
            permitir_apalancamiento=config.permitir_apalancamiento,
            unidades_fraccionables=config.unidades_fraccionables,
            periodos_por_anio=config.periodos_por_anio,
        )
        motor = MotorBacktest(parametros_backtest, activo=ticker)
        resultados_por_activo[ticker] = motor.ejecutar(df_senales)

    # --- Agregación: pool de operaciones + curva de equity combinada ---
    todos_los_trades: list[Trade] = []
    curvas_por_activo: dict[str, pd.Series] = {}
    for ticker, resultado in resultados_por_activo.items():
        todos_los_trades.extend(resultado.trades)
        curvas_por_activo[ticker] = resultado.curva_capital
    todos_los_trades.sort(key=lambda t: t.fecha_entrada)

    curva_combinada = _combinar_curvas_equity(curvas_por_activo, capital_por_activo)

    parametros_combinados = ParametrosBacktest(
        capital_inicial=config.capital_inicial,
        periodos_por_anio=config.periodos_por_anio,
    )
    metricas_combinadas = calcular_metricas(todos_los_trades, curva_combinada, parametros_combinados)

    resultado_combinado = ResultadoBacktest(
        trades=todos_los_trades,
        curva_capital=curva_combinada,
        metricas=metricas_combinadas,
        capital_inicial=config.capital_inicial,
        capital_final=float(curva_combinada.iloc[-1]) if len(curva_combinada) else config.capital_inicial,
    )

    return ResultadoMultiActivo(
        resultados_por_activo=resultados_por_activo,
        resultado_combinado=resultado_combinado,
    )


def imprimir_reporte_multiactivo(resultado: ResultadoMultiActivo) -> None:
    """Imprime primero el desglose por activo (para poder auditar cada uno
    por separado) y después el informe combinado, que es el que tiene la
    muestra estadística ampliada.
    """
    for ticker, resultado_activo in resultado.resultados_por_activo.items():
        print(f"\n>>> Activo: {ticker}")
        imprimir_reporte(resultado_activo)

    print("\n>>> COMBINADO (pool de todos los activos backtesteados)")
    imprimir_reporte(resultado.resultado_combinado)


# =============================================================================
# Diagnóstico de un único activo: por qué no genera operaciones (o genera
# muy pocas). No ejecuta ningún backtest — solo inspecciona los datos crudos
# y, filtro por filtro, dónde se pierden las entradas.
# =============================================================================

def diagnosticar_activo(config: Configuracion, ticker: str) -> None:
    """Diagnóstico de un único activo, pensado para el caso "0 operaciones
    en todo el periodo" (p. ej. XRP/USDT en el backtest multiactivo).

    Antes de asumir que el filtro de régimen simplemente "es así de
    selectivo", este diagnóstico separa dos posibles causas MUY distintas:

    1. Un problema de CALIDAD DE DATOS: si el par tiene poca liquidez en
       el exchange configurado, ccxt puede devolver velas casi planas
       (Open≈High≈Low≈Close, apenas variación de un periodo a otro). Con
       datos así, ningún indicador (EMA, ADX) va a generar una señal
       útil — no es que el mercado no tenga tendencia, es que el dato no
       la refleja.
    2. Un problema de LOS FILTROS: si el dato es sano (variación de precio
       normal) pero la exigencia SIMULTÁNEA de tendencia macro + ADX alto
       nunca coincide con un cruce de EMA en todo el periodo, el filtro
       realmente está siendo así de restrictivo para ese activo concreto
       — un resultado legítimo, aunque incómodo.

    Se imprime, en este orden: estadísticas básicas del precio crudo (para
    la causa 1), y después un embudo filtro-a-filtro que cuenta cuántos
    cruces de EMA sobreviven a cada filtro de régimen por separado (para
    la causa 2). No modifica ni reutiliza estado de ningún backtest previo
    — descarga y calcula todo de cero para `ticker`.
    """
    proveedor = ProveedorDatos(exchange_id=config.exchange_id)
    datos = proveedor.obtener_datos(
        ParametrosDescarga(
            ticker=ticker,
            tipo=config.tipo_activo,
            intervalo=config.intervalo,
            periodo=config.periodo_historico,
            exchange_id=config.exchange_id,
        )
    )

    print(f"\n{'=' * 60}\nDIAGNÓSTICO: {ticker}\n{'=' * 60}")

    # --- 1) Calidad del dato crudo ---
    print(f"Velas descargadas: {len(datos)}")
    print(f"Rango de fechas:   {datos.index.min()} -> {datos.index.max()}")
    print(
        f"Close min/max/mean/std: {datos['Close'].min():.6f} / "
        f"{datos['Close'].max():.6f} / {datos['Close'].mean():.6f} / "
        f"{datos['Close'].std():.6f}"
    )
    n_valores_unicos = int(datos["Close"].nunique())
    pct_unicos = n_valores_unicos / len(datos) * 100
    print(
        f"Valores de Close distintos entre velas consecutivas: "
        f"{n_valores_unicos} de {len(datos)} ({pct_unicos:.1f}%)"
    )
    if pct_unicos < 50.0:
        print(
            "AVISO: menos de la mitad de las velas cambian de precio de "
            "cierre respecto a la anterior. Esto es típico de pares con "
            "poca liquidez en el exchange configurado, y puede bastar por "
            "sí solo para explicar 0 operaciones (el problema sería el "
            "dato, no la estrategia)."
        )

    # --- 1b) Profundidad histórica real vs. la solicitada en `config` ---
    # Un exchange puede devolver datos SIN error y SIN velas planas, pero
    # empezando mucho más tarde de lo pedido (p. ej. porque el par se
    # listó hace poco) — un caso muy distinto al de "velas planas" de
    # arriba, y fácil de pasar por alto si solo se mira si hubo error.
    dias_solicitados, dias_cubiertos, pct_cobertura = _cobertura_historica(datos, config)
    print(
        f"Histórico solicitado: ~{dias_solicitados} días ({config.periodo_historico}) | "
        f"histórico realmente cubierto: ~{dias_cubiertos} días ({pct_cobertura:.1f}%)"
    )
    if pct_cobertura < 80.0:
        print(
            f"AVISO: el histórico real cubre solo el {pct_cobertura:.1f}% de lo "
            f"solicitado. Lo más probable es que este ticker NO tenga "
            f"{config.periodo_historico} de antigüedad en el exchange "
            f"configurado (par listado más tarde, o con menos profundidad "
            f"histórica disponible vía la API pública) — el filtro EMA200/ADX "
            f"puede estar operando correctamente, pero sobre una ventana real "
            f"mucho más corta de lo que `config.periodo_historico` sugiere."
        )

    # --- 2) Embudo de filtros (recalculado sobre las columnas que
    #        `generar_senales` sí expone: ema_rapida/lenta, ema_macro, adx) ---
    df = generar_senales(
        datos,
        ema_rapida=config.ema_rapida,
        ema_lenta=config.ema_lenta,
        periodo_atr=config.periodo_atr,
        periodo_rsi=config.periodo_rsi,
        permitir_cortos=config.permitir_cortos,
        atr_mult_stop_largo=config.atr_mult_stop_largo,
        atr_mult_stop_corto=config.atr_mult_stop_corto,
        usar_filtro_macro=config.usar_filtro_macro,
        periodo_ema_macro=config.periodo_ema_macro,
        usar_adx=config.usar_adx,
        periodo_adx=config.periodo_adx,
        umbral_adx=config.umbral_adx,
        disparador_entrada=config.disparador_entrada,
    )

    # El evento base del embudo depende del disparador configurado: el
    # cruce EMA-EMA (v3) o el "reclamo" de la EMA rápida dentro de la
    # estructura de tendencia (v4/pullback, por defecto) — ver docstring
    # de `generar_senales` en modulo_2_estrategia.py.
    if config.disparador_entrada == "cruce_ema":
        evento_base = (df["ema_rapida"] > df["ema_lenta"]) & (
            df["ema_rapida"].shift(1) <= df["ema_lenta"].shift(1)
        )
        etiqueta_evento = f"Cruces alcistas de EMA {config.ema_rapida}/{config.ema_lenta}"
    else:
        estructura_alcista = df["ema_rapida"] > df["ema_lenta"]
        reclamo_alcista = (df["Close"] > df["ema_rapida"]) & (
            df["Close"].shift(1) <= df["ema_rapida"].shift(1)
        )
        evento_base = reclamo_alcista & estructura_alcista
        etiqueta_evento = (
            f"Reclamos de EMA{config.ema_rapida} dentro de estructura alcista "
            f"(EMA{config.ema_rapida} > EMA{config.ema_lenta})"
        )
    n_eventos = int(evento_base.sum())
    print(f"\n{etiqueta_evento} (sin ningún filtro de régimen): {n_eventos}")

    filtro_macro = pd.Series(True, index=df.index)
    if config.usar_filtro_macro:
        filtro_macro = df["Close"] > df["ema_macro"]
        print(
            f"  Velas con tendencia macro alcista (Close > EMA"
            f"{config.periodo_ema_macro}): {int(filtro_macro.sum())} de "
            f"{len(df)} ({filtro_macro.mean() * 100:.1f}%) | "
            f"eventos que la cumplen: {int((evento_base & filtro_macro).sum())}"
        )

    filtro_adx = pd.Series(True, index=df.index)
    if config.usar_adx:
        print(
            f"  ADX min/max/mean: {df['adx'].min():.2f} / "
            f"{df['adx'].max():.2f} / {df['adx'].mean():.2f}"
        )
        filtro_adx = df["adx"] >= config.umbral_adx
        print(
            f"  Velas con ADX >= {config.umbral_adx}: {int(filtro_adx.sum())} "
            f"de {len(df)} ({filtro_adx.mean() * 100:.1f}%) | "
            f"eventos que la cumplen: {int((evento_base & filtro_adx).sum())}"
        )

    n_ambos = int((evento_base & filtro_macro & filtro_adx).sum())
    print(f"\nEventos de entrada que superan AMBOS filtros a la vez: {n_ambos}")

    n_entradas_finales = int(
        ((df["senal"].diff() != 0) & (df["senal"] == 1)).sum()
    )
    print(
        f"Entradas largas finales (incluyendo también RSI/volatilidad): "
        f"{n_entradas_finales}"
    )
    print("=" * 60)


if __name__ == "__main__":
    try:
        resultado_multiactivo = ejecutar_pipeline_multiactivo(CONFIG)
        imprimir_reporte_multiactivo(resultado_multiactivo)
        ruta_grafico = graficar_equity_drawdown(
            resultado_multiactivo.resultado_combinado, CONFIG.ruta_grafico
        )
        logger.info("Gráfico de equity/drawdown combinado guardado en: %s", ruta_grafico)
    except Exception as exc:  # pragma: no cover
        logger.error(
            "El pipeline se detuvo con un error. Revisa la configuración "
            "(ticker, exchange, conectividad de red) antes de reintentar."
        )
        raise
