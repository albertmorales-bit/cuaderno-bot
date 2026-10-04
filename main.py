"""
=============================================================================
 BOT-PREDICT · main.py — Orquestador del pipeline completo (v5)
=============================================================================

Encadena los 4 módulos, cada uno responsable de una única capa:

    ProveedorDatos (Módulo 1)
        -> generar_senales() (Módulo 2)
            -> MotorBacktest (Módulo 4, que invoca calcular_gestion_riesgo()
               del Módulo 3 OPERACIÓN A OPERACIÓN)

`calcular_gestion_riesgo()` se invoca DENTRO del bucle del motor, una vez
por entrada, porque el tamaño depende del ATR y del capital en ese
instante. Calcularlo de antemano sería una forma sutil de lookahead.

Este script no contiene lógica de negocio: solo construye los argumentos
de cada módulo desde `Configuracion` (una sola vez, en `kwargs_senales` y
`parametros_backtest`, para que backtest y motor en vivo no puedan
divergir) y presenta los resultados.
=============================================================================
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from modulo_1_datos import (
    ParametrosDescarga,
    ProveedorDatos,
    TipoActivo,
    _parsear_periodo_a_dias,
    duracion_intervalo,
)
from modulo_1b_historico import cargar_historico
from modulo_2_estrategia import Disparador, generar_senales
from modulo_4_backtesting import (
    COMISION_TAKER_KRAKEN,
    SLIPPAGE_PESIMISTA,
    MotorBacktest,
    ParametrosBacktest,
    ResultadoBacktest,
    Trade,
    calcular_metricas,
    graficar_equity_drawdown,
    imprimir_reporte,
    imprimir_reporte_particionado,
    particionar_resultado,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("bot_predict.main")


@dataclass
class Configuracion:
    """Configuración centralizada. Edita aquí, no dentro de los módulos.

    Los valores marcados como PROVISIONAL dependen de decisiones abiertas
    (ver DECISIONES.md) y se fijarán en la Fase 1.
    """

    # --- Origen de los datos (Fase 1) ---
    # "disco": serie limpia versionada de datos/<version_datos>/, con
    # verificación de checksum (lo normal para backtests, reproducible).
    # "api": descarga en el momento (solo para inspección; la API de Kraken
    # no da histórico largo).
    fuente_datos: str = "disco"
    version_datos: str = "v1"

    # --- Activo y temporalidad ---
    ticker: str = "BTC/EUR"
    tipo_activo: TipoActivo = TipoActivo.CRIPTO
    # Kraken: accesible desde Colab y con pares en EUR. OJO (auditoría P1):
    # su API OHLC pública solo devuelve las 720 velas más recientes, así que
    # NO sirve para histórico largo; la Fase 1 construye ese histórico con
    # otras fuentes y lo guarda en disco.
    exchange_id: str = "kraken"
    intervalo: str = "1d"              # PROVISIONAL (D-001): diario.
    periodo_historico: str = "3y"      # Ignorado si se da `fecha_inicio`.
    fecha_inicio: Optional[str] = None  # "AAAA-MM-DD" UTC; reproducible.
    fecha_fin: Optional[str] = None     # Exclusiva.
    # Cesta del backtest multiactivo. PROVISIONAL (D-002): solo BTC y ETH,
    # para evitar el sesgo de supervivencia de las altcoins.
    activos: list[str] = field(default_factory=lambda: ["BTC/EUR", "ETH/EUR"])
    # Mínimo de orden por par (Kraken vía ccxt, consultado el 2026-10-04).
    tamanos_minimos: dict[str, float] = field(
        default_factory=lambda: {"BTC/EUR": 0.00005, "ETH/EUR": 0.001}
    )
    # Auditoría P1: si el histórico descargado cubre menos de este % de lo
    # pedido, se ABORTA ese activo (la v4 solo avisaba y seguía con 120 días).
    cobertura_minima_pct: float = 95.0

    # --- Capital y riesgo ---
    capital_inicial: float = 10_000.0
    riesgo_por_operacion: float = 0.01     # 1 %.
    ratio_riesgo_beneficio: float = 2.0    # Solo si usar_take_profit=True.
    usar_take_profit: bool = False         # v5: Turtle, sin objetivo fijo.
    interes_compuesto: bool = True

    # --- Estrategia ---
    disparador_entrada: Disparador = "ruptura_donchian"   # v5.
    periodo_ruptura_entrada: int = 20      # Turtle clásico.
    periodo_ruptura_salida: int = 10
    ema_rapida: int = 20                   # Solo "pullback" / "cruce_ema".
    ema_lenta: int = 50
    periodo_atr: int = 14
    periodo_rsi: int = 14
    usar_filtro_rsi: bool = False          # v5: sin RSI (ver Módulo 2).
    permitir_cortos: bool = False          # Solo largos (contado, sin funding).
    atr_mult_stop_largo: float = 2.0       # Stop 2N, como el Turtle.
    atr_mult_stop_corto: float = 1.5
    factor_calentamiento_ema: float = 2.0

    # --- Filtros de régimen ---
    usar_filtro_macro: bool = True
    periodo_ema_macro: int = 200
    usar_adx: bool = False                 # v5: sin ADX.
    periodo_adx: int = 14
    umbral_adx: float = 18.0

    # --- Fricción de mercado (auditoría P5, D-005) ---
    comision_pct: float = COMISION_TAKER_KRAKEN   # 0,80 % taker, Kraken Pro nivel 1.
    slippage_pct: float = SLIPPAGE_PESIMISTA      # 0,10 %.

    # --- Validación ---
    fraccion_oos: float = 0.3   # Partición 70/30 por tiempo, con embargo.

    # --- Otros ---
    divisa: str = "€"
    periodos_por_anio: Optional[int] = None   # None: se deriva de `intervalo`.
    unidades_fraccionables: bool = True
    permitir_apalancamiento: bool = False
    ruta_grafico: str = "equity_drawdown.png"

    def periodos_anuales(self) -> int:
        """Velas por año (mercado 24/7) para anualizar Sharpe y Sortino."""
        if self.periodos_por_anio is not None:
            return self.periodos_por_anio
        return int(round(pd.Timedelta(days=365) / duracion_intervalo(self.intervalo)))


CONFIG = Configuracion()  # <- Único punto de edición para cambiar la ejecución.


# =============================================================================
# Constructores de argumentos: la ÚNICA traducción Configuracion -> módulos.
# =============================================================================

def kwargs_senales(config: Configuracion) -> dict:
    """Argumentos de `generar_senales` a partir de la configuración."""
    return dict(
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
        periodo_ruptura_entrada=config.periodo_ruptura_entrada,
        periodo_ruptura_salida=config.periodo_ruptura_salida,
        usar_filtro_rsi=config.usar_filtro_rsi,
        factor_calentamiento_ema=config.factor_calentamiento_ema,
    )


def parametros_backtest(
    config: Configuracion, ticker: str, capital: Optional[float] = None
) -> ParametrosBacktest:
    """Parámetros del motor para un activo (capital propio si es multiactivo)."""
    return ParametrosBacktest(
        capital_inicial=config.capital_inicial if capital is None else capital,
        riesgo_por_operacion=config.riesgo_por_operacion,
        interes_compuesto=config.interes_compuesto,
        comision_pct=config.comision_pct,
        slippage_pct=config.slippage_pct,
        atr_mult_stop_largo=config.atr_mult_stop_largo,
        atr_mult_stop_corto=config.atr_mult_stop_corto,
        ratio_riesgo_beneficio=config.ratio_riesgo_beneficio,
        usar_take_profit=config.usar_take_profit,
        permitir_apalancamiento=config.permitir_apalancamiento,
        unidades_fraccionables=config.unidades_fraccionables,
        tamano_minimo=config.tamanos_minimos.get(ticker, 0.0),
        periodos_por_anio=config.periodos_anuales(),
    )


def obtener_velas(config: Configuracion, ticker: str) -> pd.DataFrame:
    """Velas del activo según `config.fuente_datos`, recortadas a
    [fecha_inicio, fecha_fin). Es la única puerta de entrada de datos."""
    if config.fuente_datos == "disco":
        datos = cargar_historico(ticker, config.intervalo, config.version_datos)
        if config.fecha_inicio is not None:
            datos = datos[datos.index >= pd.Timestamp(config.fecha_inicio, tz="UTC")]
        if config.fecha_fin is not None:
            datos = datos[datos.index < pd.Timestamp(config.fecha_fin, tz="UTC")]
        if datos.empty:
            raise ValueError(f"{ticker}: no hay velas en datos/{config.version_datos} para ese rango.")
        return datos
    if config.fuente_datos == "api":
        return descargar(config, ticker)
    raise ValueError(f"fuente_datos debe ser 'disco' o 'api', recibido '{config.fuente_datos}'.")


def descargar(config: Configuracion, ticker: str) -> pd.DataFrame:
    """Descarga velas CERRADAS de un activo y comprueba su cobertura."""
    proveedor = ProveedorDatos(exchange_id=config.exchange_id)
    datos = proveedor.obtener_datos(
        ParametrosDescarga(
            ticker=ticker,
            tipo=config.tipo_activo,
            intervalo=config.intervalo,
            periodo=config.periodo_historico,
            exchange_id=config.exchange_id,
            fecha_inicio=config.fecha_inicio,
            fecha_fin=config.fecha_fin,
        )
    )
    dias_solicitados, dias_cubiertos, pct = _cobertura_historica(datos, config)
    if pct < config.cobertura_minima_pct:
        raise ValueError(
            f"{ticker}: el histórico descargado cubre ~{dias_cubiertos} de ~{dias_solicitados} "
            f"días ({pct:.1f} %), por debajo del mínimo exigido ({config.cobertura_minima_pct} %). "
            f"Con '{config.exchange_id}' la API pública puede no servir histórico antiguo "
            "(Kraken: 720 velas). Usa los datos versionados de la Fase 1."
        )
    return datos


def _cobertura_historica(datos: pd.DataFrame, config: Configuracion) -> tuple[int, int, float]:
    """(días solicitados, días cubiertos, % de cobertura) del histórico real.

    Existe porque un exchange puede devolver datos sin error pero empezando
    mucho más tarde de lo pedido (auditoría P1: Kraken, 720 velas).
    """
    if config.fecha_inicio is not None:
        fin = pd.Timestamp(config.fecha_fin, tz="UTC") if config.fecha_fin else pd.Timestamp.now(tz="UTC")
        dias_solicitados = (fin - pd.Timestamp(config.fecha_inicio, tz="UTC")).days
    else:
        dias_solicitados = _parsear_periodo_a_dias(config.periodo_historico)
    dias_cubiertos = (datos.index.max() - datos.index.min()).days
    pct = (dias_cubiertos / dias_solicitados * 100) if dias_solicitados else 0.0
    return dias_solicitados, dias_cubiertos, pct


# =============================================================================
# Pipeline de un activo
# =============================================================================

def ejecutar_pipeline(config: Configuracion, datos: Optional[pd.DataFrame] = None) -> ResultadoBacktest:
    """Datos -> señales -> backtest -> informe (completo y particionado).

    `datos` permite pasar velas ya cargadas (p. ej. del disco en la Fase 1,
    o sintéticas en los tests) en vez de descargarlas.
    """
    if datos is None:
        logger.info("Etapa 1/3: datos de %s (%s, %s)...", config.ticker, config.intervalo, config.fuente_datos)
        datos = obtener_velas(config, config.ticker)

    logger.info("Etapa 2/3: señales (%s)...", config.disparador_entrada)
    df_senales = generar_senales(datos, **kwargs_senales(config))

    logger.info("Etapa 3/3: backtest...")
    params = parametros_backtest(config, config.ticker)
    resultado = MotorBacktest(params, activo=config.ticker).ejecutar(df_senales)

    imprimir_reporte(resultado, divisa=config.divisa)
    imprimir_reporte_particionado(
        particionar_resultado(resultado, params, fraccion_oos=config.fraccion_oos), config.divisa
    )
    ruta = graficar_equity_drawdown(resultado, config.ruta_grafico)
    logger.info("Gráfico de equity/drawdown guardado en: %s", ruta)
    return resultado


# =============================================================================
# Backtest MULTIACTIVO
# =============================================================================
#
# SIMPLIFICACIÓN DE DISEÑO (no se oculta): cada activo se backtestea de forma
# independiente con una porción fija e igual del capital (capital / nº de
# activos), sin rebalanceo ni presupuesto de riesgo compartido. Equivale a N
# estrategias en paralelo con su propia hucha. Las criptos están muy
# correlacionadas: sumar activos aumenta el nº de operaciones, pero no
# diversifica como lo harían activos independientes. Además, el riesgo
# efectivo por operación es `riesgo_por_operacion` de la PORCIÓN del activo,
# no del capital total (con 2 activos y 1 %, un 0,5 % del total).


@dataclass
class ResultadoMultiActivo:
    """Detalle por activo y resultado combinado (pool + curva agregada)."""

    resultados_por_activo: dict[str, ResultadoBacktest]
    resultado_combinado: ResultadoBacktest
    parametros_combinados: ParametrosBacktest


def _combinar_curvas_equity(curvas: dict[str, pd.Series], capital_por_activo: float) -> pd.Series:
    """Suma las curvas de equity de varios activos independientes.

    Antes del inicio del histórico de un activo, su porción de capital se
    considera intacta y sin invertir (`fillna(capital_por_activo)`).
    """
    indice_unido = None
    for serie in curvas.values():
        indice_unido = serie.index if indice_unido is None else indice_unido.union(serie.index)
    indice_unido = indice_unido.sort_values()

    curva_combinada = pd.Series(0.0, index=indice_unido)
    for serie in curvas.values():
        curva_combinada = curva_combinada.add(
            serie.reindex(indice_unido).ffill().fillna(capital_por_activo), fill_value=0.0
        )
    curva_combinada.name = "equity_combinada"
    return curva_combinada


def ejecutar_pipeline_multiactivo(
    config: Configuracion, datos_por_activo: Optional[dict[str, pd.DataFrame]] = None
) -> ResultadoMultiActivo:
    """Pipeline completo para cada activo de `config.activos` y pool combinado.

    Dos fases para que el capital cuadre: primero se descargan y señalizan
    TODOS los activos; el capital se reparte solo entre los que salieron
    bien. Un activo que falla (no cotiza, histórico insuficiente) se omite
    con un aviso en el log, sin abortar el resto.
    """
    if not config.activos:
        raise ValueError("`config.activos` está vacío: no hay ningún activo que backtestear.")

    # --- Fase 1: datos + señales por activo ---
    senales_por_activo: dict[str, pd.DataFrame] = {}
    for ticker in config.activos:
        try:
            datos = datos_por_activo[ticker] if datos_por_activo is not None else obtener_velas(config, ticker)
            senales_por_activo[ticker] = generar_senales(datos, **kwargs_senales(config))
        except Exception:
            logger.warning("Activo %s omitido del backtest combinado.", ticker, exc_info=True)

    if not senales_por_activo:
        raise RuntimeError(
            "Ningún activo de la cesta pudo backtestearse. Revisa conectividad, `exchange_id`, "
            "los tickers y, sobre todo, la cobertura histórica (ver avisos anteriores)."
        )

    # --- Fase 2: reparto de capital SOLO entre los supervivientes ---
    capital_por_activo = config.capital_inicial / len(senales_por_activo)
    resultados_por_activo = {
        ticker: MotorBacktest(parametros_backtest(config, ticker, capital_por_activo), activo=ticker)
        .ejecutar(df_senales)
        for ticker, df_senales in senales_por_activo.items()
    }

    # --- Agregación ---
    todos_los_trades: list[Trade] = sorted(
        (t for r in resultados_por_activo.values() for t in r.trades), key=lambda t: t.fecha_entrada
    )
    curva_combinada = _combinar_curvas_equity(
        {t: r.curva_capital for t, r in resultados_por_activo.items()}, capital_por_activo
    )
    params_combinados = ParametrosBacktest(
        capital_inicial=config.capital_inicial, periodos_por_anio=config.periodos_anuales()
    )
    resultado_combinado = ResultadoBacktest(
        trades=todos_los_trades,
        curva_capital=curva_combinada,
        metricas=calcular_metricas(todos_los_trades, curva_combinada, params_combinados),
        capital_inicial=config.capital_inicial,
        capital_final=float(curva_combinada.iloc[-1]),
    )
    return ResultadoMultiActivo(resultados_por_activo, resultado_combinado, params_combinados)


def imprimir_reporte_multiactivo(resultado: ResultadoMultiActivo, config: Configuracion = CONFIG) -> None:
    """Desglose por activo, informe combinado y su partición dentro/fuera."""
    for ticker, resultado_activo in resultado.resultados_por_activo.items():
        imprimir_reporte(resultado_activo, f"ACTIVO: {ticker}", config.divisa)
    imprimir_reporte(resultado.resultado_combinado, "COMBINADO (pool de todos los activos)", config.divisa)
    imprimir_reporte_particionado(
        particionar_resultado(
            resultado.resultado_combinado, resultado.parametros_combinados, fraccion_oos=config.fraccion_oos
        ),
        config.divisa,
    )


# =============================================================================
# Diagnóstico de un único activo: dónde se pierden las entradas.
# =============================================================================

def diagnosticar_activo(config: Configuracion, ticker: str, datos: Optional[pd.DataFrame] = None) -> None:
    """Separa dos causas de "pocas o cero operaciones": datos malos (velas
    planas, histórico corto) o filtros demasiado restrictivos (embudo filtro
    a filtro sobre el evento bruto de entrada del disparador configurado).
    """
    if datos is None:
        datos = obtener_velas(config, ticker)

    print(f"\n{'=' * 60}\nDIAGNÓSTICO: {ticker}\n{'=' * 60}")
    print(f"Velas: {len(datos)} | rango: {datos.index.min()} -> {datos.index.max()}")
    pct_unicos = datos["Close"].nunique() / len(datos) * 100
    print(f"Cierres distintos: {pct_unicos:.1f} %")
    if pct_unicos < 50.0:
        print("AVISO: muchas velas planas; típico de pares con poca liquidez (el problema sería el dato).")
    dias_solicitados, dias_cubiertos, pct = _cobertura_historica(datos, config)
    print(f"Histórico solicitado ~{dias_solicitados} días | cubierto ~{dias_cubiertos} ({pct:.1f} %)")
    if pct < config.cobertura_minima_pct:
        print("AVISO: histórico truncado; cualquier conclusión sobre este activo es sobre una ventana corta.")

    df = generar_senales(datos, **kwargs_senales(config))
    evento = df["evento_entrada_largo"] & df["calentamiento_ok"]
    print(f"\nEventos brutos de entrada larga ({config.disparador_entrada}), tras calentamiento: "
          f"{int(evento.sum())}")
    if config.usar_filtro_macro:
        filtro = df["Close"] > df["ema_macro"]
        print(f"  ...con Close > EMA{config.periodo_ema_macro}: {int((evento & filtro).sum())} "
              f"(velas en tendencia macro: {filtro.mean() * 100:.1f} %)")
    if config.usar_adx:
        filtro = df["adx"] >= config.umbral_adx
        print(f"  ...con ADX >= {config.umbral_adx}: {int((evento & filtro).sum())}")
    print(f"Entradas largas finales (todos los filtros): {int((df['entrada'] == 1).sum())}")
    print("=" * 60)


if __name__ == "__main__":
    resultado_multiactivo = ejecutar_pipeline_multiactivo(CONFIG)
    imprimir_reporte_multiactivo(resultado_multiactivo, CONFIG)
    ruta_grafico = graficar_equity_drawdown(resultado_multiactivo.resultado_combinado, CONFIG.ruta_grafico)
    logger.info("Gráfico de equity/drawdown combinado guardado en: %s", ruta_grafico)
