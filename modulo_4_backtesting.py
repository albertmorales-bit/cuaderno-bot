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

   Desde la Fase 0 esto incluye la propia vela de entrada (la v4 no lo
   comprobaba: auditoría P2), y un hueco que abre más allá del stop se
   ejecuta a la apertura, no al precio del stop (P3).

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

import csv
import logging
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

from modulo_3_riesgo import calcular_gestion_riesgo

logger = logging.getLogger("bot_predict.backtesting")


# -----------------------------------------------------------------------
# Estructuras de datos
# -----------------------------------------------------------------------

# Costes por defecto (auditoría Fase 0, P5): Kraken Pro, nivel 1 de volumen,
# tarifa oficial vigente desde el 9-jul-2026: maker 0,40 % / taker 0,80 %.
# El motor ejecuta a mercado en la apertura -> paga TAKER. El slippage del
# 0,10 % es una estimación pesimista para BTC/EUR y ETH/EUR en la apertura
# diaria. Ver DECISIONES.md (D-005).
COMISION_TAKER_KRAKEN = 0.0080
SLIPPAGE_PESIMISTA = 0.0010


@dataclass
class ParametrosBacktest:
    """Hiperparámetros del motor de backtest."""

    capital_inicial: float = 10_000.0
    riesgo_por_operacion: float = 0.01
    interes_compuesto: bool = True  # True: sizing sobre capital flotante realizado.
    comision_pct: float = COMISION_TAKER_KRAKEN   # Por entrada y por salida.
    slippage_pct: float = SLIPPAGE_PESIMISTA      # Siempre en contra.
    atr_mult_stop_largo: float = 2.0
    atr_mult_stop_corto: float = 1.5
    ratio_riesgo_beneficio: float = 2.0
    # False en la v5 (Turtle clásico: sale por stop o por canal de salida,
    # nunca por objetivo fijo, para no cortar las tendencias largas).
    usar_take_profit: bool = True
    permitir_apalancamiento: bool = False
    unidades_fraccionables: bool = True
    tamano_minimo: float = 0.0      # Mínimo de orden del exchange (unidades).
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
    # Ticker del activo (se rellena en el backtest multiactivo de `main.py`).
    activo: str = ""
    # Precios de referencia ANTES de slippage y coste del slippage en divisa:
    # el registro de transparencia de la Fase 5 los publica por separado.
    precio_entrada_referencia: float = float("nan")
    precio_salida_referencia: float = float("nan")
    coste_slippage: float = 0.0


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

def _salida_intravela(
    direccion: int,
    apertura: float,
    alto: float,
    bajo: float,
    precio_stop: float,
    precio_tp: float,
    usar_take_profit: bool,
    es_vela_de_entrada: bool,
) -> tuple[float | None, str]:
    """Decide si el stop o el take-profit se ejecutan dentro de la vela.

    Reglas conservadoras (auditoría Fase 0):
    - P3, hueco en contra: si la vela ABRE ya más allá del stop, la orden de
      stop se ejecuta a la apertura (peor precio), no al precio del stop.
      No aplica en la vela de entrada, porque ahí la apertura es la entrada.
    - Si el rango toca stop y take-profit, se asume el stop primero.
    - El take-profit nunca se ejecuta a un precio mejor que su nivel, aunque
      la vela abra por encima (postura pesimista).
    """
    if direccion == 1:
        if not es_vela_de_entrada and apertura <= precio_stop:
            return apertura, "stop_loss"
        if bajo <= precio_stop:
            return precio_stop, "stop_loss"
        if usar_take_profit and alto >= precio_tp:
            return precio_tp, "take_profit"
    else:
        if not es_vela_de_entrada and apertura >= precio_stop:
            return apertura, "stop_loss"
        if alto >= precio_stop:
            return precio_stop, "stop_loss"
        if usar_take_profit and bajo <= precio_tp:
            return precio_tp, "take_profit"
    return None, ""


