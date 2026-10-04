"""
=============================================================================
 BOT-PREDICT · MÓDULO 8: Motor de paper trading en vivo (Fase 5)
=============================================================================

CERO órdenes reales: solo lee datos públicos de mercado y simula.

Cada ejecución (una vez al día, poco después de las 00:00 UTC):
1. Verifica la cadena del registro y que la configuración es la congelada.
2. Añade al archivo de velas (`vivo/velas/`) las velas diarias CERRADAS
   nuevas y registra cada una (evento `vela`).
3. Valora cada cartera al cierre de esa vela (`valoracion`) y aplica las
   reglas de seguridad fijadas de antemano (`alerta`, `parada`).
4. Para la última vela cerrada: calcula la exposición objetivo con la MISMA
   función que el backtest (`main.preparar_conjunto`) y la registra ANTES de
   ejecutar (`decision`, con el motivo y el régimen).
5. Simula la orden en la APERTURA de la vela en curso con la MISMA función
   que el backtest (`MotorExposicion.paso_apertura`) y la registra con el
   precio de referencia, comisión, slippage y funding (`ejecucion`).
6. Cierra el ciclo (`ciclo_cerrado`).

Reglas de robustez (D-032):
- Idempotente: si el ciclo de una vela ya está cerrado, no hace nada. Si se
  interrumpió a medias, lo completa sin repetir lo ya registrado.
- Velas perdidas: si un día no se ejecutó, sus velas se registran como
  `vela_perdida` y NO se opera sobre ellas a posteriori (un bot caído no
  habría operado). Es la única fuente de diferencia con el backtest, y queda
  a la vista en el panel.
- El estado de cada cartera se reconstruye desde el registro, que es la
  única fuente de verdad.

Carteras: `V8` (la estrategia, etiquetada NO APTO en validación) y
`FIJO30` (30 % fijo en cada activo, la alternativa trivial que la igualó).
=============================================================================
"""

from __future__ import annotations

import dataclasses
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

import pandas as pd

import main
from modulo_1_datos import ESQUEMA_OHLCV, descartar_vela_en_curso
from modulo_4b_exposicion import EstadoCartera, MotorExposicion
from modulo_5_regimenes import clasificar_regimenes
from modulo_7_registro import Registro, contenido_canonico, sha256_texto

PARES = ("BTC/EUR", "ETH/EUR")
UN_DIA = pd.Timedelta(days=1)


@dataclass(frozen=True)
class ReglasSeguridad:
    """Fijadas en el pre-registro. Ninguna cambia la estrategia validada salvo
    `parada_drawdown`, que es el criterio de parada del experimento."""

    parada_drawdown: float = 0.35           # caída desde máximo de la cartera V8: liquidar y parar
    alerta_perdida_diaria: float = 0.10     # solo aviso visible
    alerta_perdida_semanal: float = 0.20    # solo aviso visible
    alerta_velas_perdidas_seguidas: int = 3  # aviso técnico
    salto_sospechoso: float = 0.50          # |cierre / cierre previo - 1| mayor: no se decide ese día
    dias_experimento: int = 90


@dataclass(frozen=True)
class DefinicionCartera:
    nombre: str
    exposicion_fija: Optional[float] = None   # None = estrategia V8


CARTERAS = (DefinicionCartera("V8"), DefinicionCartera("FIJO30", 0.30))


class FuenteVelas(Protocol):
    def velas(self, par: str) -> pd.DataFrame:
        """Velas diarias con índice = apertura en UTC, incluida la vela en curso."""


class FuenteKraken:
    """Datos públicos de Kraken vía ccxt (sin claves: no puede operar)."""

    def __init__(self, reintentos: int = 3, espera_s: float = 10.0) -> None:
        import ccxt

        self._exchange = ccxt.kraken({"enableRateLimit": True})
        self._reintentos, self._espera = reintentos, espera_s

    def velas(self, par: str) -> pd.DataFrame:
        for intento in range(self._reintentos):
            try:
                crudo = self._exchange.fetch_ohlcv(par, "1d", limit=720)
                break
            except Exception:
                if intento == self._reintentos - 1:
                    raise
                time.sleep(self._espera)
        df = pd.DataFrame(crudo, columns=["timestamp", *ESQUEMA_OHLCV])
        df.index = pd.to_datetime(df.pop("timestamp"), unit="ms", utc=True)
        return df.astype(float)


