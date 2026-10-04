"""
Genera `datos/<version>/CALIDAD.md`: fuentes, comparaciones, incidencias,
tramos de la partición y mapa DESCRIPTIVO de épocas de mercado.

No ejecuta ninguna estrategia: solo describe precios. Uso:
    .venv\\Scripts\\python scripts\\informe_datos.py --version v1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modulo_1b_historico import RAIZ_DATOS, cargar_historico  # noqa: E402

# Tramos de VALIDACION.md (fin exclusiva) y calentamiento de la v5 (D-010).
TRAMOS = [
    ("Desarrollo", "2015-01-01", "2022-01-01"),
    ("Validación", "2022-01-01", "2024-07-01"),
    ("Reserva final", "2024-07-01", "2026-05-01"),
    ("Contaminado (v1-v4)", "2026-05-01", "2026-10-01"),
]
VELAS_CALENTAMIENTO = 400
UMBRAL_CICLO = 0.20   # caídas desde máximo histórico de más del 20 % se listan como ciclo


def ciclos_de_caida(cierre: pd.Series, umbral: float) -> list[dict]:
    """Ciclos máximo histórico -> mínimo -> recuperación del máximo, con caída > umbral."""
    maximo = cierre.cummax()
    ciclos, en_ciclo, inicio = [], False, None
    for fecha, valor in cierre.items():
        if not en_ciclo and valor < maximo[fecha]:
            en_ciclo, inicio = True, maximo[:fecha].idxmax()
        elif en_ciclo and valor >= maximo[fecha] and fecha != inicio:
            tramo = cierre[inicio:fecha]
            ciclos.append((inicio, tramo.idxmin(), fecha, tramo.min() / cierre[inicio] - 1))
            en_ciclo = False
    if en_ciclo:
        tramo = cierre[inicio:]
        ciclos.append((inicio, tramo.idxmin(), None, tramo.min() / cierre[inicio] - 1))
    return [
        {"maximo": a, "minimo": b, "recupera": c, "caida": d} for a, b, c, d in ciclos if d <= -umbral
    ]


def tabla_anual(df: pd.DataFrame) -> str:
    filas = ["| Año | Rentabilidad | Volatilidad anualizada | Caída máx. en el año | Cierre > SMA200 |",
             "|-----|-------------:|-----------------------:|---------------------:|----------------:|"]
    sma = df["Close"].rolling(200).mean()
    for anio, g in df.groupby(df.index.year):
        c = g["Close"]
        r = np.log(c).diff().dropna()
        dd = (c / c.cummax() - 1).min()
        encima = (c > sma.loc[g.index]).mean() if sma.loc[g.index].notna().any() else float("nan")
        parcial = " (parcial)" if len(g) < 360 else ""
        filas.append(f"| {anio}{parcial} | {c.iloc[-1] / c.iloc[0] - 1:+.0%} | {r.std() * np.sqrt(365):.0%} | "
                     f"{dd:.0%} | {'—' if np.isnan(encima) else f'{encima:.0%}'} |")
    return "\n".join(filas)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v1")
    args = ap.parse_args()
    directorio = RAIZ_DATOS / args.version
    m = json.loads((directorio / "MANIFIESTO.json").read_text(encoding="utf-8"))

    lineas = [
        f"# Calidad de datos · versión {m['version']}",
        "",
        f"Creada {m['creado_utc']} con el commit `{m['commit_codigo'][:10]}`. Rango pedido "
        f"{m['rango_pedido']['inicio']} → {m['rango_pedido']['fin_exclusiva']} (exclusiva), velas "
        f"{m['intervalo']}, {m['convencion']}. Fuente principal **{m['principal']}**, respaldo "
        f"**{m['respaldo']}**. Checksums SHA-256 en `MANIFIESTO.json`.",
        "",
        "> Dinero ficticio, no es asesoramiento financiero, resultados pasados no garantizan nada.",
    ]

    for simbolo, info in m["simbolos"].items():
        df = cargar_historico(simbolo, m["intervalo"], m["version"])
        lineas += ["", f"## {simbolo}", "", "### Fuentes", "",
                   "| Fuente | Proveedor | Velas | Desde | Hasta | Huecos | OHLC incoherente | Volumen 0 | Movimientos > 25 % |",
                   "|--------|-----------|------:|-------|-------|-------:|-----------------:|----------:|-------------------|"]
        for nombre, c in info["fuentes"].items():
            if "error" in c:
                lineas.append(f"| {nombre} | — | error: {c['error'][:60]} | | | | | | |")
                continue
            extremos = ", ".join(f"{f} ({v:+.0%})" for f, v in c["movimientos_extremos"].items()) or "—"
            lineas.append(f"| {nombre} | `{c['proveedor']}` | {c['velas']} | {c['desde'][:10]} | {c['hasta'][:10]} | "
                          f"{c['huecos']} | {c['ohlc_incoherente']} | {c['volumen_cero']} | {extremos} |")
        lineas += ["", f"### Comparación de cierres contra {m['principal']}", "",
                   "| Fuente | Días comunes | Mediana | p95 | Máximo | Días > 2 % | Peores días |",
                   "|--------|-------------:|--------:|----:|-------:|-----------:|-------------|"]
        for nombre, c in info["comparaciones"].items():
            if not c.get("dias_comunes"):
                continue
            peores = ", ".join(f"{f} ({v:.1f} %)" for f, v in list(c["peores_dias"].items())[:4])
            lineas.append(f"| {nombre.split('_vs_')[0]} | {c['dias_comunes']} | {c['mediana_dif_pct']:.3f} % | "
                          f"{c['p95_dif_pct']:.3f} % | {c['max_dif_pct']:.2f} % | {c['dias_dif_mayor_2pct']} | {peores} |")
        lineas += ["", "### Incidencias de la serie limpia", ""]
        lineas += [f"- {i['fecha']} · {i['tipo']}: {i['accion']}" for i in info["incidencias"]] or ["- Ninguna."]
        sl = info["serie_limpia"]
        lineas += ["", f"Serie limpia: {sl['velas']} velas, {sl['desde'][:10]} → {sl['hasta'][:10]}, "
                   f"huecos {sl['huecos']}, OHLC incoherente {sl['ohlc_incoherente']}, filas por fuente "
                   f"{sl['filas_por_fuente']}."]

        primera_operable = df.index[min(VELAS_CALENTAMIENTO, len(df) - 1)]
        lineas += ["", "### Cobertura de los tramos de la partición", "",
                   f"Con {VELAS_CALENTAMIENTO} velas de calentamiento (D-010), el primer día operable es "
                   f"**{primera_operable:%Y-%m-%d}**.", "",
                   "| Tramo | Fechas | Velas | Velas operables |", "|-------|--------|------:|----------------:|"]
        for nombre, ini, fin in TRAMOS:
            en_tramo = df[(df.index >= pd.Timestamp(ini, tz="UTC")) & (df.index < pd.Timestamp(fin, tz="UTC"))]
            operables = int((en_tramo.index >= primera_operable).sum())
            lineas.append(f"| {nombre} | {ini} → {fin} | {len(en_tramo)} | {operables} |")

        lineas += ["", "### Mapa descriptivo de épocas", "",
                   "Solo describe precios; no se ha usado para ajustar nada. Ojo: describir el tramo de "
                   "validación y la reserva no los contamina para la estrategia mientras ninguna regla se "
                   "elija mirándolos; aun así se deja constancia.", "", tabla_anual(df), "",
                   f"Ciclos de caída desde máximo histórico de más del {UMBRAL_CICLO:.0%}:", "",
                   "| Máximo | Mínimo | Caída | Recupera el máximo |", "|--------|--------|------:|--------------------|"]
        for c in ciclos_de_caida(df["Close"], UMBRAL_CICLO):
            recupera = c["recupera"].strftime("%Y-%m-%d") if c["recupera"] is not None else "aún no"
            lineas.append(f"| {c['maximo']:%Y-%m-%d} | {c['minimo']:%Y-%m-%d} | {c['caida']:.0%} | {recupera} |")

    ruta = directorio / "CALIDAD.md"
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8", newline="\n")
    print(f"Informe: {ruta}")


if __name__ == "__main__":
    main()
