"""
=============================================================================
 BOT-PREDICT · MÓDULO 4: Motor de backtesting, costes de fricción y métricas
=============================================================================

Objetivo del módulo
--------------------
Simular la ejecución histórica de la estrategia (Módulo 2) con gestión de
riesgo real (Módulo 3), vela a vela, respetando estrictamente la
cronología temporal, e incluyendo comisiones y slippage — para terminar
con un conjunto de métricas de rendimiento estándar en la industria.

Lógica del bucle: cómo se evita el lookahead bias (sesgo de anticipación)
--------------------------------------------------------------------------
El error más peligroso al programar un backtest —y el más fácil de
cometer sin darse cuenta— es usar información que en la realidad no
estaría disponible todavía en el momento de decidir. Dos reglas estrictas
gobiernan este motor:

1. LA SEÑAL SE CONFIRMA AL CIERRE, SE EJECUTA EN LA SIGUIENTE APERTURA.
   La columna `senal` del Módulo 2, en la vela `i`, se calculó con datos
   disponibles HASTA el cierre de la vela `i` (EMA, RSI, ATR de esa
   vela). En la realidad, no puedes comprar al precio de cierre que
   acabas de ver confirmarse: para cuando lo confirmas, esa vela ya
   cerró. Por eso este motor SIEMPRE ejecuta una entrada o una salida por
   señal en la APERTURA de la vela `i+1`, nunca en el cierre de la vela
   `i`. Es la diferencia entre "backtest realista" y "backtest con bola
   de cristal".

2. EL STOP-LOSS Y EL TAKE-PROFIT SÍ SE EVALÚAN EN TIEMPO REAL (INTRAVELA).
   Esto no es una inconsistencia: un stop-loss es una orden que ya está
   colocada en el mercado ANTES de que la vela se forme. Si el precio la
   toca durante la vela `i` (usando el High/Low de esa misma vela), la
   orden se ejecuta ahí — no hace falta esperar al cierre para "confirmar"
   nada, porque no es una señal calculada por nosotros, es una orden real
   ya en el libro. Si el High y el Low de una misma vela tocan tanto el
   stop como el take-profit (vela con rango amplio), este motor asume,
   de forma CONSERVADORA, que el stop se ejecutó primero — no hay forma
   de saber el orden real intravela con datos OHLC, y asumir lo peor es
   la postura defensiva correcta para un backtest honesto.

3. NO SE REABRE POSICIÓN EN LA MISMA VELA EN QUE SE CERRÓ OTRA.
   Simplificación deliberada para evitar operativa intravela imposible de
   validar con datos OHLC (no sabemos el orden exacto de los eventos
   dentro de una vela). Se documenta explícitamente aquí, no se oculta.

Advertencia honesta sobre sesgos de backtesting
--------------------------------------------------
Este motor reduce el lookahead bias y modela comisiones/slippage, pero
NINGÚN backtest está libre de sesgos. Tenlos siempre presentes:

- SESGO DE SUPERVIVENCIA (survivorship bias): si pruebas la estrategia
  solo sobre activos que "siguen existiendo hoy" (el índice actual, el
  ticker que no quebró ni fue deslistado), estás excluyendo sistemáticamente
  los peores casos históricos. Los resultados quedarán artificialmente
  mejores que lo que un inversor real habría experimentado.
- SOBREAJUSTE / DATA SNOOPING (overfitting): si ajustas los parámetros
  (EMA 20/50, ATR, RSI, multiplicadores) buscando el mejor resultado
  posible sobre EL MISMO histórico que usas para validar, estás
  memorizando ruido pasado, no descubriendo una ventaja real. La prueba
  de fuego es un conjunto de datos "fuera de muestra" (out-of-sample) que
  el proceso de optimización nunca vio.
- COMISIONES Y SLIPPAGE: modelados aquí como parámetros (`comision_pct`,
  `slippage_pct`), pero son ESTIMACIONES. En mercados de baja liquidez o
  en momentos de alta volatilidad, el slippage real puede ser
  significativamente mayor que el estimado — y una estrategia con muchas
  operaciones puede verse castigada de forma desproporcionada por estos
  costes, algo que un backtest sin fricción jamás revelaría.
- Rendimiento pasado, incluso simulado con honestidad, NO garantiza
  resultados futuros. Este motor busca robustez de PROCESO (gestión de
  riesgo, ausencia de lookahead), no una predicción del rendimiento real.
=============================================================================
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from modulo_3_riesgo import calcular_gestion_riesgo

logger = logging.getLogger("bot_predict.backtesting")


# -----------------------------------------------------------------------
# Estructuras de datos
# -----------------------------------------------------------------------

@dataclass
class ParametrosBacktest:
    """Hiperparámetros del motor de backtest."""

    capital_inicial: float = 10_000.0
    riesgo_por_operacion: float = 0.01
    interes_compuesto: bool = True  # True: sizing sobre capital flotante realizado.
    comision_pct: float = 0.0006    # 0.06% por entrada y por salida.
    slippage_pct: float = 0.0002    # 0.02% de deslizamiento, siempre en contra.
    atr_mult_stop_largo: float = 2.0
    atr_mult_stop_corto: float = 1.5
    ratio_riesgo_beneficio: float = 2.0
    permitir_apalancamiento: bool = False
    unidades_fraccionables: bool = True
    periodos_por_anio: int = 2190   # 4h, mercado 24/7 (cripto): 6 velas/día * 365.


@dataclass
class Trade:
    """Registro completo de una operación cerrada."""

    fecha_entrada: pd.Timestamp
    fecha_salida: pd.Timestamp
    direccion: int              # 1 largo, -1 corto
    precio_entrada: float       # Precio efectivo (con slippage) ya incluido.
    precio_salida: float        # Precio efectivo (con slippage) ya incluido.
    unidades: float
    motivo_salida: str          # 'stop_loss' | 'take_profit' | 'senal_contraria' | 'fin_de_datos'
    comision_total: float
    pnl_bruto: float
    pnl_neto: float
    capital_antes: float
    capital_despues: float
    # Ticker del activo al que pertenece esta operación. Cadena vacía por
    # defecto (retrocompatible con ejecuciones de un solo activo, donde no
    # aporta información nueva); se rellena cuando `MotorBacktest` se
    # ejecuta dentro de un backtest multiactivo (ver `main.py`), para poder
    # desglosar el trade pool combinado por activo si hace falta.
    activo: str = ""


@dataclass
class ResultadoBacktest:
    """Salida completa del motor: operaciones, curva de capital y métricas."""

    trades: list[Trade]
    curva_capital: pd.Series           # Equity mark-to-market por vela.
    metricas: dict[str, float]
    capital_inicial: float
    capital_final: float


# -----------------------------------------------------------------------
# Motor de backtest
# -----------------------------------------------------------------------

class MotorBacktest:
    """Simula la ejecución histórica de una estrategia ya señalizada.

    Espera un DataFrame con las columnas OHLCV (Módulo 1), más `senal` y
    `atr` (Módulo 2, salida de `generar_senales`). No vuelve a calcular
    indicadores: este motor solo se encarga de EJECUTAR, dimensionar
    (Módulo 3) y contabilizar.
    """

    def __init__(self, params: ParametrosBacktest | None = None, activo: str = "") -> None:
        self.params = params or ParametrosBacktest()
        # Etiqueta puramente informativa para backtests multiactivo (ver
        # `main.py::ejecutar_pipeline_multiactivo`): no afecta a ningún
        # cálculo, solo se estampa en cada `Trade` para poder identificar de
        # qué activo procede una vez se agrupan las operaciones de varios
        # activos en un único pool.
        self._activo = activo

    def ejecutar(self, df: pd.DataFrame) -> ResultadoBacktest:
        p = self.params
        df = df.dropna(subset=["ema_lenta", "atr", "rsi"]).copy()  # descarta warm-up.
        if df.empty:
            raise ValueError("El DataFrame no tiene suficientes velas tras el warm-up de indicadores.")

        capital_realizado = p.capital_inicial
        en_posicion = False
        direccion_activa = 0
        precio_entrada_activo = 0.0
        precio_stop_activo = 0.0
        precio_tp_activo = 0.0
        unidades_activas = 0.0
        comision_entrada_activa = 0.0
        fecha_entrada_activa: pd.Timestamp | None = None

        trades: list[Trade] = []
        curva_capital: list[tuple[pd.Timestamp, float]] = []

        indices = df.index
        n = len(df)

        for i in range(n):
            fecha_i = indices[i]
            apertura_i = float(df["Open"].iloc[i])
            alto_i = float(df["High"].iloc[i])
            bajo_i = float(df["Low"].iloc[i])
            cierre_i = float(df["Close"].iloc[i])

            en_posicion_al_inicio = en_posicion

            # --- 1) Si hay posición abierta: comprobar stop / take-profit / señal contraria ---
            if en_posicion_al_inicio:
                if direccion_activa == 1:
                    toco_stop = bajo_i <= precio_stop_activo
                    toco_tp = alto_i >= precio_tp_activo
                else:  # corto
                    toco_stop = alto_i >= precio_stop_activo
                    toco_tp = bajo_i <= precio_tp_activo

                precio_salida_bruto: float | None = None
                motivo_salida = ""

                if toco_stop and toco_tp:
                    # Ambigüedad intravela: postura conservadora, se asume el stop primero.
                    precio_salida_bruto = precio_stop_activo
                    motivo_salida = "stop_loss"
                elif toco_stop:
                    precio_salida_bruto = precio_stop_activo
                    motivo_salida = "stop_loss"
                elif toco_tp:
                    precio_salida_bruto = precio_tp_activo
                    motivo_salida = "take_profit"
                else:
                    # Señal contraria confirmada en el CIERRE de la vela ANTERIOR,
                    # ejecutada en la APERTURA de esta vela (regla anti-lookahead).
                    senal_previa = int(df["senal"].iloc[i - 1]) if i > 0 else 0
                    if senal_previa != direccion_activa:
                        precio_salida_bruto = apertura_i
                        motivo_salida = "senal_contraria"

                if precio_salida_bruto is not None:
                    capital_realizado = self._cerrar_trade(
                        trades=trades,
                        direccion=direccion_activa,
                        fecha_entrada=fecha_entrada_activa,
                        fecha_salida=fecha_i,
                        precio_entrada_efectivo=precio_entrada_activo,
                        precio_salida_bruto=precio_salida_bruto,
                        unidades=unidades_activas,
                        comision_entrada=comision_entrada_activa,
                        motivo_salida=motivo_salida,
                        capital_antes=capital_realizado,
                    )
                    en_posicion = False

            # --- 2) Si seguía plano desde el inicio de la vela: evaluar entrada ---
            if not en_posicion_al_inicio:
                senal_previa = int(df["senal"].iloc[i - 1]) if i > 0 else 0
                if senal_previa != 0:
                    atr_prev = float(df["atr"].iloc[i - 1]) if i > 0 else float(df["atr"].iloc[i])
                    capital_para_sizing = capital_realizado if p.interes_compuesto else p.capital_inicial

                    precio_entrada_bruto = apertura_i
                    factor_slippage = 1 + p.slippage_pct if senal_previa == 1 else 1 - p.slippage_pct
                    precio_entrada_efectivo = precio_entrada_bruto * factor_slippage

                    plan = calcular_gestion_riesgo(
                        precio_entrada=precio_entrada_efectivo,
                        atr=atr_prev,
                        direccion=senal_previa,
                        capital_cuenta=capital_para_sizing,
                        riesgo_por_operacion=p.riesgo_por_operacion,
                        atr_mult_stop_largo=p.atr_mult_stop_largo,
                        atr_mult_stop_corto=p.atr_mult_stop_corto,
                        ratio_riesgo_beneficio=p.ratio_riesgo_beneficio,
                        unidades_fraccionables=p.unidades_fraccionables,
                        permitir_apalancamiento=p.permitir_apalancamiento,
                    )

                    if plan.tamano_posicion > 0:
                        en_posicion = True
                        direccion_activa = senal_previa
                        precio_entrada_activo = precio_entrada_efectivo
                        precio_stop_activo = plan.precio_stop_loss
                        precio_tp_activo = plan.precio_take_profit
                        unidades_activas = plan.tamano_posicion
                        comision_entrada_activa = p.comision_pct * unidades_activas * precio_entrada_efectivo
                        fecha_entrada_activa = fecha_i
                    else:
                        logger.debug("Señal en %s descartada: %s", fecha_i, plan.advertencias)

            # --- 3) Registrar equity mark-to-market de esta vela ---
            if en_posicion:
                pnl_flotante = (cierre_i - precio_entrada_activo) * unidades_activas * direccion_activa
                equity_actual = capital_realizado + pnl_flotante
            else:
                equity_actual = capital_realizado
            curva_capital.append((fecha_i, equity_actual))

        # --- Cierre forzoso de una posición que quede abierta al final de los datos ---
        if en_posicion:
            capital_realizado = self._cerrar_trade(
                trades=trades,
                direccion=direccion_activa,
                fecha_entrada=fecha_entrada_activa,
                fecha_salida=indices[-1],
                precio_entrada_efectivo=precio_entrada_activo,
                precio_salida_bruto=float(df["Close"].iloc[-1]),
                unidades=unidades_activas,
                comision_entrada=comision_entrada_activa,
                motivo_salida="fin_de_datos",
                capital_antes=capital_realizado,
            )
            curva_capital[-1] = (indices[-1], capital_realizado)

        serie_equity = pd.Series(
            [c for _, c in curva_capital],
            index=[f for f, _ in curva_capital],
            name="equity",
        )
        metricas = calcular_metricas(trades, serie_equity, p)

        return ResultadoBacktest(
            trades=trades,
            curva_capital=serie_equity,
            metricas=metricas,
            capital_inicial=p.capital_inicial,
            capital_final=float(serie_equity.iloc[-1]) if len(serie_equity) else p.capital_inicial,
        )

    def _cerrar_trade(
        self,
        trades: list[Trade],
        direccion: int,
        fecha_entrada: pd.Timestamp,
        fecha_salida: pd.Timestamp,
        precio_entrada_efectivo: float,
        precio_salida_bruto: float,
        unidades: float,
        comision_entrada: float,
        motivo_salida: str,
        capital_antes: float,
    ) -> float:
        """Aplica slippage/comisión de salida, calcula el PnL neto de la
        operación y devuelve el nuevo capital realizado.
        """
        p = self.params
        factor_slippage_salida = 1 - p.slippage_pct if direccion == 1 else 1 + p.slippage_pct
        precio_salida_efectivo = precio_salida_bruto * factor_slippage_salida

        comision_salida = p.comision_pct * unidades * precio_salida_efectivo
        comision_total = comision_entrada + comision_salida

        pnl_bruto = (precio_salida_efectivo - precio_entrada_efectivo) * unidades * direccion
        pnl_neto = pnl_bruto - comision_total
        capital_despues = capital_antes + pnl_neto

        trades.append(
            Trade(
                fecha_entrada=fecha_entrada,
                fecha_salida=fecha_salida,
                direccion=direccion,
                precio_entrada=precio_entrada_efectivo,
                precio_salida=precio_salida_efectivo,
                unidades=unidades,
                motivo_salida=motivo_salida,
                comision_total=comision_total,
                pnl_bruto=pnl_bruto,
                pnl_neto=pnl_neto,
                capital_antes=capital_antes,
                capital_despues=capital_despues,
                activo=self._activo,
            )
        )
        return capital_despues


# -----------------------------------------------------------------------
# Métricas de rendimiento
# -----------------------------------------------------------------------

def calcular_metricas(
    trades: list[Trade],
    curva_capital: pd.Series,
    params: ParametrosBacktest,
) -> dict[str, float]:
    """Calcula el bloque estándar de métricas cuantitativas de rendimiento."""
    capital_inicial = params.capital_inicial
    capital_final = float(curva_capital.iloc[-1]) if len(curva_capital) else capital_inicial

    n_trades = len(trades)
    n_largos = sum(1 for t in trades if t.direccion == 1)
    n_cortos = sum(1 for t in trades if t.direccion == -1)

    pnls = np.array([t.pnl_neto for t in trades], dtype=float)
    ganadores = pnls[pnls > 0]
    perdedores = pnls[pnls <= 0]

    win_rate = (len(ganadores) / n_trades * 100) if n_trades else 0.0

    ganancia_bruta = ganadores.sum() if len(ganadores) else 0.0
    perdida_bruta = abs(perdedores.sum()) if len(perdedores) else 0.0
    profit_factor = (ganancia_bruta / perdida_bruta) if perdida_bruta > 0 else np.inf

    media_ganancia = ganadores.mean() if len(ganadores) else 0.0
    media_perdida = abs(perdedores.mean()) if len(perdedores) else 0.0
    ratio_payoff = (media_ganancia / media_perdida) if media_perdida > 0 else np.inf

    # --- Max Drawdown sobre la curva de equity (mark-to-market) ---
    if len(curva_capital):
        maximo_acumulado = curva_capital.cummax()
        drawdown_serie = curva_capital - maximo_acumulado
        drawdown_pct_serie = drawdown_serie / maximo_acumulado
        max_drawdown_divisa = float(drawdown_serie.min())
        max_drawdown_pct = float(drawdown_pct_serie.min() * 100)
    else:
        max_drawdown_divisa = 0.0
        max_drawdown_pct = 0.0

    # --- Sharpe y Sortino sobre retornos por vela de la curva de equity ---
    retornos = curva_capital.pct_change().dropna()
    if len(retornos) > 1 and retornos.std() > 0:
        sharpe = (retornos.mean() / retornos.std()) * np.sqrt(params.periodos_por_anio)
    else:
        sharpe = 0.0

    retornos_negativos = retornos[retornos < 0]
    if len(retornos_negativos) > 1 and retornos_negativos.std() > 0:
        sortino = (retornos.mean() / retornos_negativos.std()) * np.sqrt(params.periodos_por_anio)
    else:
        sortino = np.inf if retornos.mean() > 0 else 0.0

    rentabilidad_divisa = capital_final - capital_inicial
    rentabilidad_pct = (capital_final / capital_inicial - 1) * 100 if capital_inicial else 0.0

    return {
        "capital_inicial": capital_inicial,
        "capital_final": capital_final,
        "rentabilidad_neta_divisa": rentabilidad_divisa,
        "rentabilidad_neta_pct": rentabilidad_pct,
        "max_drawdown_divisa": max_drawdown_divisa,
        "max_drawdown_pct": max_drawdown_pct,
        "win_rate_pct": win_rate,
        "profit_factor": profit_factor,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "ratio_payoff": ratio_payoff,
        "num_trades": n_trades,
        "num_trades_largos": n_largos,
        "num_trades_cortos": n_cortos,
        "comisiones_totales": float(sum(t.comision_total for t in trades)),
    }


# -----------------------------------------------------------------------
# Reporte por consola
# -----------------------------------------------------------------------

def imprimir_reporte(resultado: ResultadoBacktest) -> None:
    """Imprime un resumen formateado de los resultados del backtest."""
    m = resultado.metricas
    ancho = 56
    print("=" * ancho)
    print("  INFORME DE BACKTESTING — BOT-PREDICT")
    print("=" * ancho)
    print(f"  Capital inicial:            ${m['capital_inicial']:,.2f}")
    print(f"  Capital final:              ${m['capital_final']:,.2f}")
    print(f"  Rentabilidad neta:          ${m['rentabilidad_neta_divisa']:,.2f}  "
          f"({m['rentabilidad_neta_pct']:+.2f}%)")
    print(f"  Comisiones totales pagadas: ${m['comisiones_totales']:,.2f}")
    print("-" * ancho)
    print(f"  Max Drawdown:               {m['max_drawdown_pct']:.2f}%  "
          f"(${m['max_drawdown_divisa']:,.2f})")
    print(f"  Sharpe Ratio (anualizado):  {m['sharpe_ratio']:.2f}")
    print(f"  Sortino Ratio (anualizado): {m['sortino_ratio']:.2f}")
    print("-" * ancho)
    print(f"  Nº operaciones:             {m['num_trades']} "
          f"(largos: {m['num_trades_largos']}, cortos: {m['num_trades_cortos']})")
    print(f"  Win Rate:                   {m['win_rate_pct']:.2f}%")
    print(f"  Profit Factor:              {m['profit_factor']:.2f}")
    print(f"  Ratio ganancia/pérdida media:{m['ratio_payoff']:.2f}")
    print("=" * ancho)
    print("  Recuerda: sesgo de supervivencia, overfitting y slippage real")
    print("  pueden diferir de lo simulado aquí. Ver docstring del módulo.")
    print("=" * ancho)


# -----------------------------------------------------------------------
# Gráfico de curva de capital + drawdown
# -----------------------------------------------------------------------

def graficar_equity_drawdown(resultado: ResultadoBacktest, ruta_salida: str = "equity_drawdown.png") -> str:
    """Genera un gráfico con la curva de capital y el drawdown asociado.

    Se guarda a disco (en vez de `plt.show()`) para que funcione igual en
    Colab, en un script local o dentro de un pipeline sin entorno gráfico.
    """
    import matplotlib.pyplot as plt

    curva = resultado.curva_capital
    maximo_acumulado = curva.cummax()
    drawdown_pct = (curva - maximo_acumulado) / maximo_acumulado * 100

    fig, (ax_equity, ax_drawdown) = plt.subplots(
        2, 1, figsize=(11, 6), sharex=True,
        gridspec_kw={"height_ratios": [2.2, 1]},
    )

    ax_equity.plot(curva.index, curva.values, color="#1f77b4", linewidth=1.3)
    ax_equity.axhline(resultado.capital_inicial, color="gray", linestyle="--", linewidth=0.8)
    ax_equity.set_title("Curva de capital (equity)")
    ax_equity.set_ylabel("Capital ($)")
    ax_equity.grid(alpha=0.3)

    ax_drawdown.fill_between(drawdown_pct.index, drawdown_pct.values, 0, color="#d62728", alpha=0.4)
    ax_drawdown.set_title("Drawdown")
    ax_drawdown.set_ylabel("Drawdown (%)")
    ax_drawdown.grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(ruta_salida, dpi=140)
    plt.close(fig)
    return ruta_salida


# =============================================================================
# Bloque de validación end-to-end (Módulo 1 sintético -> 2 -> 3 -> 4)
# =============================================================================
if __name__ == "__main__":
    from modulo_2_estrategia import generar_senales

    rng = np.random.default_rng(11)
    n = 1500
    indice = pd.date_range("2022-01-01", periods=n, freq="4h", tz="UTC")
    # Random walk con tendencia suave y ciclos, para generar varios trades.
    ruido = rng.normal(0, 1, n)
    ciclo = 8 * np.sin(np.linspace(0, 12 * np.pi, n))
    tendencia = np.linspace(0, 15, n)
    precio_base = 100 + np.cumsum(ruido * 0.6) + ciclo + tendencia
    df_simulado = pd.DataFrame(
        {
            "Open": precio_base,
            "High": precio_base + rng.random(n) * 1.5,
            "Low": precio_base - rng.random(n) * 1.5,
            "Close": precio_base + rng.normal(0, 0.4, n),
            "Volume": rng.integers(100, 1000, n),
        },
        index=indice,
    )

    df_senales = generar_senales(df_simulado, permitir_cortos=True)

    parametros = ParametrosBacktest(
        capital_inicial=10_000.0,
        riesgo_por_operacion=0.01,
        interes_compuesto=True,
        comision_pct=0.0006,
        slippage_pct=0.0002,
    )
    motor = MotorBacktest(parametros)
    resultado = motor.ejecutar(df_senales)

    imprimir_reporte(resultado)
    ruta = graficar_equity_drawdown(resultado, "equity_drawdown_demo.png")
    print(f"\nGráfico guardado en: {ruta}")
