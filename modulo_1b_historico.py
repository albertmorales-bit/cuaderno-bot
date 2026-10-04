"""
=============================================================================
 BOT-PREDICT · MÓDULO 1b: Histórico largo versionado (Fase 1)
=============================================================================

Por qué existe
--------------
La API pública de Kraken (el exchange donde corre el paper trading) solo
sirve las 720 velas más recientes. Para hablar de épocas de mercado hace
falta historia desde 2014-15, que hay que reunir de OTRAS fuentes,
comprobar y congelar en disco para que cualquier backtest sea reproducible.

Qué hace
--------
1. Descarga la misma serie (p. ej. BTC/EUR diario) de varias fuentes
   públicas, reutilizando `ProveedorDatos` del Módulo 1.
2. Diagnostica cada fuente: huecos, OHLC incoherente, volumen cero,
   movimientos extremos.
3. Compara las fuentes día a día (diferencia relativa de cierres).
4. Construye la serie limpia a partir de una fuente principal. NO rellena
   ni corrige nada en silencio: cada fila lleva la columna `fuente`, y
   cualquier sustitución queda registrada en el manifiesto.
5. Guarda en `datos/<version>/` los CSV crudos de cada fuente, la serie
   limpia y un `MANIFIESTO.json` con el SHA-256 de cada archivo.
   `cargar_historico()` verifica el checksum antes de devolver nada.

Las marcas de tiempo son de APERTURA de vela en UTC (convención de ccxt y
de yfinance para cripto en diario).
=============================================================================
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from modulo_1_datos import ESQUEMA_OHLCV, ParametrosDescarga, ProveedorDatos, TipoActivo, duracion_intervalo

logger = logging.getLogger("bot_predict.historico")

RAIZ_DATOS = Path(__file__).resolve().parent / "datos"
FORMATO_FECHA = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(frozen=True)
class Fuente:
    """Una fuente pública de velas. `simbolo` en el formato de esa fuente."""

    nombre: str             # Identificador corto, p. ej. "coinbase".
    proveedor: str          # Id de ccxt, o "yfinance".
    simbolo: str            # "BTC/EUR" en ccxt, "BTC-EUR" en yfinance.

    @property
    def es_yfinance(self) -> bool:
        return self.proveedor == "yfinance"


# Fuentes de la Fase 1 (sondeadas el 2026-10-04, ver DECISIONES.md D-016).
FUENTES: dict[str, list[Fuente]] = {
    "BTC/EUR": [
        Fuente("coinbase", "coinbaseexchange", "BTC/EUR"),
        Fuente("bitstamp", "bitstamp", "BTC/EUR"),
        Fuente("yfinance", "yfinance", "BTC-EUR"),
        Fuente("kraken", "kraken", "BTC/EUR"),
    ],
    "ETH/EUR": [
        Fuente("coinbase", "coinbaseexchange", "ETH/EUR"),
        Fuente("bitstamp", "bitstamp", "ETH/EUR"),
        Fuente("yfinance", "yfinance", "ETH-EUR"),
        Fuente("kraken", "kraken", "ETH/EUR"),
    ],
}


# =============================================================================
# Descarga
# =============================================================================

def descargar_fuente(
    fuente: Fuente, fecha_inicio: str, fecha_fin: str, intervalo: str = "1d"
) -> pd.DataFrame:
    """Velas cerradas de una fuente entre dos fechas (fin exclusiva)."""
    tipo = TipoActivo.ACCION if fuente.es_yfinance else TipoActivo.CRIPTO
    # Para yfinance el exchange de ccxt no se usa; se pasa uno cualquiera.
    proveedor = ProveedorDatos(exchange_id="kraken" if fuente.es_yfinance else fuente.proveedor)
    df = proveedor.obtener_datos(
        ParametrosDescarga(
            ticker=fuente.simbolo,
            tipo=tipo,
            intervalo=intervalo,
            exchange_id=fuente.proveedor,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
        )
    )
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df[ESQUEMA_OHLCV]


# =============================================================================
# Diagnóstico de calidad
# =============================================================================

def diagnosticar_calidad(df: pd.DataFrame, intervalo: str = "1d", umbral_movimiento: float = 0.25) -> dict:
    """Controles de calidad de una serie OHLCV. No modifica nada.

    - huecos: velas que faltan en la rejilla regular del intervalo.
    - ohlc_incoherente: High < max(Open, Close), Low > min(Open, Close) o
      High < Low.
    - volumen_cero: velas sin negociación (precio probablemente arrastrado).
    - movimientos_extremos: |rentabilidad logarítmica de cierre| > umbral.
    """
    paso = duracion_intervalo(intervalo)
    rejilla = pd.date_range(df.index.min(), df.index.max(), freq=paso)
    faltan = rejilla.difference(df.index)
    incoherente = (
        (df["High"] < df[["Open", "Close"]].max(axis=1))
        | (df["Low"] > df[["Open", "Close"]].min(axis=1))
        | (df["High"] < df["Low"])
    )
    log_ret = np.log(df["Close"]).diff()
    extremos = log_ret[log_ret.abs() > umbral_movimiento]
    return {
        "velas": int(len(df)),
        "desde": df.index.min().strftime(FORMATO_FECHA),
        "hasta": df.index.max().strftime(FORMATO_FECHA),
        "huecos": int(len(faltan)),
        "fechas_hueco": [f.strftime("%Y-%m-%d") for f in faltan[:50]],
        "ohlc_incoherente": int(incoherente.sum()),
        "fechas_ohlc_incoherente": [f.strftime("%Y-%m-%d") for f in df.index[incoherente][:50]],
        "volumen_cero": int((df["Volume"] <= 0).sum()),
        "movimientos_extremos": {f.strftime("%Y-%m-%d"): round(float(v), 4) for f, v in extremos.items()},
    }


def comparar_fuentes(a: pd.DataFrame, b: pd.DataFrame, umbral: float = 0.02) -> dict:
    """Diferencia relativa de cierres en los días comunes (b respecto a a)."""
    comunes = a.index.intersection(b.index)
    if len(comunes) == 0:
        return {"dias_comunes": 0}
    dif = (b.loc[comunes, "Close"] / a.loc[comunes, "Close"] - 1).abs()
    peores = dif.sort_values(ascending=False).head(10)
    return {
        "dias_comunes": int(len(comunes)),
        "desde": comunes.min().strftime("%Y-%m-%d"),
        "hasta": comunes.max().strftime("%Y-%m-%d"),
        "mediana_dif_pct": round(float(dif.median() * 100), 4),
        "p95_dif_pct": round(float(dif.quantile(0.95) * 100), 4),
        "max_dif_pct": round(float(dif.max() * 100), 4),
        f"dias_dif_mayor_{umbral * 100:g}pct": int((dif > umbral).sum()),
        "peores_dias": {f.strftime("%Y-%m-%d"): round(float(v * 100), 3) for f, v in peores.items()},
    }


# =============================================================================
# Serie limpia
# =============================================================================

def construir_serie_limpia(
    principal: pd.DataFrame,
    respaldo: Optional[pd.DataFrame],
    nombre_principal: str,
    nombre_respaldo: str,
    intervalo: str = "1d",
    dias_arranque: int = 30,
) -> tuple[pd.DataFrame, list[dict]]:
    """Serie de la fuente principal; los huecos se rellenan con la fuente de
    respaldo (nunca interpolando), y cada relleno se registra.

    Los huecos sin respaldo dentro de los primeros `dias_arranque` días
    (típicos de los primeros días de cotización de un par) no se rellenan:
    la serie se RECORTA para empezar justo después del último de ellos, y el
    recorte se registra como incidencia.

    Las velas con OHLC incoherente de la principal se sustituyen por las del
    respaldo si existen allí; si no, se conservan y quedan registradas.
    Devuelve (serie con columna `fuente`, lista de incidencias).
    """
    serie = principal[ESQUEMA_OHLCV].copy()
    serie["fuente"] = nombre_principal
    incidencias: list[dict] = []

    incoherente = (
        (serie["High"] < serie[["Open", "Close"]].max(axis=1))
        | (serie["Low"] > serie[["Open", "Close"]].min(axis=1))
    )
    for fecha in serie.index[incoherente]:
        if respaldo is not None and fecha in respaldo.index:
            serie.loc[fecha, ESQUEMA_OHLCV] = respaldo.loc[fecha, ESQUEMA_OHLCV].to_numpy()
            serie.loc[fecha, "fuente"] = nombre_respaldo
            accion = f"sustituida por {nombre_respaldo}"
        else:
            accion = "conservada (sin respaldo ese día)"
        incidencias.append({"fecha": fecha.strftime("%Y-%m-%d"), "tipo": "ohlc_incoherente", "accion": accion})

    rejilla = pd.date_range(serie.index.min(), serie.index.max(), freq=duracion_intervalo(intervalo))
    for fecha in rejilla.difference(serie.index):
        if respaldo is not None and fecha in respaldo.index:
            fila = respaldo.loc[[fecha], ESQUEMA_OHLCV].copy()
            fila["fuente"] = nombre_respaldo
            serie = pd.concat([serie, fila])
            accion = f"rellenado con {nombre_respaldo}"
        else:
            accion = "SIN DATO (hueco que permanece)"
        incidencias.append({"fecha": fecha.strftime("%Y-%m-%d"), "tipo": "hueco", "accion": accion})

    serie = serie.sort_index()
    sin_dato = [
        pd.Timestamp(i["fecha"], tz="UTC") for i in incidencias
        if i["tipo"] == "hueco" and i["accion"].startswith("SIN DATO")
    ]
    limite_arranque = serie.index.min() + pd.Timedelta(days=dias_arranque)
    en_arranque = [f for f in sin_dato if f <= limite_arranque]
    if en_arranque:
        nuevo_inicio = max(en_arranque) + duracion_intervalo(intervalo)
        incidencias.append({
            "fecha": nuevo_inicio.strftime("%Y-%m-%d"),
            "tipo": "recorte_inicio",
            "accion": f"serie recortada para empezar el {nuevo_inicio:%Y-%m-%d} "
                      f"({int((serie.index < nuevo_inicio).sum())} velas iniciales fuera por huecos de arranque)",
        })
        serie = serie[serie.index >= nuevo_inicio]
    return serie, incidencias


# =============================================================================
# Guardado versionado y carga con verificación
# =============================================================================

def nombre_archivo(simbolo: str, intervalo: str, sufijo: str = "") -> str:
    return f"{simbolo.replace('/', '-')}_{intervalo}{sufijo}.csv"


def sha256_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 16), b""):
            h.update(bloque)
    return h.hexdigest()


def guardar_csv(df: pd.DataFrame, ruta: Path) -> str:
    """CSV determinista (formato fijo, LF) y devuelve su SHA-256."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    salida = df.copy()
    salida.index = salida.index.strftime(FORMATO_FECHA)
    salida.index.name = "timestamp"
    salida.to_csv(ruta, float_format="%.8f", lineterminator="\n", encoding="utf-8")
    return sha256_archivo(ruta)