class FuenteHistorica:
    """Para el test de repetición: devuelve el histórico como lo habría visto
    el bot en `ahora` (la vela en curso solo con su apertura conocida)."""

    def __init__(self, datos: dict[str, pd.DataFrame]) -> None:
        self.datos, self.ahora = datos, None

    def velas(self, par: str) -> pd.DataFrame:
        df = self.datos[par]
        df = df[df.index <= self.ahora].copy()
        en_curso = df.index + UN_DIA > self.ahora
        df.loc[en_curso, ["High", "Low", "Close"]] = df.loc[en_curso, "Open"].to_numpy()[:, None]
        df.loc[en_curso, "Volume"] = 0.0
        return df


def configuracion_congelada(config: "main.Configuracion", reglas: ReglasSeguridad) -> dict:
    def plano(x):
        if isinstance(x, (list, tuple)):
            return [plano(v) for v in x]
        if isinstance(x, dict):
            return {k: plano(v) for k, v in x.items()}
        return getattr(x, "value", x)
    return {"configuracion": plano(dataclasses.asdict(config)), "reglas": dataclasses.asdict(reglas),
            "carteras": [dataclasses.asdict(c) for c in CARTERAS], "pares": list(PARES)}


def hash_configuracion(congelada: dict) -> str:
    return sha256_texto(contenido_canonico(congelada))


def _ts(t: pd.Timestamp) -> str:
    return pd.Timestamp(t).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fecha(t) -> pd.Timestamp:
    return pd.Timestamp(t).tz_convert("UTC") if pd.Timestamp(t).tzinfo else pd.Timestamp(t, tz="UTC")


