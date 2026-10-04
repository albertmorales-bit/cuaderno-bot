"""
=============================================================================
 BOT-PREDICT · MÓDULO 1: Configuración del entorno y extracción unificada
                          de datos (Acciones + Cripto)
=============================================================================

Objetivo del módulo
--------------------
Construir una única función de entrada que, sin importar si el activo es
una acción/ETF o una criptomoneda, siempre devuelva un DataFrame de pandas
con el MISMO esquema de columnas (Open, High, Low, Close, Volume + índice
de fecha en UTC).

¿Por qué es importante esto?
-----------------------------
Todo lo que construyamos después (indicadores técnicos, señales, motor de
riesgo, backtester) va a operar sobre ese DataFrame estandarizado. Si hoy
invertimos tiempo en una capa de datos limpia, evitamos que cada módulo
posterior tenga que "saber" si el dato viene de yfinance o de ccxt. Esto es
un principio de ingeniería de software (separación de responsabilidades /
"single source of truth" para el esquema de datos) tan importante como la
propia estrategia matemática: un backtest es tan fiable como los datos que
lo alimentan (regla de "garbage in, garbage out").

Fuentes de datos:
    - yfinance -> Acciones, ETFs, índices (Yahoo Finance).
    - ccxt     -> Criptomonedas, vía API pública de un exchange (Binance
                  por defecto, configurable).

Compatibilidad: pensado para correr igual en Google Colab que en local.
=============================================================================
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

import pandas as pd

# -----------------------------------------------------------------------
# Dependencias externas. En Colab: !pip install yfinance ccxt -q
# En local: pip install yfinance ccxt
# -----------------------------------------------------------------------
try:
    import yfinance as yf
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "Falta 'yfinance'. Instálalo con: pip install yfinance"
    ) from exc

try:
    import ccxt
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "Falta 'ccxt'. Instálalo con: pip install ccxt"
    ) from exc


# -----------------------------------------------------------------------
# Configuración básica de logging.
# En un sistema de trading, tener trazabilidad de qué datos se pidieron,
# cuándo y con qué resultado no es opcional: es la base para poder
# depurar por qué una señal se disparó (o no) más adelante.
# -----------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("bot_predict.datos")


class TipoActivo(str, Enum):
    """Distingue el origen del dato: acción/ETF vs criptomoneda.

    Usar un Enum en vez de strings sueltos ("stock", "crypto") evita
    errores de escritura (typos) y le da autocompletado a tu editor.
    """

    ACCION = "accion"
    CRIPTO = "cripto"


# Columnas que TODO DataFrame de salida de este módulo debe tener,
# en este orden exacto. Es el "contrato" que el resto del sistema
# puede asumir siempre válido.
ESQUEMA_OHLCV = ["Open", "High", "Low", "Close", "Volume"]


def duracion_intervalo(intervalo: str) -> pd.Timedelta:
    """Convierte un intervalo de vela ('15m', '1h', '4h', '1d', '1w') a Timedelta.

    Se usa para saber cuándo CIERRA una vela: una vela con marca de tiempo
    `t` (apertura) cierra en `t + duracion`. Ver `descartar_vela_en_curso`.
    """
    unidades = {"m": "min", "h": "h", "d": "D", "w": "W"}
    intervalo = intervalo.strip().lower()
    if len(intervalo) < 2 or intervalo[-1] not in unidades or not intervalo[:-1].isdigit():
        raise ValueError(f"Intervalo no soportado: '{intervalo}'. Usa p. ej. '15m', '1h', '4h', '1d', '1w'.")
    return pd.Timedelta(int(intervalo[:-1]), unit=unidades[intervalo[-1]])


def descartar_vela_en_curso(
    df: pd.DataFrame, intervalo: str, ahora: Optional[pd.Timestamp] = None
) -> pd.DataFrame:
    """Elimina las velas que todavía no han cerrado en el instante `ahora`.

    Auditoría Fase 0 (P7): ccxt (Kraken incluido) y yfinance devuelven como
    última fila la vela EN CURSO, cuyo Close/High/Low aún van a cambiar.
    Usarla en un backtest contamina la última barra; usarla en vivo sería
    lookahead puro (decidir con un cierre que todavía no existe). Las marcas
    de tiempo de ambas fuentes son de APERTURA de vela, así que una vela está
    cerrada si `apertura + duracion <= ahora`.

    `ahora` es inyectable para que los tests sean deterministas.
    """
    ahora = pd.Timestamp.now(tz="UTC") if ahora is None else pd.Timestamp(ahora)
    if ahora.tzinfo is None:
        ahora = ahora.tz_localize("UTC")
    cerradas = df.index + duracion_intervalo(intervalo) <= ahora
    n_descartadas = int((~cerradas).sum())
    if n_descartadas:
        logger.info("Descartadas %d vela(s) aún en curso (ahora=%s).", n_descartadas, ahora)
    return df[cerradas]


def _parsear_periodo_a_dias(periodo: str) -> int:
    """Convierte cadenas de periodo tipo '1y', '6mo', '90d' a días.

    Usa el mismo formato de cadena que ya acepta `yfinance` en su
    parámetro `period`, para que `ParametrosDescarga.periodo` sirva
    igual para acciones que para la paginación de cripto.
    """
    periodo_normalizado = periodo.strip().lower()
    if periodo_normalizado.endswith("mo"):
        return int(periodo_normalizado[:-2]) * 30
    if periodo_normalizado.endswith("y"):
        return int(periodo_normalizado[:-1]) * 365
    if periodo_normalizado.endswith("d"):
        return int(periodo_normalizado[:-1])
    raise ValueError(
        f"Formato de periodo no soportado: '{periodo}'. "
        "Usa 'Ny' (años), 'Nmo' (meses) o 'Nd' (días), p.ej. '1y', '6mo', '90d'."
    )


@dataclass
class ParametrosDescarga:
    """Agrupa los parámetros de una petición de datos.

    Usamos un dataclass en vez de pasar 5-6 argumentos sueltos a cada
    función: hace el código más legible y fácil de extender (por ejemplo,
    el día de mañana añadimos un campo `ajustado: bool` sin romper nada).
    """

    ticker: str
    tipo: TipoActivo
    intervalo: str = "1d"      # "1d" (diario) o "4h" (4 horas), etc.
    periodo: str = "2y"        # Horizonte histórico a descargar (yfinance)
    exchange_id: str = "binance"  # Exchange de ccxt para cripto
    # Fechas explícitas (UTC). Si se dan, sustituyen a `periodo`: así una
    # ejecución es reproducible y no depende del día en que se lanza
    # (auditoría Fase 0, P9). `fecha_fin` es exclusiva.
    fecha_inicio: Optional[str] = None
    fecha_fin: Optional[str] = None
    # Descarta la vela en curso (auditoría Fase 0, P7). Solo debe ponerse a
    # False en tests que construyan datos a mano.
    solo_velas_cerradas: bool = True


class ProveedorDatos:
    """Capa de datos unificada: acciones (yfinance) + cripto (ccxt).

    Esta clase es el único punto de entrada que el resto del sistema
    debería usar para obtener velas (OHLCV). Internamente decide si
    delega en yfinance o en ccxt según `TipoActivo`, pero de cara afuera
    siempre entrega el mismo formato.
    """

    # Velas que se avanza el cursor cuando un exchange devuelve un lote vacío
    # antes del inicio de cotización (menor que el límite por petición más
    # pequeño conocido, 300 en Coinbase, para no saltarse datos).
    _VELAS_POR_SALTO = 250

    def __init__(self, exchange_id: str = "binance") -> None:
        # Instanciamos el cliente del exchange una sola vez y lo
        # reutilizamos (evita overhead de crear conexiones repetidas).
        # enableRateLimit=True hace que ccxt espere automáticamente entre
        # peticiones lo necesario para no saturar la API pública del
        # exchange (importante en la paginación de _descargar_cripto).
        self._exchange_id = exchange_id
        self._exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True})

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def obtener_datos(self, params: ParametrosDescarga) -> pd.DataFrame:
        """Punto de entrada único: enruta a la fuente correcta.

        Devuelve siempre un DataFrame con columnas ESQUEMA_OHLCV e
        índice de tipo datetime (UTC), ordenado cronológicamente.
        """
        logger.info(
            "Solicitando datos: %s (%s) intervalo=%s",
            params.ticker, params.tipo.value, params.intervalo,
        )

        if params.tipo is TipoActivo.ACCION:
            df = self._descargar_accion(params)
        elif params.tipo is TipoActivo.CRIPTO:
            df = self._descargar_cripto(params)
        else:  # Defensivo: si en el futuro se añade un TipoActivo nuevo
            raise ValueError(f"TipoActivo no soportado: {params.tipo}")

        df = self._validar_y_normalizar(df, params.ticker)
        if params.fecha_inicio is not None:
            df = df[df.index >= pd.Timestamp(params.fecha_inicio, tz="UTC")]
        if params.fecha_fin is not None:
            df = df[df.index < pd.Timestamp(params.fecha_fin, tz="UTC")]
        if params.solo_velas_cerradas:
            df = descartar_vela_en_curso(df, params.intervalo)
        if df.empty:
            raise ValueError(f"'{params.ticker}': no quedan velas en el rango solicitado.")
        return df

    # ------------------------------------------------------------------
    # Fuente 1: Acciones / ETFs vía yfinance
    # ------------------------------------------------------------------
    def _descargar_accion(self, params: ParametrosDescarga) -> pd.DataFrame:
        rango = (
            {"start": params.fecha_inicio, "end": params.fecha_fin}
            if params.fecha_inicio is not None
            else {"period": params.periodo}
        )
        df = yf.download(
            tickers=params.ticker,
            **rango,
            interval=params.intervalo,
            auto_adjust=True,   # Ajusta por dividendos/splits: precios comparables.
            progress=False,
        )

        if df.empty:
            raise ValueError(
                f"yfinance no devolvió datos para '{params.ticker}'. "
                "Revisa el ticker o el intervalo/periodo solicitado."
            )

        # yfinance a veces devuelve columnas en MultiIndex (p.ej. al pedir
        # varios tickers a la vez). Nos aseguramos de aplanarlo.
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        return df[ESQUEMA_OHLCV]

    # ------------------------------------------------------------------
    # Fuente 2: Criptomonedas vía ccxt (con paginación)
    # ------------------------------------------------------------------
    def _descargar_cripto(self, params: ParametrosDescarga) -> pd.DataFrame:
        # Los exchanges limitan cada petición de fetch_ohlcv a un número
        # máximo de velas (Binance ~1000, Kraken ~720, y varía según el
        # exchange). Para un histórico de 12 meses en 4h (~2190 velas)
        # hace falta más de una petición: paginamos avanzando el parámetro
        # `since` hasta cubrir todo el rango solicitado en `params.periodo`
        # (p.ej. "1y", "6mo", "90d"), sin asumir cuántas velas devuelve
        # cada llamada.
        timeframe = params.intervalo
        limite_por_peticion = 1000  # Techo solicitado; cada exchange aplica el suyo propio.

        if params.fecha_inicio is not None:
            inicio = pd.Timestamp(params.fecha_inicio, tz="UTC")
            fin = (
                pd.Timestamp(params.fecha_fin, tz="UTC")
                if params.fecha_fin is not None
                else pd.Timestamp.now(tz="UTC")
            )
            desde_ms = int(inicio.timestamp() * 1000)
            ahora_ms = int(fin.timestamp() * 1000)
            dias_historial = (fin - inicio).days
        else:
            dias_historial = _parsear_periodo_a_dias(params.periodo)
            desde_ms = int(
                (datetime.now(timezone.utc) - timedelta(days=dias_historial)).timestamp() * 1000
            )
            ahora_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        velas_acumuladas: list[list] = []
        cursor_ms = desde_ms
        paso_ms = int(duracion_intervalo(timeframe).total_seconds() * 1000)
        max_iteraciones = 400  # cinturón y tirantes: nunca más de 400 peticiones.

        for _ in range(max_iteraciones):
            if cursor_ms >= ahora_ms:
                break

            try:
                lote = self._exchange.fetch_ohlcv(
                    symbol=params.ticker,
                    timeframe=timeframe,
                    since=cursor_ms,
                    limit=limite_por_peticion,
                )
            except Exception as exc:
                mensaje_error = str(exc)
                if "451" in mensaje_error or "403" in mensaje_error:
                    raise ConnectionError(
                        f"El exchange '{self._exchange_id}' ha rechazado la petición "
                        f"(código {'451' if '451' in mensaje_error else '403'}). Esto "
                        "suele significar un BLOQUEO GEOGRÁFICO: el servidor desde el "
                        "que ejecutas el script (p. ej. Google Colab, con IP de EE.UU.) "
                        "no tiene permitido el acceso a la API pública de este exchange. "
                        "Prueba con otro `exchange_id` en la configuración, p. ej. "
                        "'kraken' en vez de 'binance'."
                    ) from exc
                raise
            if not lote:
                if not velas_acumuladas:
                    # Lote vacío ANTES de tener ningún dato: lo normal es que el
                    # par aún no cotizara en esa fecha (p. ej. Coinbase BTC/EUR
                    # empieza el 2015-04-23). Saltamos una ventana hacia delante
                    # en vez de concluir que no hay datos (fallo hallado en la
                    # Fase 1: la v4 se rendía aquí).
                    cursor_ms += self._VELAS_POR_SALTO * paso_ms
                    continue
                break

            if not velas_acumuladas and lote[0][0] > desde_ms + 7 * 86_400_000:
                # Auditoría Fase 0 (P1): la API OHLC pública de Kraken solo
                # devuelve las 720 velas MÁS RECIENTES e ignora `since`. Si la
                # primera vela llega más de una semana después de lo pedido,
                # o el par empezó a cotizar entonces, o el histórico está
                # truncado: el log no puede distinguirlo, así que lo avisa.
                logger.warning(
                    "%s: pedido desde %s, primera vela disponible en '%s': %s. O el par empezó "
                    "a cotizar entonces, o el exchange no sirve histórico antiguo por API "
                    "(Kraken: máx. 720 velas).",
                    params.ticker,
                    pd.Timestamp(desde_ms, unit="ms", tz="UTC").date(),
                    self._exchange_id,
                    pd.Timestamp(lote[0][0], unit="ms", tz="UTC").date(),
                )
            velas_acumuladas.extend(lote)
            ultimo_timestamp = lote[-1][0]

            # Protección anti bucle infinito: si el exchange no avanza el
            # cursor, cortamos en vez de quedarnos pidiendo lo mismo.
            if ultimo_timestamp <= cursor_ms:
                break
            cursor_ms = ultimo_timestamp + 1

            # OJO: NO usamos "len(lote) < limite_por_peticion" como señal de
            # "ya no hay más histórico". Es una suposición que rompe con
            # exchanges cuyo límite real por petición es menor que el
            # solicitado (p. ej. Kraken devuelve como mucho ~720 velas por
            # llamada, aunque pidamos 1000) -> cortaría la paginación tras
            # el primer lote y nos dejaría con muchos menos meses de los
            # pedidos, sin ningún error visible. La única señal fiable de
            # "ya no hay más" es haber alcanzado el presente (comprobado al
            # principio del bucle) o que el exchange devuelva un lote vacío.

            # Respeta el rate limit del exchange entre peticiones sucesivas.
            time.sleep(self._exchange.rateLimit / 1000)

        if not velas_acumuladas:
            raise ValueError(
                f"ccxt/{self._exchange_id} no devolvió datos para "
                f"'{params.ticker}'. Revisa el símbolo (formato BASE/QUOTE), "
                "el timeframe y el periodo solicitado."
            )

        df = pd.DataFrame(
            velas_acumuladas,
            columns=["timestamp", "Open", "High", "Low", "Close", "Volume"],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)

        logger.info(
            "%s: %d velas descargadas en paginación (~%d días de histórico).",
            params.ticker, len(df), dias_historial,
        )
        return df[ESQUEMA_OHLCV]

    # ------------------------------------------------------------------
    # Validación y normalización común a ambas fuentes
    # ------------------------------------------------------------------
    @staticmethod
    def _validar_y_normalizar(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
        """Aplica controles de calidad mínimos antes de entregar el dato.

        Esto es prevención temprana de sesgos: un dato corrupto o con
        huecos que pase desapercibido aquí puede generar señales falsas
        varios módulos más adelante, mucho más difíciles de detectar.
        """
        df = df.copy()

        # 0) Índice en UTC siempre (yfinance puede devolverlo sin zona
        #    horaria); sin esto, comparar con fechas UTC lanzaría un error.
        df.index = pd.DatetimeIndex(df.index)
        df.index = df.index.tz_localize("UTC") if df.index.tz is None else df.index.tz_convert("UTC")

        # 1) Índice temporal ordenado y sin duplicados.
        df = df[~df.index.duplicated(keep="last")]
        df.sort_index(inplace=True)

        # 2) Tipos numéricos correctos (a veces llegan como object/str).
        for col in ESQUEMA_OHLCV:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # 3) Filas totalmente vacías o con precio <= 0 se descartan.
        filas_antes = len(df)
        df = df.dropna(subset=["Close"])
        df = df[df["Close"] > 0]
        filas_eliminadas = filas_antes - len(df)
        if filas_eliminadas > 0:
            logger.warning(
                "%s: se descartaron %d filas inválidas durante la limpieza.",
                ticker, filas_eliminadas,
            )

        if df.empty:
            raise ValueError(
                f"Tras la limpieza no quedaron datos válidos para '{ticker}'."
            )

        logger.info(
            "%s: %d velas listas (%s → %s).",
            ticker, len(df), df.index.min(), df.index.max(),
        )
        return df


# =============================================================================
# Bloque de auto-verificación (se ejecuta solo si corres este archivo
# directamente, no cuando lo importas como módulo desde otro script/notebook)
# =============================================================================
if __name__ == "__main__":
    proveedor = ProveedorDatos(exchange_id="binance")

    # --- Ejemplo 1: Acción (Apple, diario, últimos 2 años) ---
    datos_accion = proveedor.obtener_datos(
        ParametrosDescarga(ticker="AAPL", tipo=TipoActivo.ACCION,
                            intervalo="1d", periodo="2y")
    )
    print("\n=== AAPL (acción) ===")
    print(datos_accion.tail())

    # --- Ejemplo 2: Criptomoneda (Bitcoin, velas de 4h, últimos 12 meses) ---
    datos_cripto = proveedor.obtener_datos(
        ParametrosDescarga(ticker="BTC/USDT", tipo=TipoActivo.CRIPTO,
                            intervalo="4h", periodo="1y")
    )
    print("\n=== BTC/USDT (cripto) ===")
    print(datos_cripto.tail())
