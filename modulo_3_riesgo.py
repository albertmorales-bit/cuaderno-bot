"""
=============================================================================
 BOT-PREDICT · MÓDULO 3: Dimensionamiento de posición y gestión de riesgo
=============================================================================

Objetivo del módulo
--------------------
Convertir una señal de entrada (precio, dirección, ATR del momento) en un
plan de operación completo y cuantificado: precio de stop-loss, precio de
take-profit, y el TAMAÑO de la posición — la pieza que, en la práctica,
protege más el capital que la propia señal de entrada.

Position sizing por riesgo fijo vs. tamaño de lote constante
----------------------------------------------------------------
El error más común de un trader novato es operar con un tamaño FIJO de
posición (p. ej. "siempre compro 100 acciones" o "siempre 0.1 BTC"),
independientemente de dónde esté el stop-loss. Esto hace que el riesgo
monetario real varíe sin control operación a operación: si el stop está
cerca, arriesgas poco; si está lejos (activo más volátil, stop más ancho),
arriesgas mucho más sin haberlo decidido conscientemente.

El "position sizing por riesgo fijo" invierte el problema: en vez de fijar
el tamaño y dejar que el riesgo flote, fijamos el RIESGO (un % constante
del capital, la regla del 1-2%) y dejamos que el TAMAÑO se ajuste:

                        Capital × Riesgo%
    Tamaño (unidades) = ------------------
                        Distancia al Stop

Así, tanto si el stop está a $500 como a $2.000 de la entrada, la pérdida
máxima en caso de que salte el stop es siempre la misma cantidad de dinero
(en términos relativos al capital). Es la diferencia entre "decidir cuánto
puedo perder" y "descubrir cuánto perdiste después de perderlo".

Por qué el ATR es superior a un stop de % fijo
----------------------------------------------
Un stop de porcentaje fijo (p. ej. "siempre -3%") ignora que no todos los
activos ni todos los momentos de mercado tienen la misma volatilidad. Un
-3% en un activo de baja volatilidad puede ser un stop absurdamente ancho
(nunca te saca aunque la tesis haya fallado); ese mismo -3% en un activo
muy volátil puede saltar por simple ruido normal de mercado, sin que la
tendencia se haya invalidado realmente. El ATR resuelve esto porque mide
la volatilidad REAL y RECIENTE de ESE activo en ESE momento: el stop se
adapta activo a activo y periodo a periodo, en vez de aplicar la misma
regla arbitraria a todo. Es el mismo principio que ya usamos en el
Módulo 2 para diferenciar el stop de largos y cortos, llevado ahora al
dimensionamiento de la posición completa.
=============================================================================
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

logger = logging.getLogger("bot_predict.riesgo")

_EPSILON = 1e-8  # Umbral por debajo del cual consideramos una distancia "cero".


@dataclass
class ResultadoGestionRiesgo:
    """Plan de operación completo devuelto por `calcular_gestion_riesgo`.

    Reunir todos los resultados en un único objeto (en vez de devolver una
    tupla suelta de 6 valores) hace el código que lo consume más legible
    (`plan.precio_stop_loss` en vez de recordar que es el segundo elemento
    de una tupla) y más fácil de extender sin romper firmas de función.
    """

    direccion: int
    precio_entrada: float
    distancia_stop: float
    precio_stop_loss: float
    precio_take_profit: float
    distancia_take_profit: float
    tamano_posicion: float
    capital_arriesgado: float
    capital_invertido: float
    perdida_maxima_teorica: float
    advertencias: list[str] = field(default_factory=list)


def calcular_gestion_riesgo(
    precio_entrada: float,
    atr: float,
    direccion: int,
    capital_cuenta: float = 10_000.0,
    riesgo_por_operacion: float = 0.01,
    atr_mult_stop_largo: float = 2.0,
    atr_mult_stop_corto: float = 1.5,
    ratio_riesgo_beneficio: float = 2.0,
    decimales_unidades: int = 6,
    unidades_fraccionables: bool = True,
    permitir_apalancamiento: bool = False,
    comision_pct: float = 0.0,
    tamano_minimo: float = 0.0,
) -> ResultadoGestionRiesgo:
    """Calcula stop-loss, take-profit y tamaño de posición para una señal.

    Parameters
    ----------
    precio_entrada : float
        Precio al que se abriría la posición.
    atr : float
        Average True Range vigente en el momento de la entrada (mismo
        ATR calculado en el Módulo 2).
    direccion : int
        1 = posición larga, -1 = posición corta.
    capital_cuenta : float
        Capital total disponible en la cuenta. Argumento configurable por
        llamada (nunca hardcoded), para poder simular distintos tamaños de
        cuenta en el backtest del Módulo 4.
    riesgo_por_operacion : float
        Fracción del capital que se está dispuesto a perder si el stop-loss
        salta (regla del 1-2%: 0.01 = 1%, 0.02 = 2%). También configurable
        por llamada.
    atr_mult_stop_largo, atr_mult_stop_corto : float
        Multiplicadores de ATR para la distancia del stop, asimétricos por
        el riesgo direccional distinto entre largos y cortos (ver Módulo 2).
    ratio_riesgo_beneficio : float
        Múltiplo de la distancia del stop que define la distancia del
        take-profit. Por defecto 2.0 -> ratio R:R de 1:2.
    decimales_unidades : int
        Precisión de redondeo del tamaño de posición cuando
        `unidades_fraccionables=True` (p. ej. cripto, 6 decimales típico).
    unidades_fraccionables : bool
        True (por defecto) para activos que admiten fracciones (cripto).
        False para redondear HACIA ABAJO a unidades enteras (acciones al
        contado, donde no existen fracciones de acción en la mayoría de
        brokers) — se redondea siempre hacia abajo, nunca hacia arriba,
        para no superar el riesgo objetivo.
    permitir_apalancamiento : bool
        Si False (por defecto), el tamaño de posición se limita para que
        el capital invertido (tamaño × precio) nunca supere el capital de
        la cuenta -> comportamiento "spot", sin apalancamiento. Si esto
        recorta el tamaño calculado por riesgo, se añade una advertencia:
        significa que el stop está tan cerca del precio que el sizing por
        riesgo puro pediría más exposición de la que el capital permite.
    comision_pct : float
        Comisión de entrada (fracción del nocional). Se usa en el tope sin
        apalancamiento: nocional + comisión no puede superar el capital
        (auditoría Fase 0). 0 por defecto (compatibilidad).
    tamano_minimo : float
        Tamaño mínimo de orden del exchange en unidades del activo (p. ej.
        0.00005 BTC en Kraken). Por debajo, la operación se descarta.

    Returns
    -------
    ResultadoGestionRiesgo
        Objeto con el plan de operación completo. Revisa siempre el campo
        `advertencias` antes de operar con el resultado.
    """
    if direccion not in (1, -1):
        raise ValueError("direccion debe ser 1 (largo) o -1 (corto).")
    if precio_entrada <= 0:
        raise ValueError("precio_entrada debe ser positivo.")
    if not 0 < riesgo_por_operacion < 1:
        raise ValueError("riesgo_por_operacion debe estar entre 0 y 1 (p. ej. 0.01).")

    advertencias: list[str] = []

    # 1) Distancia del stop, con el multiplicador asimétrico según dirección.
    multiplicador_stop = atr_mult_stop_largo if direccion == 1 else atr_mult_stop_corto
    distancia_stop = atr * multiplicador_stop

    # 2) Guarda defensiva: ATR nulo/insignificante -> no se puede dimensionar
    #    con seguridad (dividir por ~0 dispararía un tamaño de posición
    #    absurdamente grande). En vez de lanzar una excepción que tumbe un
    #    backtest completo, devolvemos un plan con tamaño 0 y lo advertimos.
    if distancia_stop < _EPSILON:
        logger.warning(
            "ATR/distancia de stop insignificante (%.10f) para precio_entrada=%.4f; "
            "no se puede dimensionar la posición de forma segura.",
            distancia_stop, precio_entrada,
        )
        return ResultadoGestionRiesgo(
            direccion=direccion,
            precio_entrada=precio_entrada,
            distancia_stop=distancia_stop,
            precio_stop_loss=precio_entrada,
            precio_take_profit=precio_entrada,
            distancia_take_profit=0.0,
            tamano_posicion=0.0,
            capital_arriesgado=0.0,
            capital_invertido=0.0,
            perdida_maxima_teorica=0.0,
            advertencias=["ATR/distancia de stop insignificante: posición descartada (tamaño 0)."],
        )

    # 3) Precios de stop-loss y take-profit según dirección.
    distancia_take_profit = distancia_stop * ratio_riesgo_beneficio
    if direccion == 1:  # Largo: stop debajo, take-profit encima.
        precio_stop_loss = precio_entrada - distancia_stop
        precio_take_profit = precio_entrada + distancia_take_profit
    else:  # Corto: stop encima, take-profit debajo.
        precio_stop_loss = precio_entrada + distancia_stop
        precio_take_profit = precio_entrada - distancia_take_profit

    # 4) Dimensionamiento por riesgo fijo: la fórmula central del módulo.
    capital_arriesgado = capital_cuenta * riesgo_por_operacion
    tamano_posicion = capital_arriesgado / distancia_stop

    # 5) Redondeo a unidades operativas válidas.
    if unidades_fraccionables:
        # Hacia abajo (no round): redondear hacia arriba superaría el riesgo objetivo.
        factor = 10 ** decimales_unidades
        tamano_posicion = math.floor(tamano_posicion * factor) / factor
    else:
        # floor (no round) para no superar nunca el riesgo objetivo.
        tamano_posicion = math.floor(tamano_posicion)

    # 6) Control de límites: sin apalancamiento, el nocional invertido no
    #    puede superar el capital disponible (comportamiento "spot").
    capital_invertido = tamano_posicion * precio_entrada
    if not permitir_apalancamiento and capital_invertido * (1 + comision_pct) > capital_cuenta:
        tamano_maximo_por_capital = capital_cuenta / (precio_entrada * (1 + comision_pct))
        tamano_posicion = (
            math.floor(tamano_maximo_por_capital * 10 ** decimales_unidades) / 10 ** decimales_unidades
            if unidades_fraccionables
            else math.floor(tamano_maximo_por_capital)
        )
        capital_invertido = tamano_posicion * precio_entrada
        advertencias.append(
            "El tamaño de posición por riesgo puro superaba el capital disponible "
            "(implicaría apalancamiento); se ha recortado al máximo sin apalancar. "
            "La pérdida máxima real es ahora menor que el riesgo objetivo."
        )

    # 7) Pérdida máxima teórica real (puede ser menor que capital_arriesgado
    #    si el paso 6 recortó el tamaño).
    perdida_maxima_teorica = tamano_posicion * distancia_stop

    if 0 < tamano_posicion < tamano_minimo:
        advertencias.append(
            f"El tamaño {tamano_posicion} es menor que el mínimo de orden del exchange "
            f"({tamano_minimo}); posición descartada."
        )
        tamano_posicion = 0.0
        capital_invertido = 0.0
        perdida_maxima_teorica = 0.0

    if tamano_posicion <= 0:
        advertencias.append(
            "El tamaño de posición resultante es 0 (redondeo a unidades enteras "
            "o capital insuficiente para el precio de entrada dado)."
        )

    return ResultadoGestionRiesgo(
        direccion=direccion,
        precio_entrada=precio_entrada,
        distancia_stop=distancia_stop,
        precio_stop_loss=precio_stop_loss,
        precio_take_profit=precio_take_profit,
        distancia_take_profit=distancia_take_profit,
        tamano_posicion=tamano_posicion,
        capital_arriesgado=capital_arriesgado,
        capital_invertido=capital_invertido,
        perdida_maxima_teorica=perdida_maxima_teorica,
        advertencias=advertencias,
    )


def escala_por_volatilidad(
    cierre: "pd.Series",
    objetivo_anual: float = 0.40,
    ventana: int = 30,
    periodos_por_anio: int = 365,
    tope: float = 1.0,
) -> "pd.Series":
    """Fracción del capital a exponer para que la posición tenga, en
    promedio, una volatilidad anual cercana a `objetivo_anual` (Fase 2, D-023).

        escala_t = min(tope, objetivo_anual / vol_realizada_t)

    `vol_realizada_t` es la desviación típica de las rentabilidades
    logarítmicas diarias de las `ventana` velas hasta el CIERRE de `t`
    inclusive, anualizada. Solo usa información conocida al cierre de `t`;
    el motor la aplica en la apertura de `t+1`. `tope=1.0` = sin
    apalancamiento: solo puede reducir la exposición, nunca ampliarla.
    """
    import numpy as np  # import local: el resto del módulo no depende de numpy

    vol = np.log(cierre).diff().rolling(ventana, min_periods=ventana).std() * np.sqrt(periodos_por_anio)
    return (objetivo_anual / vol).clip(upper=tope).fillna(0.0)


def _imprimir_plan(etiqueta: str, plan: ResultadoGestionRiesgo) -> None:
    """Utilidad de presentación para el bloque de validación numérica."""
    print(f"\n--- {etiqueta} ---")
    print(f"Dirección:                {'LARGO' if plan.direccion == 1 else 'CORTO'}")
    print(f"Precio de entrada:        ${plan.precio_entrada:,.2f}")
    print(f"Distancia al stop:        ${plan.distancia_stop:,.2f}")
    print(f"Precio Stop-Loss:         ${plan.precio_stop_loss:,.2f}")
    print(f"Precio Take-Profit:       ${plan.precio_take_profit:,.2f}")
    print(f"Tamaño de posición:       {plan.tamano_posicion} unidades")
    print(f"Capital invertido:        ${plan.capital_invertido:,.2f}")
    print(f"Capital arriesgado (obj): ${plan.capital_arriesgado:,.2f}")
    print(f"Pérdida máxima real:      ${plan.perdida_maxima_teorica:,.2f}")
    if plan.advertencias:
        for adv in plan.advertencias:
            print(f"⚠ Advertencia: {adv}")


# =============================================================================
# Bloque de validación numérica con el ejemplo solicitado:
# Entrada $50,000, ATR $1,200, cuenta $10,000, riesgo 1%.
# =============================================================================
if __name__ == "__main__":
    PRECIO_ENTRADA = 50_000.0
    ATR = 1_200.0
    CAPITAL = 10_000.0
    RIESGO = 0.01  # 1%

    plan_largo = calcular_gestion_riesgo(
        precio_entrada=PRECIO_ENTRADA,
        atr=ATR,
        direccion=1,
        capital_cuenta=CAPITAL,
        riesgo_por_operacion=RIESGO,
    )
    _imprimir_plan("LARGO — BTC/USDT @ $50,000, ATR $1,200", plan_largo)

    # Mismo escenario en corto, para comprobar visualmente el efecto del
    # multiplicador de stop asimétrico (1.5x en vez de 2.0x -> stop más
    # ceñido, posición algo mayor a igualdad de riesgo objetivo).
    plan_corto = calcular_gestion_riesgo(
        precio_entrada=PRECIO_ENTRADA,
        atr=ATR,
        direccion=-1,
        capital_cuenta=CAPITAL,
        riesgo_por_operacion=RIESGO,
    )
    _imprimir_plan("CORTO — BTC/USDT @ $50,000, ATR $1,200", plan_corto)