class MotorBacktest:
    """Simula la ejecución histórica de una estrategia ya señalizada.

    Espera un DataFrame con OHLCV (Módulo 1) más las columnas `entrada`,
    `senal`, `atr` y `calentamiento_ok` (Módulo 2, `generar_senales`).

    Orden de los acontecimientos en cada vela `i` (auditoría Fase 0, P6):
      1. Apertura: si hay posición y la señal de la vela `i-1` ya no la
         respalda, se cierra a la apertura. Si no hay posición y hubo un
         EVENTO de entrada en `i-1`, se abre a la apertura.
      2. Dentro de la vela: stop / take-profit de la posición abierta,
         incluida la que se acaba de abrir en esta misma vela (P2).
      3. Cierre: se valora la posición a precio de cierre (mark-to-market,
         descontando ya la comisión de entrada).
    Nunca se reabre en la misma vela en la que se cerró otra posición.
    """

    def __init__(self, params: ParametrosBacktest | None = None, activo: str = "") -> None:
        self.params = params or ParametrosBacktest()
        self._activo = activo

    def ejecutar(self, df: pd.DataFrame) -> ResultadoBacktest:
        p = self.params
        faltan = {"entrada", "senal", "atr", "calentamiento_ok"} - set(df.columns)
        if faltan:
            raise ValueError(f"Faltan columnas del Módulo 2: {sorted(faltan)}")
        df = df[df["calentamiento_ok"].astype(bool)]
        if df.empty:
            raise ValueError("El DataFrame no tiene suficientes velas tras el calentamiento de indicadores.")

        apertura = df["Open"].to_numpy(dtype=float)
        alto = df["High"].to_numpy(dtype=float)
        bajo = df["Low"].to_numpy(dtype=float)
        cierre = df["Close"].to_numpy(dtype=float)
        entrada = df["entrada"].to_numpy(dtype=int)
        senal = df["senal"].to_numpy(dtype=int)
        atr = df["atr"].to_numpy(dtype=float)
        indices = df.index

        capital_realizado = p.capital_inicial
        posicion: dict | None = None
        trades: list[Trade] = []
        equity = np.empty(len(df))

        for i in range(len(df)):
            cerro_en_esta_vela = False

            # --- 1a) Cierre por señal a la apertura (señal confirmada en i-1) ---
            if posicion is not None and i > 0 and senal[i - 1] != posicion["direccion"]:
                capital_realizado = self._cerrar_trade(
                    trades, posicion, indices[i], apertura[i], "senal_contraria", capital_realizado
                )
                posicion = None
                cerro_en_esta_vela = True

            # --- 1b) Apertura por EVENTO de entrada confirmado en i-1 ---
            es_vela_de_entrada = False
            if posicion is None and not cerro_en_esta_vela and i > 0 and entrada[i - 1] != 0:
                posicion = self._abrir_posicion(
                    direccion=int(entrada[i - 1]),
                    fecha=indices[i],
                    precio_referencia=apertura[i],
                    atr_previo=atr[i - 1],
                    capital_realizado=capital_realizado,
                )
                es_vela_de_entrada = posicion is not None

            # --- 2) Stop / take-profit dentro de la vela ---
            if posicion is not None:
                precio_salida, motivo = _salida_intravela(
                    posicion["direccion"], apertura[i], alto[i], bajo[i],
                    posicion["stop"], posicion["tp"], p.usar_take_profit, es_vela_de_entrada,
                )
                if precio_salida is not None:
                    capital_realizado = self._cerrar_trade(
                        trades, posicion, indices[i], precio_salida, motivo, capital_realizado
                    )
                    posicion = None

            # --- 3) Equity mark-to-market al cierre ---
            if posicion is not None:
                flotante = (cierre[i] - posicion["precio"]) * posicion["unidades"] * posicion["direccion"]
                equity[i] = capital_realizado + flotante - posicion["comision_entrada"]
            else:
                equity[i] = capital_realizado

        # --- Cierre forzoso al final de los datos (se marca como tal) ---
        if posicion is not None:
            capital_realizado = self._cerrar_trade(
                trades, posicion, indices[-1], cierre[-1], "fin_de_datos", capital_realizado
            )
            equity[-1] = capital_realizado

        serie_equity = pd.Series(equity, index=indices, name="equity")
        metricas = calcular_metricas(trades, serie_equity, p)
        return ResultadoBacktest(
            trades=trades,
            curva_capital=serie_equity,
            metricas=metricas,
            capital_inicial=p.capital_inicial,
            capital_final=float(serie_equity.iloc[-1]),
        )

    def _abrir_posicion(
        self,
        direccion: int,
        fecha: pd.Timestamp,
        precio_referencia: float,
        atr_previo: float,
        capital_realizado: float,
    ) -> dict | None:
        """Dimensiona (Módulo 3) y abre una posición; None si se descarta."""
        p = self.params
        factor_slippage = 1 + p.slippage_pct if direccion == 1 else 1 - p.slippage_pct
        precio_efectivo = precio_referencia * factor_slippage
        capital_para_sizing = capital_realizado if p.interes_compuesto else p.capital_inicial
        plan = calcular_gestion_riesgo(
            precio_entrada=precio_efectivo,
            atr=atr_previo,
            direccion=direccion,
            capital_cuenta=capital_para_sizing,
            riesgo_por_operacion=p.riesgo_por_operacion,
            atr_mult_stop_largo=p.atr_mult_stop_largo,
            atr_mult_stop_corto=p.atr_mult_stop_corto,
            ratio_riesgo_beneficio=p.ratio_riesgo_beneficio,
            unidades_fraccionables=p.unidades_fraccionables,
            permitir_apalancamiento=p.permitir_apalancamiento,
            comision_pct=p.comision_pct,
            tamano_minimo=p.tamano_minimo,
        )
        if plan.tamano_posicion <= 0:
            logger.debug("Entrada en %s descartada: %s", fecha, plan.advertencias)
            return None
        return {
            "direccion": direccion,
            "fecha": fecha,
            "precio": precio_efectivo,
            "precio_referencia": precio_referencia,
            "stop": plan.precio_stop_loss,
            "tp": plan.precio_take_profit,
            "unidades": plan.tamano_posicion,
            "comision_entrada": p.comision_pct * plan.tamano_posicion * precio_efectivo,
        }

    def _cerrar_trade(
        self,
        trades: list[Trade],
        posicion: dict,
        fecha_salida: pd.Timestamp,
        precio_salida_bruto: float,
        motivo_salida: str,
        capital_antes: float,
    ) -> float:
        """Aplica slippage y comisión de salida, registra la operación y
        devuelve el nuevo capital realizado.
        """
        p = self.params
        direccion = posicion["direccion"]
        unidades = posicion["unidades"]
        factor_slippage_salida = 1 - p.slippage_pct if direccion == 1 else 1 + p.slippage_pct
        precio_salida_efectivo = precio_salida_bruto * factor_slippage_salida

        comision_total = posicion["comision_entrada"] + p.comision_pct * unidades * precio_salida_efectivo
        pnl_bruto = (precio_salida_efectivo - posicion["precio"]) * unidades * direccion
        pnl_neto = pnl_bruto - comision_total
        coste_slippage = unidades * (
            abs(posicion["precio"] - posicion["precio_referencia"])
            + abs(precio_salida_efectivo - precio_salida_bruto)
        )

        trades.append(
            Trade(
                fecha_entrada=posicion["fecha"],
                fecha_salida=fecha_salida,
                direccion=direccion,
                precio_entrada=posicion["precio"],
                precio_salida=precio_salida_efectivo,
                unidades=unidades,
                motivo_salida=motivo_salida,
                comision_total=comision_total,
                pnl_bruto=pnl_bruto,
                pnl_neto=pnl_neto,
                capital_antes=capital_antes,
                capital_despues=capital_antes + pnl_neto,
                activo=self._activo,
                precio_entrada_referencia=posicion["precio_referencia"],
                precio_salida_referencia=precio_salida_bruto,
                coste_slippage=coste_slippage,
            )
        )
        return capital_antes + pnl_neto


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

    if len(curva_capital):
        maximo_acumulado = curva_capital.cummax()
        drawdown_serie = curva_capital - maximo_acumulado
        max_drawdown_divisa = float(drawdown_serie.min())
        max_drawdown_pct = float((drawdown_serie / maximo_acumulado).min() * 100)
    else:
        max_drawdown_divisa = max_drawdown_pct = 0.0

    # Sharpe y Sortino sobre retornos por vela de la curva de equity.
    retornos = curva_capital.pct_change().dropna()
    if len(retornos) > 1 and retornos.std() > 0:
        sharpe = (retornos.mean() / retornos.std()) * np.sqrt(params.periodos_por_anio)
    else:
        sharpe = 0.0
    # Auditoría Fase 0 (P10): desviación a la baja estándar, sobre TODOS los
    # periodos (los positivos cuentan como 0). La v4 usaba la desviación
    # típica de los retornos negativos alrededor de su propia media, que
    # sale más pequeña e inflaba el Sortino.
    desviacion_baja = float(np.sqrt(np.mean(np.minimum(retornos.to_numpy(), 0.0) ** 2))) if len(retornos) else 0.0
    if desviacion_baja > 0:
        sortino = (retornos.mean() / desviacion_baja) * np.sqrt(params.periodos_por_anio)
    else:
        sortino = np.inf if len(retornos) and retornos.mean() > 0 else 0.0

    return {
        "capital_inicial": capital_inicial,
        "capital_final": capital_final,
        "rentabilidad_neta_divisa": capital_final - capital_inicial,
        "rentabilidad_neta_pct": (capital_final / capital_inicial - 1) * 100 if capital_inicial else 0.0,
        "max_drawdown_divisa": max_drawdown_divisa,
        "max_drawdown_pct": max_drawdown_pct,
        "win_rate_pct": win_rate,
        "profit_factor": profit_factor,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "ratio_payoff": ratio_payoff,
        "num_trades": n_trades,
        "num_trades_largos": sum(1 for t in trades if t.direccion == 1),
        "num_trades_cortos": sum(1 for t in trades if t.direccion == -1),
        # Operaciones cerradas a la fuerza por fin de datos: cuentan en las
        # métricas, pero su resultado no lo decidió la estrategia.
        "num_trades_fin_de_datos": sum(1 for t in trades if t.motivo_salida == "fin_de_datos"),
        "comisiones_totales": float(sum(t.comision_total for t in trades)),
        "slippage_total": float(sum(t.coste_slippage for t in trades)),
    }


