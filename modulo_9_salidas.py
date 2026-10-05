"""
=============================================================================
 BOT-PREDICT · MÓDULO 9: Salidas diarias para X (Fase 6)
=============================================================================

Todo se calcula a partir del registro encadenado (la única fuente de verdad):
- `construir_estado`: día N de 90, capital, resultado del día y acumulado,
  caída actual y máxima, posiciones, órdenes, comisiones, régimen y motivo,
  velas perdidas y avisos, para la V8, la FIJO30 y comprar y mantener al 100 %.
- `tuit_diario` / `comentario_diario` / `hilo_semanal`: textos que respetan
  el límite de X con su recuento real (`longitud_x`: según la configuración
  v3 de twitter-text, "€", "…" o "→" cuentan 2 y cada enlace cuenta 23), y
  además `len()`. El texto varía cada día, pero siempre lleva día N de 90,
  capital total, resultado del día y caída.
- `imagen_diaria`: curva completa de capital (nunca solo la parte buena) y
  caída en un panel aparte (nunca dos ejes en el mismo gráfico).

Nunca se promete rentabilidad. Siempre la nota: dinero ficticio, no es
asesoramiento financiero, resultados pasados no garantizan nada.
=============================================================================
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

NOTA = "Dinero ficticio, no es asesoramiento financiero, resultados pasados no garantizan nada."
LIMITE_X = 280
CAPITAL = 10_000.0
DIAS = 90
NOMBRES = {"V8": "V8", "FIJO30": "30 % fijo", "BH100": "comprar y mantener"}

# Paleta validada (skill dataviz, validate_palette.js: todo PASS en claro y oscuro).
COLOR = {"V8": "#2a78d6", "FIJO30": "#eb6834", "BH100": "#898781"}
TINTA = {"superficie": "#fcfcfb", "primaria": "#0b0b0b", "secundaria": "#52514e", "tenue": "#898781",
         "rejilla": "#e1e0d9", "base": "#c3c2b7"}

ETIQUETA = {"debil": "débil"}   # las etiquetas internas no llevan tilde; al mostrarlas, sí
_URL = re.compile(r"https?://\S+")
_RANGOS_PESO_1 = ((0, 4351), (8192, 8205), (8208, 8223), (8242, 8247))


def longitud_x(texto: str) -> int:
    """Longitud ponderada de X (twitter-text v3): enlaces 23, caracteres de los
    rangos latinos 1, el resto 2. No se usan emojis en los textos del bot."""
    total = 0
    for trozo in _URL.split(texto):
        total += sum(1 if any(a <= ord(ch) <= b for a, b in _RANGOS_PESO_1) else 2 for ch in trozo)
    return total + 23 * len(_URL.findall(texto))


def longitud_len(texto: str) -> int:
    """`len()` contando cada enlace como 23 caracteres (como hace X)."""
    return len(_URL.sub("x" * 23, texto))


def cabe_en_x(texto: str) -> bool:
    """Las dos comprobaciones: len() con enlaces a 23 y el peso real de X."""
    return longitud_len(texto) <= LIMITE_X and longitud_x(texto) <= LIMITE_X


def eur(x: float, decimales: int = 0, signo: bool = False) -> str:
    """10234.5 -> '10.235 €' (formato español)."""
    s = f"{abs(x):,.{decimales}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    prefijo = ("+" if x > 0 else "-" if x < 0 else "±") if signo else ("-" if x < 0 else "")
    return f"{prefijo}{s} €"


def pct(x: float, decimales: int = 1, signo: bool = False) -> str:
    s = f"{abs(x) * 100:.{decimales}f}".replace(".", ",")
    prefijo = ("+" if x > 0 else "-" if x < 0 else "±") if signo else ("-" if x < 0 else "")
    return f"{prefijo}{s} %"


def num(x: float, decimales: int = 4) -> str:
    return f"{x:.{decimales}f}".replace(".", ",")


# =============================================================================
# Estado del día
# =============================================================================

@dataclass
class EstadoCarteraDia:
    equity: float
    resultado_dia: float
    resultado_dia_pct: float
    acumulado_pct: float
    caida_actual: float
    caida_maxima: float
    exposicion: float
    posiciones: dict = field(default_factory=dict)
    ordenes_hoy: list = field(default_factory=list)
    ordenes_total: int = 0
    salidas_total: int = 0
    comisiones: float = 0.0
    slippage: float = 0.0


@dataclass
class EstadoDia:
    fecha: str                    # cierre en el que se decidió
    fecha_apertura: str           # apertura en la que se ejecutó (momento de la valoración)
    dia: int
    carteras: dict
    regimen: dict
    motivo: dict
    velas_perdidas: int
    avisos: list
    parada: bool
    hash_dia: str
    lineas_registro: int
    series: pd.DataFrame          # valor tras la apertura de cada día, por cartera (incluye BH100)

    def a_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "series"}
        d["carteras"] = {k: v.__dict__ for k, v in self.carteras.items()}
        d["aviso"] = NOTA
        return d


def _caidas(serie: pd.Series) -> tuple[float, float]:
    pico = np.maximum.accumulate(np.maximum(serie.to_numpy(), CAPITAL))
    caida = 1 - serie.to_numpy() / pico
    return float(caida[-1]), float(caida.max())


def construir_estado(eventos: list[dict], hash_dia: str, comision: float, slippage: float) -> Optional[EstadoDia]:
    """Estado del día tras la última decisión ya EJECUTADA. None si aún no hay ninguna (día 0).

    Fe de erratas 1 (2026-10-05, ver CAMBIOS.md): cada día se valora la cartera
    JUSTO DESPUÉS de ejecutar las órdenes de la decisión, al precio de apertura
    al que se ejecutaron. Así el capital, las comisiones, las posiciones y la
    exposición describen el mismo instante. (La versión anterior valoraba al
    cierre previo a la orden, pero sumaba ya las comisiones de esa orden.)
    """
    por_tipo: dict[str, list[dict]] = {}
    for e in eventos:
        por_tipo.setdefault(e["tipo"], []).append(e["datos"])
    decisiones = [d for d in por_tipo.get("decision", []) if d["cartera"] == "V8"]
    if not decisiones:
        return None
    inicio = por_tipo["inicio"][0]
    pares = list(inicio["archivo_inicial"])
    ejecuciones = por_tipo.get("ejecucion", [])

    # Precio de apertura en el que se ejecutó cada decisión (está en `ejecucion` y en `sin_orden`).
    aperturas: dict[str, dict[str, float]] = {}
    for e in ejecuciones + por_tipo.get("sin_orden", []):
        aperturas.setdefault(e["fecha_decision"], {})[e["par"]] = e.get("apertura", e.get("precio_referencia"))
    fechas_decision = sorted({d["fecha"] for d in decisiones})
    completas = [f for f in fechas_decision if all(p in aperturas.get(f, {}) for p in pares)]
    if not completas:
        return None
    fecha = completas[-1]

    def mas_un_dia(iso: str) -> str:
        return (pd.Timestamp(iso) + pd.Timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Posiciones tras cada decisión ejecutada, valoradas a su precio de apertura.
    fecha_base = mas_un_dia(max(v["ultima_vela"] for v in inicio["archivo_inicial"].values()))
    tenencias = {(c, p): (CAPITAL / len(pares), 0.0) for c in ("V8", "FIJO30") for p in pares}
    filas = {fecha_base: {"V8": CAPITAL, "FIJO30": CAPITAL, "BH100": CAPITAL}}
    primera = aperturas[completas[0]]
    unidades_bh = {p: CAPITAL / len(pares) / (primera[p] * (1 + slippage) * (1 + comision)) for p in pares}
    for f in completas:
        for e in ejecuciones:
            if e["fecha_decision"] == f:
                tenencias[(e["cartera"], e["par"])] = (e["efectivo_despues"], e["unidades_despues"])
        apertura = aperturas[f]
        fila = {c: sum(tenencias[(c, p)][0] + tenencias[(c, p)][1] * apertura[p] for p in pares) for c in ("V8", "FIJO30")}
        fila["BH100"] = sum(unidades_bh[p] * apertura[p] for p in pares)
        filas[mas_un_dia(f)] = fila
    series = pd.DataFrame.from_dict(filas, orient="index").sort_index()

    carteras = {}
    ultima_apertura = aperturas[fecha]
    for c in ("V8", "FIJO30", "BH100"):
        s = series[c]
        actual, maxima = _caidas(s)
        previo = s.iloc[-2] if len(s) > 1 else CAPITAL
        estado = EstadoCarteraDia(
            equity=float(s.iloc[-1]), resultado_dia=float(s.iloc[-1] - previo),
            resultado_dia_pct=float(s.iloc[-1] / previo - 1), acumulado_pct=float(s.iloc[-1] / CAPITAL - 1),
            caida_actual=actual, caida_maxima=maxima, exposicion=1.0 if c == "BH100" else 0.0,
        )
        if c != "BH100":
            invertido = sum(tenencias[(c, p)][1] * ultima_apertura[p] for p in pares)
            estado.exposicion = invertido / estado.equity if estado.equity > 0 else 0.0
            estado.posiciones = {p: {"unidades": tenencias[(c, p)][1], "valor": tenencias[(c, p)][1] * ultima_apertura[p]}
                                 for p in pares if tenencias[(c, p)][1] > 0}
            propias = [e for e in ejecuciones if e["cartera"] == c and e["fecha_decision"] <= fecha]
            estado.ordenes_hoy = [e for e in propias if e["fecha_decision"] == fecha]
            estado.ordenes_total = len(propias)
            estado.salidas_total = sum(1 for e in propias if e["motivo"] == "salida")
            estado.comisiones = float(sum(e["comision"] for e in propias))
            estado.slippage = float(sum(e["slippage"] for e in propias))
        carteras[c] = estado

    hoy = [d for d in decisiones if d["fecha"] == fecha]
    dia = fechas_decision.index(fecha) + 1
    avisos = [a for a in por_tipo.get("alerta", []) if a.get("fecha", "") >= fechas_decision[-min(7, len(fechas_decision))]]
    return EstadoDia(
        fecha=fecha, fecha_apertura=mas_un_dia(fecha), dia=dia, carteras=carteras,
        regimen={d["par"]: d["regimen"] for d in hoy}, motivo={d["par"]: d["motivo"] for d in hoy},
        velas_perdidas=len(por_tipo.get("vela_perdida", [])), avisos=avisos,
        parada=bool(por_tipo.get("parada")), hash_dia=hash_dia, lineas_registro=len(eventos), series=series,
    )


# =============================================================================
# Textos
# =============================================================================

def _orden_corta(o: dict) -> str:
    activo = o["par"].split("/")[0]
    verbo = {"compra": "compra", "venta": "venta"}[o["lado"]]
    tipo = {"entrada": "entrada", "salida": "salida", "reajuste": "reajuste", "fin_de_datos": "cierre"}[o["motivo"]]
    return f"{verbo} de {activo} ({tipo})"


def _frase_contexto(e: EstadoDia) -> str:
    v8 = e.carteras["V8"]
    if e.parada:
        return "La V8 está DETENIDA por la regla de parada pre-registrada."
    if v8.ordenes_hoy:
        return "Hoy: " + ", ".join(_orden_corta(o) for o in v8.ordenes_hoy) + "."
    if v8.exposicion == 0:
        return "La V8 sigue en efectivo: ningún sistema ve tendencia."
    return f"Sin órdenes hoy; la V8 tiene invertido un {pct(v8.exposicion, 0)}."


PLANTILLAS = (
    "Día {dia} de 90 con 10.000 € ficticios.\n\nV8: {capital} ({dia_pct} hoy, {dia_eur}). Caída desde máximo: {caida}.\n"
    "30 % fijo: {fijo}.\n\n{contexto}\n\nHash: {hash8}",
    "Día {dia} de 90. La cartera V8 vale {capital}: {dia_eur} hoy ({dia_pct}), {acum} desde el inicio. "
    "Caída actual {caida}.\nA su lado, el 30 % fijo: {fijo}.\n\n{contexto}\nHash del registro: {hash8}",
    "Parte del día {dia} de 90 (dinero ficticio).\n\nCapital V8: {capital}\nHoy: {dia_eur} ({dia_pct})\n"
    "Caída: {caida}\nRival 30 % fijo: {fijo}\n\n{contexto}\nHash {hash8}",
    "{dia} de 90. La V8 cierra en {capital} ({dia_pct} en el día). Caída desde su máximo: {caida}. "
    "El 30 % fijo, en {fijo}.\n\n{contexto} Ninguna conclusión con tan pocos días.\n\nHash: {hash8}",
    "Día {dia} de 90 con 10.000 € de mentira y cuentas de verdad.\nV8: {capital} ({dia_eur} hoy). Caída: {caida}.\n"
    "30 % fijo: {fijo}.\n{contexto}\n\nHash {hash8}",
    "Día {dia} de 90. Hoy la V8 {verbo} {dia_eur_abs} y queda en {capital} ({acum} acumulado). "
    "Caída actual {caida}. 30 % fijo: {fijo}.\n\n{contexto}\n\nHash: {hash8}",
    "Bot en paper trading, día {dia} de 90.\n\nV8 {capital} | hoy {dia_pct} | caída {caida}\n30 % fijo {fijo}\n\n"
    "{contexto}\nRegistro encadenado, hash {hash8}",
    "Día {dia} de 90. Capital de la V8: {capital}. Resultado del día: {dia_eur} ({dia_pct}). "
    "Caída desde máximo: {caida}.\nEl rival trivial (30 % fijo) va por {fijo}.\n{contexto}\n\nHash: {hash8}",
)


def tuit_diario(e: EstadoDia) -> str:
    """Tuit del día: cambia cada día (plantilla rotatoria y frase de contexto),
    con las mismas cifras clave. Sin enlaces: van en el comentario."""
    v8, fijo = e.carteras["V8"], e.carteras["FIJO30"]
    datos = dict(
        dia=e.dia, capital=eur(v8.equity), dia_pct=pct(v8.resultado_dia_pct, 2, True),
        dia_eur=eur(v8.resultado_dia, 0, True), dia_eur_abs=eur(abs(v8.resultado_dia)),
        verbo="gana" if v8.resultado_dia > 0 else "pierde" if v8.resultado_dia < 0 else "ni gana ni pierde, se queda en",
        acum=pct(v8.acumulado_pct, 1, True), caida=pct(v8.caida_actual, 1), fijo=eur(fijo.equity),
        contexto=_frase_contexto(e), hash8=e.hash_dia[:8],
    )
    for desplazamiento in range(len(PLANTILLAS)):
        texto = PLANTILLAS[(e.dia - 1 + desplazamiento) % len(PLANTILLAS)].format(**datos)
        if cabe_en_x(texto):
            return texto
    texto = PLANTILLAS[0].format(**{**datos, "contexto": ""}).replace("\n\n\n", "\n\n")
    if not cabe_en_x(texto):
        raise ValueError("Ningún tuit cabe en el límite de X.")
    return texto


def comentario_diario(e: EstadoDia, url_web: str, url_repo: str) -> str:
    texto = (f"Panel con el botón Verificar: {url_web}\nCódigo y registro: {url_repo}\n"
             f"Hash completo del día {e.dia}: {e.hash_dia}\n\n{NOTA}")
    if not cabe_en_x(texto):
        raise ValueError(f"El comentario no cabe en X ({longitud_x(texto)}).")
    return texto


def hilo_semanal(e: EstadoDia, eventos: list[dict]) -> Optional[list[str]]:
    """Hilo los días 7, 14, 21... (y el 90). None el resto de días."""
    if e.dia % 7 != 0 and e.dia != DIAS:
        return None
    semana = (e.dia + 6) // 7
    v8, fijo, bh = (e.carteras[c] for c in ("V8", "FIJO30", "BH100"))
    fechas = sorted({ev["datos"]["fecha"] for ev in eventos if ev["tipo"] == "decision"})[-7:]
    ordenes = [ev["datos"] for ev in eventos if ev["tipo"] == "ejecucion" and ev["datos"]["cartera"] == "V8"
               and ev["datos"]["fecha_decision"] in fechas]
    comision = sum(o["comision"] for o in ordenes)
    regimen = "; ".join(f"{p.split('/')[0]}: tendencia {r['tendencia']}, volatilidad {r['volatilidad']}"
                        for p, r in e.regimen.items())
    tuits = [
        f"Semana {semana} (día {e.dia} de 90) del bot con 10.000 € ficticios. Hilo con todo, también lo malo.",
        f"Capital tras {e.dia} días:\nV8: {eur(v8.equity)} ({pct(v8.acumulado_pct, 1, True)}), caída máx. {pct(v8.caida_maxima)}\n"
        f"30 % fijo: {eur(fijo.equity)} ({pct(fijo.acumulado_pct, 1, True)})\n"
        f"Comprar y mantener: {eur(bh.equity)} ({pct(bh.acumulado_pct, 1, True)}), caída máx. {pct(bh.caida_maxima)}",
        f"Esta semana la V8 hizo {len(ordenes)} órdenes ({', '.join(_orden_corta(o) for o in ordenes) or 'ninguna'}). "
        f"Comisiones de la semana: {eur(comision, 2)}; acumuladas: {eur(v8.comisiones, 2)}. "
        f"Exposición actual: {pct(v8.exposicion, 0)}.",
        f"Régimen al cierre: {regimen}. La V8 no cambia de reglas según el régimen: solo lo registra.",
        f"Integridad: {e.lineas_registro} eventos encadenados con SHA-256, {e.velas_perdidas} velas perdidas. "
        f"Hash del día: {e.hash_dia[:16]}…",
        "Recordatorio: la V8 salió NO APTO en mi validación fuera de muestra y 90 días no demuestran nada. "
        f"{NOTA}",
    ]
    for t in tuits:
        if not cabe_en_x(t):
            raise ValueError(f"Un tuit del hilo no cabe en X ({longitud_x(t)}): {t[:60]}…")
    return tuits


def resumen_markdown(e: EstadoDia, tuit: str, comentario: str, hilo: Optional[list[str]]) -> str:
    filas = [f"# Día {e.dia} de 90 · decisión al cierre del {e.fecha[:10]}, órdenes en la apertura del "
             f"{e.fecha_apertura[:10]}", "", f"> {NOTA}", "",
             "Valores tras ejecutar las órdenes del día, al precio de apertura (comisiones y slippage incluidos).", "",
             "| Cartera | Valor | Hoy | Acumulado | Caída actual | Caída máxima | Invertido | Comisiones |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for c, s in e.carteras.items():
        comis = "—" if c == "BH100" else eur(s.comisiones, 2)
        filas.append(f"| {NOMBRES[c]} | {eur(s.equity, 2)} | {eur(s.resultado_dia, 2, True)} ({pct(s.resultado_dia_pct, 2, True)}) | "
                     f"{pct(s.acumulado_pct, 2, True)} | {pct(s.caida_actual)} | {pct(s.caida_maxima)} | {pct(s.exposicion, 0)} | {comis} |")
    filas += ["", "## Qué ve y qué hace la V8", ""]
    for par, m in e.motivo.items():
        r = e.regimen[par]
        filas.append(f"- **{par}** · régimen: tendencia {r['tendencia']}, volatilidad {r['volatilidad']}, "
                     f"fuerza {ETIQUETA.get(r['fuerza'], r['fuerza'])}. {m}")
    v8 = e.carteras["V8"]
    filas += ["", f"Posiciones abiertas: " + (", ".join(f"{p} {num(x['unidades'], 6)} ({eur(x['valor'])})"
                                                   for p, x in v8.posiciones.items()) or "ninguna (efectivo)"),
              f"Órdenes de hoy: " + (", ".join(f"{_orden_corta(o)}: {num(o['unidades'], 6)} a {eur(o['precio_efectivo'], 2)} "
                                               f"(comisión {eur(o['comision'], 2)}, slippage {eur(o['slippage'], 2)})"
                                               for o in v8.ordenes_hoy) or "ninguna"),
              f"Órdenes totales: {v8.ordenes_total} · salidas cerradas: {v8.salidas_total} · slippage acumulado {eur(v8.slippage, 2)}",
              f"Velas perdidas: {e.velas_perdidas} · avisos recientes: {len(e.avisos)} · parada: {'SÍ' if e.parada else 'no'}", "",
              f"Hash del día: `{e.hash_dia}`", "",
              f"## Tuit (longitud X {longitud_x(tuit)}, len() {len(tuit)})", "", "```", tuit, "```", "",
              f"## Comentario (longitud X {longitud_x(comentario)})", "", "```", comentario, "```"]
    if hilo:
        filas += ["", "## Hilo semanal", ""]
        for i, t in enumerate(hilo, 1):
            filas += [f"{i}/{len(hilo)} (longitud X {longitud_x(t)})", "", "```", t, "```", ""]
    return "\n".join(filas) + "\n"


# =============================================================================
# Imagen
# =============================================================================

def imagen_diaria(e: EstadoDia, ruta: Path) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    plt.rcParams.update({"font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"], "font.size": 11})
    s = e.series.copy()
    s.index = pd.to_datetime(s.index, utc=True)
    fig = plt.figure(figsize=(8, 4.5), dpi=200, facecolor=TINTA["superficie"])
    rejilla = fig.add_gridspec(2, 1, height_ratios=[2.3, 1], hspace=0.12, left=0.1, right=0.71, top=0.76, bottom=0.12)
    ax, axd = fig.add_subplot(rejilla[0]), fig.add_subplot(rejilla[1])
    marcadores = len(s) < 4
    caida_min = -1.0
    for c in ("BH100", "FIJO30", "V8"):   # la V8 se dibuja encima
        ancho = 1.4 if c == "BH100" else 2.0
        ax.plot(s.index, s[c], color=COLOR[c], linewidth=ancho, solid_capstyle="round", solid_joinstyle="round",
                marker="o" if marcadores else None, markersize=4, label=NOMBRES[c], zorder=3 if c == "V8" else 2)
        if c != "BH100":
            caida = -(1 - s[c] / np.maximum.accumulate(np.maximum(s[c].to_numpy(), CAPITAL))) * 100
            axd.plot(s.index, caida, color=COLOR[c], linewidth=1.6, marker="o" if marcadores else None, markersize=3)
            axd.fill_between(s.index, caida, 0, color=COLOR[c], alpha=0.10, linewidth=0)
            caida_min = min(caida_min, float(caida.min()))
    ax.axhline(CAPITAL, color=TINTA["base"], linewidth=0.8, zorder=1)

    for a in (ax, axd):
        a.set_facecolor(TINTA["superficie"])
        a.grid(axis="y", color=TINTA["rejilla"], linewidth=0.6)
        a.tick_params(colors=TINTA["tenue"], labelsize=8, length=0)
        for lado in ("top", "right", "left"):
            a.spines[lado].set_visible(False)
        a.spines["bottom"].set_color(TINTA["base"])
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: eur(v)))
    axd.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f} %"))
    axd.set_ylim(caida_min * 1.25, 0.5)
    ax.tick_params(labelbottom=False)
    if len(s) <= 8:      # pocos días: una marca por fecha real, sin repetidas
        axd.set_xticks(s.index)
    else:
        axd.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=7))
    axd.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    axd.set_ylabel("Caída", color=TINTA["secundaria"], fontsize=8.5)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), frameon=False, fontsize=8.5, ncol=3,
              labelcolor=TINTA["secundaria"], borderaxespad=0.2)

    # Etiquetas al final de cada línea, en tinta de texto (nunca en el color de la serie). Se colocan a la
    # derecha del eje; si chocan, se separan en vertical y se unen a su línea con un conector fino.
    abajo, arriba = ax.get_ylim()
    hueco = (arriba - abajo) * 0.11
    finales = sorted(((float(s[c].iloc[-1]), c) for c in ("V8", "FIJO30", "BH100")), reverse=True)
    posiciones, previa = [], None
    for valor, c in finales:
        y = valor if previa is None else min(valor, previa - hueco)
        posiciones.append((valor, y, c))
        previa = y
    for valor, y, c in posiciones:
        ax.annotate(f"{NOMBRES[c]}  {eur(valor)}", xy=(s.index[-1], valor), xytext=(1.02, y),
                    textcoords=ax.get_yaxis_transform(), va="center", fontsize=8, annotation_clip=False,
                    color=TINTA["primaria"] if c == "V8" else TINTA["secundaria"],
                    arrowprops=dict(arrowstyle="-", color=TINTA["base"], linewidth=0.6, shrinkA=0, shrinkB=2))
    v8 = e.carteras["V8"]
    fig.text(0.1, 0.94, f"Día {e.dia} de 90 · V8: {eur(v8.equity)} ({pct(v8.acumulado_pct, 1, True)})",
             fontsize=14, color=TINTA["primaria"], weight="bold", va="top")
    fa = e.fecha_apertura
    fig.text(0.1, 0.875, f"Valor tras la apertura del {fa[8:10]}/{fa[5:7]}/{fa[:4]} · curva completa desde el día 0 · "
             f"caída actual {pct(v8.caida_actual)}, máxima {pct(v8.caida_maxima)}", fontsize=9,
             color=TINTA["secundaria"], va="top")
    fig.text(0.1, 0.03, f"{NOTA} · hash {e.hash_dia[:16]}", fontsize=7, color=TINTA["tenue"])
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ruta, facecolor=TINTA["superficie"], metadata={"Software": None})
    plt.close(fig)
    return ruta


# =============================================================================
# Todo junto
# =============================================================================

def generar_salidas(raiz_vivo: Path, comision: float, slippage: float, url_web: str, url_repo: str) -> Optional[Path]:
    """Escribe vivo/diario/<fecha>/ con resumen.json, resumen.md, tuit.txt,
    comentario.txt, imagen.png e hilo.txt (los días que toca)."""
    from modulo_7_registro import Registro

    registro = Registro(raiz_vivo / "registro.jsonl")
    eventos = registro.eventos()
    estado = construir_estado(eventos, registro.verificar().ultimo_hash, comision, slippage)
    if estado is None:
        return None
    carpeta = raiz_vivo / "diario" / estado.fecha[:10]
    carpeta.mkdir(parents=True, exist_ok=True)
    tuit = tuit_diario(estado)
    comentario = comentario_diario(estado, url_web, url_repo)
    hilo = hilo_semanal(estado, eventos)
    (carpeta / "resumen.json").write_text(json.dumps(estado.a_dict(), indent=2, ensure_ascii=False, default=float) + "\n",
                                          encoding="utf-8", newline="\n")
    (carpeta / "resumen.md").write_text(resumen_markdown(estado, tuit, comentario, hilo), encoding="utf-8", newline="\n")
    (carpeta / "tuit.txt").write_text(tuit + "\n", encoding="utf-8", newline="\n")
    (carpeta / "comentario.txt").write_text(comentario + "\n", encoding="utf-8", newline="\n")
    if hilo:
        (carpeta / "hilo.txt").write_text("\n\n---\n\n".join(hilo) + "\n", encoding="utf-8", newline="\n")
    imagen_diaria(estado, carpeta / "imagen.png")
    return carpeta