class MotorVivo:
    def __init__(self, raiz: Path, config: "main.Configuracion", reglas: ReglasSeguridad,
                 fuente: FuenteVelas) -> None:
        self.raiz = Path(raiz)
        self.config, self.reglas, self.fuente = config, reglas, fuente
        self.registro = Registro(self.raiz / "registro.jsonl")
        self.ruta_config = self.raiz / "configuracion_congelada.json"

    # ------------------------------------------------------------ archivo
    def _ruta_velas(self, par: str) -> Path:
        return self.raiz / "velas" / f"{par.replace('/', '-')}_1d.csv"

    def archivo(self, par: str) -> pd.DataFrame:
        """Archivo de velas cerradas del par (copia; caché invalidada por tamaño y fecha)."""
        ruta = self._ruta_velas(par)
        st = ruta.stat()
        huella = (st.st_size, st.st_mtime_ns)
        cache = getattr(self, "_cache_archivo", {})
        if par not in cache or cache[par][0] != huella:
            df = pd.read_csv(ruta, index_col="timestamp")
            df.index = pd.to_datetime(df.index, format="%Y-%m-%dT%H:%M:%SZ", utc=True)
            cache[par] = (huella, df)
            self._cache_archivo = cache
        return cache[par][1].copy()

    def _anadir_velas(self, par: str, nuevas: pd.DataFrame) -> None:
        ruta = self._ruta_velas(par)
        with ruta.open("a", encoding="utf-8", newline="\n") as f:
            for t, fila in nuevas.iterrows():
                f.write(_ts(t) + "," + ",".join(f"{fila[c]:.8f}" for c in ESQUEMA_OHLCV) + "\n")

    # --------------------------------------------------------- inicializar
    def inicializar(self, ahora: pd.Timestamp, commit: str = "desconocido") -> dict:
        """Día 0: archivo de velas inicial, configuración congelada y evento
        `inicio`. Se niega si ya existe un registro."""
        if self.registro.ruta.exists():
            raise RuntimeError("El registro ya existe: el experimento ya se inició.")
        ahora = _fecha(ahora)
        congelada = configuracion_congelada(self.config, self.reglas)
        self.raiz.mkdir(parents=True, exist_ok=True)
        self.ruta_config.write_text(json.dumps(congelada, indent=2, ensure_ascii=False) + "\n",
                                    encoding="utf-8", newline="\n")
        hashes = {}
        for par in PARES:
            cerradas = descartar_vela_en_curso(self.fuente.velas(par), "1d", ahora)
            if len(cerradas) <= self.config.velas_calentamiento:
                raise RuntimeError(f"{par}: solo {len(cerradas)} velas cerradas; hacen falta más de "
                                   f"{self.config.velas_calentamiento} para calentar los indicadores.")
            ruta = self._ruta_velas(par)
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text("timestamp," + ",".join(ESQUEMA_OHLCV) + "\n", encoding="utf-8", newline="\n")
            self._anadir_velas(par, cerradas[ESQUEMA_OHLCV])
            hashes[par] = sha256_texto(ruta.read_text(encoding="utf-8"))
        return self.registro.anadir("inicio", {
            "capital_por_cartera": self.config.capital_inicial,
            "carteras": [c.nombre for c in CARTERAS],
            "hash_configuracion": hash_configuracion(congelada),
            "commit_codigo": commit,
            "archivo_inicial": {par: {"sha256": hashes[par], "ultima_vela": _ts(self.archivo(par).index[-1]),
                                      "velas": int(len(self.archivo(par)))} for par in PARES},
            "aviso": "Dinero ficticio, no es asesoramiento financiero, resultados pasados no garantizan nada.",
        }, ts_utc=ahora)

    # -------------------------------------------------------------- estado
    def _eventos(self, tipo: Optional[str] = None) -> list[dict]:
        ev = self.registro.eventos()
        return ev if tipo is None else [e for e in ev if e["tipo"] == tipo]

    def estado(self, cartera: str, par: str) -> EstadoCartera:
        estado = EstadoCartera(self.config.capital_inicial / len(PARES), 0.0)
        for e in self._eventos("ejecucion"):
            d = e["datos"]
            if d["cartera"] == cartera and d["par"] == par:
                estado.efectivo, estado.unidades = d["efectivo_despues"], d["unidades_despues"]
        return estado

    def _parada(self, cartera: str) -> bool:
        return any(e["datos"]["cartera"] == cartera for e in self._eventos("parada"))

    # ------------------------------------------------------------ ejecutar
    def ejecutar(self, ahora: pd.Timestamp) -> dict:
        ahora = _fecha(ahora)
        verificacion = self.registro.verificar()
        if not verificacion.valido:
            raise RuntimeError(f"Registro alterado en la línea {verificacion.linea_error}: {verificacion.error}")
        inicio = self._eventos("inicio")
        if not inicio:
            raise RuntimeError("El experimento no se ha inicializado.")
        congelada = configuracion_congelada(self.config, self.reglas)
        if hash_configuracion(congelada) != inicio[0]["datos"]["hash_configuracion"] or \
                json.loads(self.ruta_config.read_text(encoding="utf-8")) != congelada:
            raise RuntimeError("La configuración no es la congelada en el día 0. Un cambio exige una versión "
                               "nueva del experimento con el contador a cero.")

        # 1) Velas cerradas nuevas al archivo, cada una registrada.
        velas_api = {par: self.fuente.velas(par) for par in PARES}
        for par in PARES:
            archivo = self.archivo(par)
            cerradas = descartar_vela_en_curso(velas_api[par], "1d", ahora)
            nuevas = cerradas[cerradas.index > archivo.index[-1]][ESQUEMA_OHLCV]
            esperada = archivo.index[-1] + UN_DIA
            if len(nuevas) and nuevas.index[0] != esperada:
                self.registro.anadir("alerta", {"par": par, "regla": "hueco_datos", "fecha": _ts(esperada),
                                                "motivo": f"el exchange no devuelve la vela {_ts(esperada)}"}, ahora)
            for t, fila in nuevas.iterrows():
                self.registro.anadir("vela", {"par": par, "fecha": _ts(t),
                                              **{c: float(fila[c]) for c in ESQUEMA_OHLCV}}, ahora)
            if len(nuevas):
                self._anadir_velas(par, nuevas)

        # 2) Ciclos pendientes: velas posteriores al día 0 sin ciclo cerrado.
        cerrados = {(e["datos"]["par"], e["datos"]["fecha"]) for e in self._eventos("ciclo_cerrado")}
        pendientes = {}
        for par in PARES:
            archivo = self.archivo(par)
            limite = pd.Timestamp(inicio[0]["datos"]["archivo_inicial"][par]["ultima_vela"])
            pendientes[par] = [t for t in archivo.index if t > limite and (par, _ts(t)) not in cerrados]
            for t in pendientes[par]:     # valoración al cierre de cada vela pendiente
                self._valoracion(par, t, float(archivo.loc[t, "Close"]), ahora)

        # 3) Reglas de seguridad ANTES de decidir (la parada actúa en la siguiente apertura).
        self._comprobar_reglas(ahora)

        # 4) Velas perdidas (no se opera a posteriori) y ciclo de la última vela cerrada.
        resumen = {"ahora": _ts(ahora), "ciclos": []}
        perdidas = {(e["datos"]["par"], e["datos"]["fecha"]) for e in self._eventos("vela_perdida")}
        for par in PARES:
            if not pendientes[par]:
                continue
            ultima = self.archivo(par).index[-1]
            for t in pendientes[par]:
                if t != ultima:
                    if (par, _ts(t)) not in perdidas:
                        self.registro.anadir("vela_perdida", {"par": par, "fecha": _ts(t), "motivo":
                                             "el bot no se ejecutó tras su cierre; no se opera a posteriori"}, ahora)
                    self.registro.anadir("ciclo_cerrado", {"par": par, "fecha": _ts(t), "operado": False}, ahora)
            if ultima in pendientes[par]:
                resumen["ciclos"].append(self._ciclo(par, ultima, velas_api[par], ahora))
        resumen["hash_dia"] = self.registro.verificar().ultimo_hash
        return resumen

    def _valoracion(self, par: str, t: pd.Timestamp, cierre: float, ahora) -> None:
        ya = {(e["datos"]["cartera"], e["datos"]["par"], e["datos"]["fecha"]) for e in self._eventos("valoracion")}
        for c in CARTERAS:
            if (c.nombre, par, _ts(t)) in ya:
                continue
            e = self.estado(c.nombre, par)
            equity = e.efectivo + e.unidades * cierre
            self.registro.anadir("valoracion", {
                "cartera": c.nombre, "par": par, "fecha": _ts(t), "cierre": cierre, "efectivo": e.efectivo,
                "unidades": e.unidades, "equity": equity,
                "exposicion": e.unidades * cierre / equity if equity > 0 else 0.0,
            }, ahora)

    def _motivo_v8(self, fila: pd.Series, objetivo: float) -> str:
        estados = [(f"{e}/{s}", int(fila[f"estado_{e}_{s}"])) for e, s in self.config.sistemas_donchian]
        detalle = ", ".join(f"{nombre} {'sí' if v else 'no'}" for nombre, v in estados)
        escala = float(fila["escala_volatilidad"])
        vol = self.config.objetivo_volatilidad / escala if 0 < escala < 1 else None
        texto_vol = f"volatilidad de 30 días {vol:.0%}" if vol is not None else "volatilidad por debajo del objetivo"
        return (f"{sum(v for _, v in estados)} de {len(estados)} sistemas en tendencia ({detalle}); "
                f"{texto_vol}, escala {escala:.2f}; exposición objetivo {objetivo:.0%}")

    def _ciclo(self, par: str, t: pd.Timestamp, velas_api: pd.DataFrame, ahora) -> dict:
        archivo = self.archivo(par)
        fila = archivo.loc[t]

        # Decisión, registrada ANTES de ejecutar.
        decisiones = {(e["datos"]["cartera"], e["datos"]["par"], e["datos"]["fecha"]): e["datos"]
                      for e in self._eventos("decision")}
        senales = main.preparar_conjunto(self.config, archivo).loc[t]
        regimen = clasificar_regimenes(archivo).loc[t]
        salto = abs(fila["Close"] / archivo["Close"].iloc[-2] - 1) if len(archivo) > 1 else 0.0
        for c in CARTERAS:
            clave = (c.nombre, par, _ts(t))
            if clave in decisiones:
                continue
            if c.exposicion_fija is not None:
                objetivo = c.exposicion_fija
                motivo = f"cartera de comparación: {c.exposicion_fija:.0%} fijo"
            else:
                objetivo = float(senales["exposicion_objetivo"]) if bool(senales["calentamiento_ok"]) else 0.0
                motivo = self._motivo_v8(senales, objetivo)
            if self._parada(c.nombre):
                objetivo, motivo = 0.0, "experimento detenido por la regla de parada: exposición 0"
            elif salto > self.reglas.salto_sospechoso:
                objetivo = None
                motivo = f"salto de precio sospechoso ({salto:.0%}): no se decide hoy y se mantiene la posición"
            datos = {"cartera": c.nombre, "par": par, "fecha": _ts(t), "cierre": float(fila["Close"]),
                     "exposicion_objetivo": objetivo, "motivo": motivo,
                     "regimen": {"tendencia": str(regimen["regimen_tendencia"]),
                                 "volatilidad": str(regimen["regimen_volatilidad"]),
                                 "fuerza": str(regimen["regimen_fuerza"])}}
            if c.exposicion_fija is None:
                datos["estados"] = {f"{e}/{s}": int(senales[f"estado_{e}_{s}"]) for e, s in self.config.sistemas_donchian}
                datos["escala_volatilidad"] = float(senales["escala_volatilidad"])
            self.registro.anadir("decision", datos, ahora)
            decisiones[clave] = datos

        # Ejecución en la apertura de la vela en curso.
        siguiente = t + UN_DIA
        if siguiente not in velas_api.index:
            self.registro.anadir("alerta", {"par": par, "regla": "sin_apertura", "fecha": _ts(siguiente),
                                            "motivo": "el exchange aún no da la apertura de la vela en curso; se reintentará"}, ahora)
            return {"par": par, "fecha": _ts(t), "completado": False}
        apertura = float(velas_api.loc[siguiente, "Open"])
        hechas = {(e["datos"]["cartera"], e["datos"]["par"], e["datos"]["fecha_decision"])
                  for e in self._eventos("ejecucion") + self._eventos("sin_orden")}
        params = main.parametros_exposicion(self.config, par, self.config.capital_inicial / len(PARES))
        for c in CARTERAS:
            if (c.nombre, par, _ts(t)) in hechas:
                continue
            objetivo = decisiones[(c.nombre, par, _ts(t))]["exposicion_objetivo"]
            estado = self.estado(c.nombre, par)
            ordenes = [] if objetivo is None else MotorExposicion(params, par).paso_apertura(
                estado, float(objetivo), apertura, siguiente, [], [])
            if not ordenes:
                self.registro.anadir("sin_orden", {"cartera": c.nombre, "par": par, "fecha_decision": _ts(t),
                                                   "fecha": _ts(siguiente), "apertura": apertura,
                                                   "motivo": "exposición dentro de la banda o sin cambio"}, ahora)
            for o in ordenes:
                self.registro.anadir("ejecucion", {
                    "cartera": c.nombre, "par": par, "fecha_decision": _ts(t), "fecha": _ts(o.fecha),
                    "lado": o.lado, "motivo": o.motivo, "unidades": o.unidades,
                    "precio_referencia": o.precio_referencia, "precio_efectivo": o.precio_efectivo,
                    "comision": o.comision, "slippage": o.coste_slippage, "funding": 0.0,
                    "exposicion_antes": o.exposicion_antes, "exposicion_objetivo": o.exposicion_objetivo,
                    "efectivo_despues": estado.efectivo, "unidades_despues": estado.unidades,
                }, ahora)
        self.registro.anadir("ciclo_cerrado", {"par": par, "fecha": _ts(t), "operado": True}, ahora)
        return {"par": par, "fecha": _ts(t), "completado": True}

    def _comprobar_reglas(self, ahora) -> None:
        val = pd.DataFrame([e["datos"] for e in self._eventos("valoracion")])
        if val.empty:
            return
        ya_alertas = {(e["datos"].get("cartera"), e["datos"].get("regla"), e["datos"].get("fecha"))
                      for e in self._eventos("alerta") + self._eventos("parada")}
        for c in CARTERAS:
            v = val[val["cartera"] == c.nombre].pivot_table(index="fecha", columns="par", values="equity")
            v = v.dropna()
            if v.empty:
                continue
            total = v.sum(axis=1)
            fecha = total.index[-1]
            dd = 1 - total.iloc[-1] / max(total.max(), self.config.capital_inicial)
            if c.exposicion_fija is None and dd >= self.reglas.parada_drawdown and not self._parada(c.nombre):
                self.registro.anadir("parada", {"cartera": c.nombre, "regla": "parada_drawdown", "fecha": fecha,
                                                "drawdown": dd, "motivo": "caída desde máximo por encima del límite "
                                                "pre-registrado: se liquida en la siguiente apertura y se detiene"}, ahora)
            for regla, ventana, limite in (("perdida_diaria", 1, self.reglas.alerta_perdida_diaria),
                                           ("perdida_semanal", 7, self.reglas.alerta_perdida_semanal)):
                if len(total) > ventana and total.iloc[-1] / total.iloc[-1 - ventana] - 1 <= -limite \
                        and (c.nombre, regla, fecha) not in ya_alertas:
                    self.registro.anadir("alerta", {"cartera": c.nombre, "regla": regla, "fecha": fecha,
                                                    "variacion": total.iloc[-1] / total.iloc[-1 - ventana] - 1}, ahora)
        perdidas = self._eventos("vela_perdida")
        if len(perdidas) >= self.reglas.alerta_velas_perdidas_seguidas:
            fechas = sorted({p["datos"]["fecha"] for p in perdidas})[-self.reglas.alerta_velas_perdidas_seguidas:]
            seguidas = all((pd.Timestamp(b) - pd.Timestamp(a)) == UN_DIA for a, b in zip(fechas, fechas[1:]))
            if seguidas and (None, "velas_perdidas", fechas[-1]) not in ya_alertas:
                self.registro.anadir("alerta", {"regla": "velas_perdidas", "fecha": fechas[-1],
                                                "motivo": f"{len(fechas)} días seguidos sin ejecutarse"}, ahora)
