"""
=============================================================================
 BOT-PREDICT · MÓDULO 5: Clasificación de regímenes de mercado (Fase 2)
=============================================================================

Reglas simples y transparentes (D-025), calculadas con información
disponible al CIERRE de cada vela y sin mirar nunca hacia delante:

- Volatilidad: desviación típica de 30 días de las rentabilidades
  logarítmicas, anualizada, y su PERCENTIL respecto a toda la historia
  ANTERIOR (ventana expansiva). Terciles: baja / media / alta. Un percentil
  calculado con toda la muestra usaría el futuro y está prohibido.
- Tendencia: cierre frente a la SMA de 200 días y pendiente de esa SMA en
  20 días. alcista = por encima y subiendo; bajista = por debajo y bajando;
  mixto = el resto.
- Fuerza: ratio de eficiencia de Kaufman a 50 días
  (|C_t - C_{t-50}| / suma de |variaciones diarias|), en percentil
  expansivo. fuerte = por encima de la mediana histórica previa.

`atribuir_por_regimen` asigna la rentabilidad del día t al régimen conocido
al cierre de t-1, que es cuando se decidió la posición de ese día.
=============================================================================
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

SIN_DATOS = "sin_datos"
DIMENSIONES = ("regimen_tendencia", "regimen_volatilidad", "regimen_fuerza")


@dataclass(frozen=True)
class ParametrosRegimen:
    ventana_volatilidad: int = 30
    periodo_media: int = 200
    ventana_pendiente: int = 20
    ventana_eficiencia: int = 50
    min_historia_percentil: int = 300
    periodos_por_anio: int = 365


def percentil_expansivo(serie: pd.Series, min_obs: int) -> pd.Series:
    """Percentil de cada valor dentro de su propia historia hasta ese día
    (inclusive). Solo usa el pasado: añadir datos futuros no lo cambia."""
    return serie.expanding(min_periods=min_obs).rank(pct=True)


def clasificar_regimenes(df: pd.DataFrame, p: ParametrosRegimen = ParametrosRegimen()) -> pd.DataFrame:
    """Devuelve un DataFrame con los indicadores y las tres etiquetas de régimen."""
    cierre = df["Close"]
    r = pd.DataFrame(index=df.index)

    log_ret = np.log(cierre).diff()
    r["volatilidad"] = log_ret.rolling(p.ventana_volatilidad, min_periods=p.ventana_volatilidad).std() \
        * np.sqrt(p.periodos_por_anio)
    r["percentil_volatilidad"] = percentil_expansivo(r["volatilidad"], p.min_historia_percentil)
    r["regimen_volatilidad"] = np.select(
        [r["percentil_volatilidad"] <= 1 / 3, r["percentil_volatilidad"] <= 2 / 3, r["percentil_volatilidad"] > 2 / 3],
        ["baja", "media", "alta"], default=SIN_DATOS,
    )

    r["sma"] = cierre.rolling(p.periodo_media, min_periods=p.periodo_media).mean()
    r["pendiente_sma"] = r["sma"] / r["sma"].shift(p.ventana_pendiente) - 1
    alcista = (cierre > r["sma"]) & (r["pendiente_sma"] > 0)
    bajista = (cierre < r["sma"]) & (r["pendiente_sma"] < 0)
    r["regimen_tendencia"] = np.select(
        [r["pendiente_sma"].isna(), alcista, bajista], [SIN_DATOS, "alcista", "bajista"], default="mixto"
    )

    camino = cierre.diff().abs().rolling(p.ventana_eficiencia, min_periods=p.ventana_eficiencia).sum()
    r["eficiencia"] = (cierre - cierre.shift(p.ventana_eficiencia)).abs() / camino
    r["percentil_eficiencia"] = percentil_expansivo(r["eficiencia"], p.min_historia_percentil)
    r["regimen_fuerza"] = np.select(
        [r["percentil_eficiencia"].isna(), r["percentil_eficiencia"] > 0.5], [SIN_DATOS, "fuerte"], default="debil"
    )
    return r


def atribuir_por_regimen(retornos: pd.Series, regimen: pd.Series) -> pd.DataFrame:
    """Empareja la rentabilidad del día t con el régimen al cierre de t-1."""
    tabla = pd.DataFrame({"retorno": retornos, "regimen": regimen.shift(1)}).dropna()
    return tabla[tabla["regimen"] != SIN_DATOS]


def resumen_por_regimen(
    ret_estrategia: pd.Series,
    ret_comprar_mantener: pd.Series,
    exposicion: pd.Series,
    regimen: pd.Series,
    periodos_por_anio: int = 365,
) -> pd.DataFrame:
    """Tabla por régimen: días, exposición media y rentabilidad / Sharpe
    anualizados de la estrategia y de comprar y mantener."""
    datos = pd.DataFrame({
        "estrategia": ret_estrategia,
        "comprar_mantener": ret_comprar_mantener,
        "exposicion": exposicion.shift(1),   # exposición durante el día = la del cierre previo
        "regimen": regimen.shift(1),
    }).dropna()
    datos = datos[datos["regimen"] != SIN_DATOS]
    filas = []
    for nombre, g in datos.groupby("regimen"):
        fila = {"regimen": nombre, "dias": len(g), "pct_dias": len(g) / len(datos) * 100,
                "exposicion_media": g["exposicion"].mean()}
        for col in ("estrategia", "comprar_mantener"):
            media, desv = g[col].mean(), g[col].std()
            fila[f"{col}_rent_anual_pct"] = media * periodos_por_anio * 100
            fila[f"{col}_sharpe"] = media / desv * np.sqrt(periodos_por_anio) if desv > 0 else 0.0
        filas.append(fila)
    return pd.DataFrame(filas).set_index("regimen")


def bootstrap_por_bloques(
    retornos: np.ndarray,
    etiquetas: np.ndarray,
    estadistico,
    n_remuestreos: int = 5000,
    longitud_bloque: int = 20,
    semilla: int = 12345,
) -> np.ndarray:
    """Bootstrap circular por bloques sobre pares (retorno, régimen).

    Remuestrea bloques contiguos de días, conservando la autocorrelación de
    las rentabilidades y la persistencia de los regímenes. `estadistico`
    recibe (retornos, etiquetas) remuestreados y devuelve un número.
    Semilla fija: resultados reproducibles.
    """
    rng = np.random.default_rng(semilla)
    n = len(retornos)
    n_bloques = int(np.ceil(n / longitud_bloque))
    salida = np.empty(n_remuestreos)
    desplazamiento = np.arange(longitud_bloque)
    for b in range(n_remuestreos):
        inicios = rng.integers(0, n, n_bloques)
        idx = ((inicios[:, None] + desplazamiento[None, :]) % n).ravel()[:n]
        salida[b] = estadistico(retornos[idx], etiquetas[idx])
    return salida


def media_anual_en(etiqueta: str, periodos_por_anio: int = 365):
    """Estadístico: rentabilidad media anualizada en los días con `etiqueta`."""
    def f(ret: np.ndarray, etq: np.ndarray) -> float:
        sel = ret[etq == etiqueta]
        return float(sel.mean() * periodos_por_anio) if len(sel) else np.nan
    return f


def diferencia_anual(a: str, b: str, periodos_por_anio: int = 365):
    """Estadístico: media anualizada en régimen `a` menos en régimen `b`."""
    fa, fb = media_anual_en(a, periodos_por_anio), media_anual_en(b, periodos_por_anio)
    return lambda ret, etq: fa(ret, etq) - fb(ret, etq)
