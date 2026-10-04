"""
=============================================================================
 BOT-PREDICT · MÓDULO 4b: Motor por EXPOSICIÓN OBJETIVO (Fase 2)
=============================================================================

Complementa al motor por operaciones del Módulo 4. Aquí la estrategia no
dice "compra / vende", sino "qué fracción del capital debe estar invertida"
(columna `exposicion_objetivo`, entre 0 y 1, calculada al CIERRE de cada
vela). El motor la ejecuta en la APERTURA de la vela siguiente.

Reglas de ejecución (D-024):
1. Señal con vela cerrada, ejecución en la apertura siguiente.
2. Solo se reajusta si la exposición real a la apertura se separa del
   objetivo más que `banda_reajuste` (p. ej. 10 puntos). Con una comisión
   del 0,80 %, reajustar a diario se comería cualquier ventaja.
3. Entrar desde cero y salir a cero se ejecutan siempre, sin banda.
4. Comisión y slippage sobre el nocional negociado; compras limitadas por
   el efectivo disponible (sin apalancamiento); órdenes por debajo del
   mínimo del exchange se omiten (salvo cerrar la posición completa).
5. Cada orden simulada queda registrada (`Operacion`) con precio de
   referencia, precio efectivo, comisión y slippage: es la base del
   registro de transparencia de la Fase 5.

Un "episodio" va de exposición cero a exposición cero. Los episodios se
guardan como `Trade` del Módulo 4 para reutilizar métricas (Profit Factor,
Win Rate) y la exportación a `validacion/significancia.py`.
=============================================================================
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from modulo_4_backtesting import (
    COMISION_TAKER_KRAKEN,
    SLIPPAGE_PESIMISTA,
    ParametrosBacktest,
    Trade,
    calcular_metricas,
)

_DECIMALES_UNIDADES = 8   # Precisión de cantidad de Kraken vía ccxt (1e-8).


@dataclass
class ParametrosExposicion:
    capital_inicial: float = 10_000.0
    comision_pct: float = COMISION_TAKER_KRAKEN
    slippage_pct: float = SLIPPAGE_PESIMISTA
    banda_reajuste: float = 0.10
    tamano_minimo: float = 0.0
    periodos_por_anio: int = 365


@dataclass
class Operacion:
    """Una orden simulada."""

    fecha: pd.Timestamp
    lado: str                    # "compra" | "venta"
    unidades: float
    precio_referencia: float     # Apertura de la vela (antes de slippage).
    precio_efectivo: float
    comision: float
    coste_slippage: float
    exposicion_antes: float
    exposicion_objetivo: float
    motivo: str                  # "entrada" | "reajuste" | "salida" | "fin_de_datos"


@dataclass
class ResultadoExposicion:
    curva_capital: pd.Series
    exposicion: pd.Series        # Fracción invertida al cierre de cada vela.
    operaciones: list[Operacion]
    episodios: list[Trade]
    metricas: dict[str, float]
    capital_inicial: float
    capital_final: float


def _truncar(x: float) -> float:
    factor = 10 ** _DECIMALES_UNIDADES
    return math.floor(x * factor) / factor


class MotorExposicion:
    def __init__(self, params: ParametrosExposicion | None = None, activo: str = "") -> None:
        self.params = params or ParametrosExposicion()
        self._activo = activo

    def ejecutar(self, df: pd.DataFrame) -> ResultadoExposicion:
        p = self.params
        faltan = {"Open", "Close", "exposicion_objetivo", "calentamiento_ok"} - set(df.columns)
        if faltan:
            raise ValueError(f"Faltan columnas: {sorted(faltan)}")
        df = df[df["calentamiento_ok"].astype(bool)]
        if len(df) < 2:
            raise ValueError("No hay velas suficientes tras el calentamiento.")
        objetivo = df["exposicion_objetivo"].to_numpy(dtype=float)
        if np.nanmin(objetivo) < 0 or np.nanmax(objetivo) > 1:
            raise ValueError("exposicion_objetivo debe estar entre 0 y 1 (solo largos, sin apalancamiento).")
        apertura = df["Open"].to_numpy(dtype=float)
        cierre = df["Close"].to_numpy(dtype=float)
        indices = df.index

        efectivo, unidades = p.capital_inicial, 0.0
        operaciones: list[Operacion] = []
        episodios: list[Trade] = []
        episodio: dict | None = None
        equity = np.empty(len(df))
        exposicion = np.empty(len(df))

        for i in range(len(df)):
            if i > 0:
                w_obj = float(objetivo[i - 1])
                equity_apertura = efectivo + unidades * apertura[i]
                w_actual = unidades * apertura[i] / equity_apertura if equity_apertura > 0 else 0.0
                if unidades > 0 and w_obj == 0:
                    motivo = "salida"
                elif unidades == 0 and w_obj > 0:
                    motivo = "entrada"
                elif unidades > 0 and abs(w_obj - w_actual) > p.banda_reajuste:
                    motivo = "reajuste"
                else:
                    motivo = ""
                if motivo:
                    if motivo == "entrada":
                        episodio = {"fecha": indices[i], "capital_antes": equity_apertura,
                                    "compras": 0.0, "unidades_compradas": 0.0, "ventas": 0.0,
                                    "unidades_vendidas": 0.0, "comision": 0.0, "slippage": 0.0,
                                    "max_unidades": 0.0}
                    efectivo, unidades = self._operar(
                        indices[i], apertura[i], w_obj, w_actual, equity_apertura,
                        efectivo, unidades, motivo, operaciones, episodio,
                    )
                    if episodio is not None and unidades == 0:
                        episodios.append(self._cerrar_episodio(episodio, indices[i], efectivo, "senal"))
                        episodio = None

            equity[i] = efectivo + unidades * cierre[i]
            exposicion[i] = unidades * cierre[i] / equity[i] if equity[i] > 0 else 0.0

        if unidades > 0:   # Cierre forzoso al final de los datos, al cierre de la última vela.
            equity_final = efectivo + unidades * cierre[-1]
            efectivo, unidades = self._operar(
                indices[-1], cierre[-1], 0.0, exposicion[-1], equity_final,
                efectivo, unidades, "fin_de_datos", operaciones, episodio,
            )
            episodios.append(self._cerrar_episodio(episodio, indices[-1], efectivo, "fin_de_datos"))
            equity[-1], exposicion[-1] = efectivo, 0.0

        curva = pd.Series(equity, index=indices, name="equity")
        serie_exposicion = pd.Series(exposicion, index=indices, name="exposicion")
        metricas = calcular_metricas(
            episodios, curva, ParametrosBacktest(capital_inicial=p.capital_inicial, periodos_por_anio=p.periodos_por_anio)
        )
        anios = max((indices[-1] - indices[0]).days / 365.25, 1e-9)
        nocional = sum(o.unidades * o.precio_efectivo for o in operaciones)
        metricas.update({
            "exposicion_media": float(serie_exposicion.mean()),
            "tiempo_invertido_pct": float((serie_exposicion > 0).mean() * 100),
            "num_ordenes": len(operaciones),
            "comisiones_totales": float(sum(o.comision for o in operaciones)),
            "slippage_total": float(sum(o.coste_slippage for o in operaciones)),
            "rotacion_anual": float(nocional / curva.mean() / anios),
        })
        return ResultadoExposicion(curva, serie_exposicion, operaciones, episodios, metricas,
                                   p.capital_inicial, float(curva.iloc[-1]))

    def _operar(self, fecha, precio, w_obj, w_actual, equity_ref, efectivo, unidades, motivo,
                operaciones, episodio):
        """Lleva la posición a `w_obj` del equity de referencia al `precio` dado."""
        p = self.params
        deseadas = w_obj * equity_ref / precio
        if deseadas > unidades:   # compra
            efectivo_unitario = precio * (1 + p.slippage_pct) * (1 + p.comision_pct)
            cantidad = _truncar(min(deseadas - unidades, efectivo / efectivo_unitario))
            if cantidad <= 0 or cantidad < p.tamano_minimo:
                return efectivo, unidades
            precio_efectivo = precio * (1 + p.slippage_pct)
            comision = cantidad * precio_efectivo * p.comision_pct
            efectivo -= cantidad * precio_efectivo + comision
            unidades += cantidad
            lado = "compra"
        else:   # venta
            cantidad = unidades if w_obj == 0 else _truncar(unidades - deseadas)
            if cantidad <= 0 or (w_obj > 0 and cantidad < p.tamano_minimo):
                return efectivo, unidades
            precio_efectivo = precio * (1 - p.slippage_pct)
            comision = cantidad * precio_efectivo * p.comision_pct
            efectivo += cantidad * precio_efectivo - comision
            unidades = 0.0 if w_obj == 0 else unidades - cantidad
            lado = "venta"
        slippage = cantidad * abs(precio_efectivo - precio)
        operaciones.append(Operacion(fecha, lado, cantidad, precio, precio_efectivo, comision, slippage,
                                     w_actual, w_obj, motivo))
        if episodio is not None:
            clave = "compras" if lado == "compra" else "ventas"
            episodio[clave] += cantidad * precio_efectivo
            episodio["unidades_compradas" if lado == "compra" else "unidades_vendidas"] += cantidad
            episodio["comision"] += comision
            episodio["slippage"] += slippage
            episodio["max_unidades"] = max(episodio["max_unidades"], unidades)
        return efectivo, unidades

    def _cerrar_episodio(self, e: dict, fecha_salida, efectivo_final, motivo) -> Trade:
        pnl_neto = efectivo_final - e["capital_antes"]
        return Trade(
            fecha_entrada=e["fecha"],
            fecha_salida=fecha_salida,
            direccion=1,
            precio_entrada=e["compras"] / e["unidades_compradas"],
            precio_salida=e["ventas"] / e["unidades_vendidas"],
            unidades=e["max_unidades"],
            motivo_salida=motivo,
            comision_total=e["comision"],
            pnl_bruto=pnl_neto + e["comision"],
            pnl_neto=pnl_neto,
            capital_antes=e["capital_antes"],
            capital_despues=efectivo_final,
            activo=self._activo,
            coste_slippage=e["slippage"],
        )


def benchmark_exposicion_constante(
    df: pd.DataFrame, params: ParametrosExposicion, exposicion: float, activo: str = ""
) -> ResultadoExposicion:
    """Comprar y mantener con una fracción constante (1.0 = todo invertido),
    con los MISMOS costes, banda y calendario que la estrategia."""
    base = df[["Open", "High", "Low", "Close", "calentamiento_ok"]].copy()
    base["exposicion_objetivo"] = float(exposicion)
    return MotorExposicion(params, activo).ejecutar(base)