# -----------------------------------------------------------------------
# Partición dentro / fuera de muestra (con embargo)
# -----------------------------------------------------------------------

@dataclass
class ResultadoParticionado:
    """Un mismo backtest partido en el tiempo en dentro y fuera de muestra."""

    fecha_corte: pd.Timestamp
    dentro: ResultadoBacktest
    fuera: ResultadoBacktest
    embargadas: list[Trade]


def _sub_resultado(trades: list[Trade], curva: pd.Series, params: ParametrosBacktest) -> ResultadoBacktest:
    capital_base = float(curva.iloc[0]) if len(curva) else params.capital_inicial
    params_tramo = replace(params, capital_inicial=capital_base)
    return ResultadoBacktest(
        trades=trades,
        curva_capital=curva,
        metricas=calcular_metricas(trades, curva, params_tramo),
        capital_inicial=capital_base,
        capital_final=float(curva.iloc[-1]) if len(curva) else capital_base,
    )


def particionar_resultado(
    resultado: ResultadoBacktest,
    params: ParametrosBacktest,
    fraccion_oos: float = 0.3,
    fecha_corte: str | pd.Timestamp | None = None,
) -> ResultadoParticionado:
    """Parte un backtest en dentro de muestra (antes del corte) y fuera.

    El corte es una fecha: la indicada, o la que deja `fraccion_oos` de las
    velas de la curva al final. Las operaciones que empiezan antes del corte
    y terminan después se EMBARGAN (no cuentan en ningún tramo), mismo
    criterio que `validacion/significancia.py`. Las métricas de cada tramo se
    calculan sobre su propia porción de curva, tomando como capital inicial
    el equity al empezar el tramo.

    Ojo: esto solo trocea un backtest ya hecho. Que un tramo cuente como
    "fuera de muestra" de verdad depende de que nadie lo haya mirado al
    ajustar; eso lo controla el protocolo de VALIDACION.md, no este código.
    """
    curva = resultado.curva_capital
    if fecha_corte is None:
        if not 0 < fraccion_oos < 1:
            raise ValueError("fraccion_oos debe estar entre 0 y 1.")
        corte = curva.index[int(len(curva) * (1 - fraccion_oos))]
    else:
        corte = pd.Timestamp(fecha_corte)
        if corte.tzinfo is None:
            corte = corte.tz_localize("UTC")

    dentro = [t for t in resultado.trades if t.fecha_salida < corte]
    fuera = [t for t in resultado.trades if t.fecha_entrada >= corte]
    usados = {id(t) for t in dentro} | {id(t) for t in fuera}
    embargadas = [t for t in resultado.trades if id(t) not in usados]

    return ResultadoParticionado(
        fecha_corte=corte,
        dentro=_sub_resultado(dentro, curva[curva.index < corte], params),
        fuera=_sub_resultado(fuera, curva[curva.index >= corte], params),
        embargadas=embargadas,
    )