def escribir_manifiesto(directorio: Path, manifiesto: dict) -> Path:
    ruta = directorio / "MANIFIESTO.json"
    ruta.write_text(json.dumps(manifiesto, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return ruta


def cargar_historico(
    simbolo: str, intervalo: str = "1d", version: str = "v1", raiz: Path = RAIZ_DATOS
) -> pd.DataFrame:
    """Carga la serie limpia versionada comprobando antes su SHA-256.

    Si el archivo no coincide con el manifiesto (alguien lo editó, o se
    corrompió), se lanza un error: nunca se backtestea sobre datos que no
    son los registrados.
    """
    directorio = raiz / version
    manifiesto = json.loads((directorio / "MANIFIESTO.json").read_text(encoding="utf-8"))
    nombre = nombre_archivo(simbolo, intervalo)
    esperado = manifiesto["archivos"].get(nombre)
    if esperado is None:
        raise KeyError(f"'{nombre}' no está en el manifiesto de datos/{version}.")
    ruta = directorio / nombre
    real = sha256_archivo(ruta)
    if real != esperado:
        raise ValueError(
            f"Checksum de {ruta} no coincide con el manifiesto (esperado {esperado[:12]}…, "
            f"real {real[:12]}…). Los datos han cambiado: no se usan."
        )
    df = pd.read_csv(ruta, index_col="timestamp")
    df.index = pd.to_datetime(df.index, format=FORMATO_FECHA, utc=True)
    return df
