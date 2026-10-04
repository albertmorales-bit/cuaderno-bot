"""
=============================================================================
 BOT-PREDICT · MÓDULO 6: Herramientas de validación (Fase 4)
=============================================================================

- `ejecutar_ventana`: evalúa la estrategia en una ventana [inicio, fin)
  empezando SIN posición y con el capital entero el día `inicio`, igual que
  arrancará el paper trading. Los indicadores sí se calientan con la
  historia anterior a `inicio` (es información pasada, legítima). Nunca se
  cargan datos posteriores a `fin`.
- Benchmarks en la misma ventana y con los mismos costes: comprar y
  mantener al 100 %, comprar y mantener con la exposición media que tuvo la
  estrategia, y efectivo.
- Métricas diarias, bootstrap por bloques de esas métricas, probabilidad de
  que la estrategia tenga más Sharpe que un benchmark, y Sharpe deflactado
  (reutiliza `validacion/significancia.py`).
=============================================================================
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

import main
from modulo_4b_exposicion import MotorExposicion, ResultadoExposicion, benchmark_exposicion_constante

sys.path.insert(0, str(Path(__file__).resolve().parent / "validacion"))
import significancia  # noqa: E402


@dataclass
class ResultadoVentana:
    activo: str
    inicio: pd.Timestamp
    fin: pd.Timestamp
    estrategia: ResultadoExposicion
    comprar_mantener: ResultadoExposicion
    misma_exposicion: ResultadoExposicion


def _ts(fecha) -> pd.Timestamp:
    t = pd.Timestamp(fecha)
    return t.tz_localize("UTC") if t.tzinfo is None else t


def ejecutar_ventana(
    config: "main.Configuracion",
    activo: str,
    inicio: str,
    fin: str,
    capital: Optional[float] = None,
    datos: Optional[pd.DataFrame] = None,
) -> ResultadoVentana:
    """Estrategia V8 y benchmarks en [inicio, fin), arrancando sin posición."""
    inicio_ts, fin_ts = _ts(inicio), _ts(fin)
    if datos is None:
        datos = main.obtener_velas(replace(config, fecha_fin=fin), activo)
    datos = datos[datos.index < fin_ts]
    df = main.preparar_conjunto(config, datos)
    df["calentamiento_ok"] = df["calentamiento_ok"] & (df.index >= inicio_ts)
    if not df["calentamiento_ok"].any():
        raise ValueError(f"{activo}: la ventana {inicio}–{fin} no tiene velas operables.")
    params = main.parametros_exposicion(config, activo, capital)
    estrategia = MotorExposicion(params, activo).ejecutar(df)
    bh = benchmark_exposicion_constante(df, params, 1.0, activo)
    igual = benchmark_exposicion_constante(df, params, estrategia.metricas["exposicion_media"], activo)
    return ResultadoVentana(activo, inicio_ts, fin_ts, estrategia, bh, igual)


def sumar_curvas(curvas: list[pd.Series]) -> pd.Series:
    """Cartera de varias curvas independientes (cada una con su capital)."""
    indice = curvas[0].index
    for c in curvas[1:]:
        indice = indice.intersection(c.index)
    return sum(c.loc[indice] for c in curvas)


def metricas_diarias(curva: pd.Series, periodos_por_anio: int = 365) -> dict:
    r = curva.pct_change().dropna()
    anios = max((curva.index[-1] - curva.index[0]).days / 365.25, 1e-9)
    abajo = float(np.sqrt(np.mean(np.minimum(r.to_numpy(), 0) ** 2))) if len(r) else 0.0
    return {
        "rent_total_pct": (curva.iloc[-1] / curva.iloc[0] - 1) * 100,
        "cagr_pct": ((curva.iloc[-1] / curva.iloc[0]) ** (1 / anios) - 1) * 100,
        "vol_anual_pct": r.std() * np.sqrt(periodos_por_anio) * 100,
        "sharpe": r.mean() / r.std() * np.sqrt(periodos_por_anio) if r.std() > 0 else 0.0,
        "sortino": r.mean() / abajo * np.sqrt(periodos_por_anio) if abajo > 0 else 0.0,
        "max_dd_pct": ((curva / curva.cummax()) - 1).min() * 100,
    }


def _indices_bloques(n: int, longitud: int, rng: np.random.Generator) -> np.ndarray:
    inicios = rng.integers(0, n, int(np.ceil(n / longitud)))
    return ((inicios[:, None] + np.arange(longitud)[None, :]) % n).ravel()[:n]


def _sharpe(r: np.ndarray, periodos: int) -> float:
    s = r.std()
    return float(r.mean() / s * np.sqrt(periodos)) if s > 0 else 0.0


def _max_dd(r: np.ndarray) -> float:
    curva = np.cumprod(1 + r)
    return float((curva / np.maximum.accumulate(curva) - 1).min() * 100)


def bootstrap_metricas(
    retornos: pd.Series, n_remuestreos: int = 5000, bloque: int = 20, semilla: int = 12345,
    periodos_por_anio: int = 365, nivel: float = 0.90,
) -> dict:
    """Intervalos por bootstrap circular de bloques para Sharpe, CAGR y caída máxima."""
    r = retornos.dropna().to_numpy()
    rng = np.random.default_rng(semilla)
    sh, cagr, dd = np.empty(n_remuestreos), np.empty(n_remuestreos), np.empty(n_remuestreos)
    for b in range(n_remuestreos):
        m = r[_indices_bloques(len(r), bloque, rng)]
        sh[b] = _sharpe(m, periodos_por_anio)
        cagr[b] = (np.prod(1 + m) ** (periodos_por_anio / len(m)) - 1) * 100
        dd[b] = _max_dd(m)
    q = ((1 - nivel) / 2, 1 - (1 - nivel) / 2)
    return {
        "sharpe_ic": tuple(np.quantile(sh, q)),
        "cagr_ic_pct": tuple(np.quantile(cagr, q)),
        "max_dd_ic_pct": tuple(np.quantile(dd, q)),
        "prob_sharpe_positivo": float((sh > 0).mean()),
    }


def prob_sharpe_superior(
    ret_a: pd.Series, ret_b: pd.Series, n_remuestreos: int = 5000, bloque: int = 20,
    semilla: int = 12345, periodos_por_anio: int = 365,
) -> float:
    """P(Sharpe de A > Sharpe de B) por bootstrap EMPAREJADO (mismos días en
    las dos series en cada remuestreo, para conservar su correlación)."""
    tabla = pd.concat([ret_a, ret_b], axis=1).dropna().to_numpy()
    rng = np.random.default_rng(semilla)
    gana = 0
    for _ in range(n_remuestreos):
        m = tabla[_indices_bloques(len(tabla), bloque, rng)]
        gana += _sharpe(m[:, 0], periodos_por_anio) > _sharpe(m[:, 1], periodos_por_anio)
    return gana / n_remuestreos


def sharpe_deflactado(retornos: pd.Series, n_variantes: int, periodos_por_anio: int = 365) -> dict:
    """Sharpe deflactado (Bailey y López de Prado, 2014) sobre rentabilidades
    diarias, con la implementación de `validacion/significancia.py`.
    `dsr` es la probabilidad de que el Sharpe real sea mayor que el máximo
    esperado por azar tras probar `n_variantes`."""
    res = significancia.deflated_sharpe(list(retornos.dropna().to_numpy()), n_variantes=n_variantes)
    if res is None:
        return {"dsr": float("nan")}
    return {
        "dsr": res["dsr"],
        "sharpe_anual": res["sr_hat"] * np.sqrt(periodos_por_anio),
        "umbral_azar_anual": res["sr_star"] * np.sqrt(periodos_por_anio),
        "n_variantes": n_variantes,
        "dias": int(retornos.dropna().shape[0]),
    }


def actividad_esperada(resultados: list[ResultadoExposicion], dias: int = 90) -> dict:
    """Episodios (entradas nuevas) y órdenes esperadas en `dias`, a partir de
    las tasas históricas, con un intervalo de Poisson del 90 % aproximado."""
    años = sum((r.curva_capital.index[-1] - r.curva_capital.index[0]).days for r in resultados) / 365.25
    entradas = sum(len(r.episodios) for r in resultados)
    ordenes = sum(r.metricas["num_ordenes"] for r in resultados)
    factor = dias / 365.25 / años * len(resultados)   # por cartera de todos los activos

    def poisson(lam: float) -> tuple[int, int]:
        from math import exp, factorial
        acumulada, k, bajo = 0.0, 0, None
        while True:
            acumulada += exp(-lam) * lam ** k / factorial(k)
            if bajo is None and acumulada >= 0.05:
                bajo = k
            if acumulada >= 0.95:
                return bajo, k
            k += 1

    lam_e, lam_o = entradas * factor, ordenes * factor
    return {"entradas_esperadas": lam_e, "entradas_ic90": poisson(lam_e),
            "ordenes_esperadas": lam_o, "ordenes_ic90": poisson(lam_o)}