# -----------------------------------------------------------------------
# Exportación para los scripts del Auditor (validacion/)
# -----------------------------------------------------------------------

COLUMNAS_CSV_OPERACIONES = [
    "fecha_entrada", "fecha_salida", "activo", "tipo", "precio_entrada", "precio_salida",
    "resultado_%", "motivo_salida", "comision", "slippage", "pnl_neto",
]


def exportar_operaciones_csv(trades: list[Trade], ruta: str | Path) -> Path:
    """CSV de operaciones con el formato de `validacion/significancia.py`.

    `resultado_%` es la rentabilidad de la operación sobre el capital de la
    cuenta en el momento de abrirla (pnl_neto / capital_antes), no la
    variación del precio: significancia.py compone esos porcentajes uno
    tras otro como una curva de capital. Las columnas extra (motivo,
    comisión, slippage, pnl) las ignora el script y sirven para auditar.
    """
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    formato = "%Y-%m-%d %H:%M:%S"
    with ruta.open("w", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        escritor.writerow(COLUMNAS_CSV_OPERACIONES)
        for t in sorted(trades, key=lambda t: t.fecha_entrada):
            escritor.writerow([
                t.fecha_entrada.strftime(formato),
                t.fecha_salida.strftime(formato),
                t.activo,
                "largo" if t.direccion == 1 else "corto",
                f"{t.precio_entrada:.8f}",
                f"{t.precio_salida:.8f}",
                f"{t.pnl_neto / t.capital_antes * 100:.6f}",
                t.motivo_salida,
                f"{t.comision_total:.6f}",
                f"{t.coste_slippage:.6f}",
                f"{t.pnl_neto:.6f}",
            ])
    return ruta


def exportar_rentabilidades_periodicas(
    curvas: dict[str, pd.Series], ruta: str | Path, frecuencia: str = "1D"
) -> Path:
    """CSV para `validacion/pbo.py`: una fila por periodo y una columna por
    variante, con la rentabilidad (%) de cada variante en ese periodo.

    Las curvas se remuestrean al cierre de cada periodo en un calendario
    común; los periodos sin dato se rellenan con 0 % (sin cambio de equity).
    """
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tabla = pd.DataFrame({nombre: c.resample(frecuencia).last() for nombre, c in curvas.items()})
    rentabilidades = (tabla.ffill().pct_change() * 100).iloc[1:].fillna(0.0)
    rentabilidades.index = rentabilidades.index.strftime("%Y-%m-%d")
    rentabilidades.index.name = "fecha"
    rentabilidades.round(6).to_csv(ruta, encoding="utf-8")
    return ruta


# -----------------------------------------------------------------------
# Reporte por consola
# -----------------------------------------------------------------------

def imprimir_reporte(resultado: ResultadoBacktest, titulo: str = "INFORME DE BACKTESTING — BOT-PREDICT",
                     divisa: str = "€") -> None:
    """Imprime un resumen formateado de los resultados del backtest."""
    m = resultado.metricas
    ancho = 60
    print("=" * ancho)
    print(f"  {titulo}")
    print("=" * ancho)
    if len(resultado.curva_capital):
        print(f"  Periodo:                    {resultado.curva_capital.index[0]:%Y-%m-%d} -> "
              f"{resultado.curva_capital.index[-1]:%Y-%m-%d}")
    print(f"  Capital inicial:            {m['capital_inicial']:,.2f} {divisa}")
    print(f"  Capital final:              {m['capital_final']:,.2f} {divisa}")
    print(f"  Rentabilidad neta:          {m['rentabilidad_neta_divisa']:,.2f} {divisa}  "
          f"({m['rentabilidad_neta_pct']:+.2f}%)")
    print(f"  Comisiones pagadas:         {m['comisiones_totales']:,.2f} {divisa}")
    print(f"  Coste de slippage:          {m['slippage_total']:,.2f} {divisa}")
    print("-" * ancho)
    print(f"  Max Drawdown:               {m['max_drawdown_pct']:.2f}%  "
          f"({m['max_drawdown_divisa']:,.2f} {divisa})")
    print(f"  Sharpe Ratio (anualizado):  {m['sharpe_ratio']:.2f}")
    print(f"  Sortino Ratio (anualizado): {m['sortino_ratio']:.2f}")
    print("-" * ancho)
    print(f"  Nº operaciones:             {m['num_trades']} "
          f"(largos: {m['num_trades_largos']}, cortos: {m['num_trades_cortos']}, "
          f"cerradas por fin de datos: {m['num_trades_fin_de_datos']})")
    print(f"  Win Rate:                   {m['win_rate_pct']:.2f}%")
    print(f"  Profit Factor:              {m['profit_factor']:.2f}")
    print(f"  Ratio ganancia/pérdida media: {m['ratio_payoff']:.2f}")
    if m["num_trades"] < 30:
        print(f"  AVISO: {m['num_trades']} operaciones son INSUFICIENTES para concluir nada.")
    print("=" * ancho)
    print("  Recuerda: sesgo de supervivencia, overfitting y slippage real")
    print("  pueden diferir de lo simulado aquí. Ver docstring del módulo.")
    print("=" * ancho)


def imprimir_reporte_particionado(particion: ResultadoParticionado, divisa: str = "€") -> None:
    """Imprime los dos tramos de `particionar_resultado` uno detrás de otro."""
    print(f"\nCorte dentro/fuera de muestra: {particion.fecha_corte}  |  "
          f"operaciones embargadas (a caballo del corte): {len(particion.embargadas)}")
    imprimir_reporte(particion.dentro, "DENTRO DE MUESTRA (ajuste)", divisa)
    imprimir_reporte(particion.fuera, "FUERA DE MUESTRA (validación)", divisa)


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

    df_senales = generar_senales(df_simulado, permitir_cortos=True, disparador_entrada="ruptura_donchian",
                                 usar_adx=False, usar_filtro_rsi=False)

    parametros = ParametrosBacktest(
        capital_inicial=10_000.0,
        riesgo_por_operacion=0.01,
        interes_compuesto=True,
        usar_take_profit=False,
    )  # Comisión y slippage: los valores reales por defecto (Kraken taker).
    motor = MotorBacktest(parametros)
    resultado = motor.ejecutar(df_senales)

    imprimir_reporte(resultado)
    ruta = graficar_equity_drawdown(resultado, "equity_drawdown_demo.png")
    print(f"\nGráfico guardado en: {ruta}")
