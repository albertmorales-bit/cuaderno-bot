"""
Fase 4 · Robustez en el tramo de DESARROLLO (criterio C6 y contexto).

Ventanas anuales independientes, sensibilidad a costes, rejilla de
parámetros (meseta), bootstrap de métricas, Sharpe deflactado, PBO de la
rejilla y actividad esperada en 90 días. Nada de esto mira la validación.

Uso: .venv\\Scripts\\python scripts\\fase4_desarrollo.py
"""

from __future__ import annotations

import itertools
import json
import logging
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "validacion"))

import main  # noqa: E402
import pbo  # noqa: E402
from modulo_6_validacion import (  # noqa: E402
    actividad_esperada,
    bootstrap_metricas,
    ejecutar_ventana,
    metricas_diarias,
    prob_sharpe_superior,
    sharpe_deflactado,
    sumar_curvas,
)

logging.disable(logging.INFO)
FIN = "2022-01-01"
INICIO_CARTERA = "2018-07-03"     # primer día operable de ETH: los dos activos activos
INICIO_ACTIVO = {"BTC/EUR": "2016-05-31", "ETH/EUR": "2018-07-03"}
N_VARIANTES = 8
SALIDA = Path(__file__).resolve().parents[1] / "informes" / "fase4"
BASE = main.Configuracion()


def escalar(sistemas, factor):
    return tuple((int(e * factor + 0.5), int(s * factor + 0.5)) for e, s in sistemas)


def cartera(config, inicio, fin, datos):
    """Ventanas de los dos activos con 5.000 € cada uno y su suma."""
    ventanas = {a: ejecutar_ventana(config, a, inicio, fin, capital=config.capital_inicial / 2, datos=datos[a])
                for a in datos}
    curvas = {
        "V8": sumar_curvas([v.estrategia.curva_capital for v in ventanas.values()]),
        "BH100": sumar_curvas([v.comprar_mantener.curva_capital for v in ventanas.values()]),
        "BHigual": sumar_curvas([v.misma_exposicion.curva_capital for v in ventanas.values()]),
    }
    return ventanas, curvas


def fila(nombre, curva, extra=None):
    return {"nombre": nombre, **metricas_diarias(curva), **(extra or {})}


def tabla_md(filas, columnas):
    cab = "| " + " | ".join(c[0] for c in columnas) + " |"
    sep = "|" + "|".join("---" for _ in columnas) + "|"
    cuerpo = ["| " + " | ".join(fmt(f[k]) if k in f else "—" for _, k, fmt in columnas) + " |" for f in filas]
    return "\n".join([cab, sep, *cuerpo])


COLS = [("Estrategia", "nombre", str), ("Rent. total", "rent_total_pct", lambda v: f"{v:+,.0f} %"),
        ("CAGR", "cagr_pct", lambda v: f"{v:+.1f} %"), ("Vol.", "vol_anual_pct", lambda v: f"{v:.0f} %"),
        ("Sharpe", "sharpe", lambda v: f"{v:.2f}"), ("Sortino", "sortino", lambda v: f"{v:.2f}"),
        ("Máx. DD", "max_dd_pct", lambda v: f"{v:.0f} %")]


def main_desarrollo() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    datos = {a: main.obtener_velas(replace(BASE, fecha_fin=FIN), a) for a in ("BTC/EUR", "ETH/EUR")}
    for d in datos.values():
        assert d.index.max() < pd.Timestamp(FIN, tz="UTC"), "fuga del tramo de validación"
    L = ["# Fase 4 · Robustez en el tramo de desarrollo", "",
         "> Dinero ficticio, no es asesoramiento financiero, resultados pasados no garantizan nada.", "",
         "Todo con datos anteriores al 2022-01-01. Criterios: [`CRITERIOS_ACEPTACION.md`](CRITERIOS_ACEPTACION.md). "
         "Cada ventana empieza SIN posición (como el paper trading).", ""]
    resumen = {}

    # 1) Ventana completa por activo y cartera
    L += ["## 1. Desarrollo completo", ""]
    filas = []
    for a, ini in INICIO_ACTIVO.items():
        v = ejecutar_ventana(BASE, a, ini, FIN, datos=datos[a])
        filas += [fila(f"{a} V8", v.estrategia.curva_capital), fila(f"{a} BH100", v.comprar_mantener.curva_capital),
                  fila(f"{a} BHigual ({v.estrategia.metricas['exposicion_media']:.0%})", v.misma_exposicion.curva_capital)]
    ventanas_c, curvas_c = cartera(BASE, INICIO_CARTERA, FIN, datos)
    for k, c in curvas_c.items():
        filas.append(fila(f"Cartera 50/50 {k}", c))
    L += [tabla_md(filas, COLS), ""]

    r = {k: c.pct_change().dropna() for k, c in curvas_c.items()}
    boot = {k: bootstrap_metricas(r[k]) for k in ("V8", "BH100")}
    p_bh = prob_sharpe_superior(r["V8"], r["BH100"])
    p_igual = prob_sharpe_superior(r["V8"], r["BHigual"])
    dsr8 = sharpe_deflactado(r["V8"], N_VARIANTES)
    dsr35 = sharpe_deflactado(r["V8"], N_VARIANTES + 27)
    L += [f"Cartera 50/50 ({INICIO_CARTERA} → {FIN}), intervalos del 90 % por bootstrap de bloques de 20 días:", "",
          f"- V8: Sharpe [{boot['V8']['sharpe_ic'][0]:.2f}, {boot['V8']['sharpe_ic'][1]:.2f}], CAGR "
          f"[{boot['V8']['cagr_ic_pct'][0]:+.0f} %, {boot['V8']['cagr_ic_pct'][1]:+.0f} %], caída máxima "
          f"[{boot['V8']['max_dd_ic_pct'][0]:.0f} %, {boot['V8']['max_dd_ic_pct'][1]:.0f} %]",
          f"- BH100: Sharpe [{boot['BH100']['sharpe_ic'][0]:.2f}, {boot['BH100']['sharpe_ic'][1]:.2f}], caída máxima "
          f"[{boot['BH100']['max_dd_ic_pct'][0]:.0f} %, {boot['BH100']['max_dd_ic_pct'][1]:.0f} %]",
          f"- P(Sharpe V8 > BH100) = {p_bh:.2f} · P(Sharpe V8 > BHigual) = {p_igual:.2f}",
          f"- Sharpe deflactado con {N_VARIANTES} variantes: {dsr8['dsr']:.2f} (umbral de azar "
          f"{dsr8['umbral_azar_anual']:.2f} anual); contando también las 27 de la rejilla: {dsr35['dsr']:.2f}", ""]
    resumen["desarrollo"] = {"p_bh": p_bh, "p_igual": p_igual, "dsr8": dsr8, "dsr35": dsr35}

    # 2) Años independientes
    L += ["## 2. Año a año (cada año empieza sin posición)", ""]
    filas = []
    for anio in range(2017, 2022):
        ini, fin = f"{anio}-01-01", f"{anio + 1}-01-01"
        for a in ("BTC/EUR", "ETH/EUR"):
            if pd.Timestamp(ini, tz="UTC") < pd.Timestamp(INICIO_ACTIVO[a], tz="UTC"):
                continue
            v = ejecutar_ventana(BASE, a, ini, fin, datos=datos[a])
            m8, mb = metricas_diarias(v.estrategia.curva_capital), metricas_diarias(v.comprar_mantener.curva_capital)
            filas.append({"nombre": f"{anio} {a}", "v8": m8["rent_total_pct"], "bh": mb["rent_total_pct"],
                          "s8": m8["sharpe"], "sb": mb["sharpe"], "d8": m8["max_dd_pct"], "db": mb["max_dd_pct"],
                          "exp": v.estrategia.metricas["exposicion_media"]})
    L += [tabla_md(filas, [("Año y activo", "nombre", str), ("V8 rent.", "v8", lambda x: f"{x:+.0f} %"),
                           ("BH100 rent.", "bh", lambda x: f"{x:+.0f} %"), ("V8 Sharpe", "s8", lambda x: f"{x:.2f}"),
                           ("BH100 Sharpe", "sb", lambda x: f"{x:.2f}"), ("V8 DD", "d8", lambda x: f"{x:.0f} %"),
                           ("BH100 DD", "db", lambda x: f"{x:.0f} %"), ("Exposición", "exp", lambda x: f"{x:.0%}")]), ""]

    # 3) Costes
    L += ["## 3. Sensibilidad a costes (cartera 50/50)", ""]
    filas = []
    for mult in (0.5, 1.0, 2.0, 3.0):
        cfg = replace(BASE, comision_pct=BASE.comision_pct * mult, slippage_pct=BASE.slippage_pct * mult)
        _, c = cartera(cfg, INICIO_CARTERA, FIN, datos)
        filas.append(fila(f"costes x{mult:g} ({cfg.comision_pct:.2%} + {cfg.slippage_pct:.2%})", c["V8"]))
    L += [tabla_md(filas, COLS), ""]

    # 4) Rejilla (meseta, C6) y PBO
    L += ["## 4. Rejilla de parámetros (C6: meseta)", ""]
    objetivos, bandas, escalas = (0.30, 0.40, 0.50), (0.05, 0.10, 0.20), (0.75, 1.0, 1.25)
    rejilla, rent_diarias = {}, {}
    for o, b, e in itertools.product(objetivos, bandas, escalas):
        cfg = replace(BASE, objetivo_volatilidad=o, banda_reajuste=b, sistemas_donchian=escalar(BASE.sistemas_donchian, e))
        _, c = cartera(cfg, INICIO_CARTERA, FIN, datos)
        rejilla[(o, b, e)] = metricas_diarias(c["V8"])
        rent_diarias[f"vol{int(o * 100)}_banda{int(b * 100)}_esc{e}"] = c["V8"].pct_change().dropna() * 100
    central = rejilla[(0.40, 0.10, 1.0)]["sharpe"]
    vecinos = {}
    for i, valores in enumerate((objetivos, bandas, escalas)):
        for paso in (-1, 1):
            punto = [0.40, 0.10, 1.0]
            j = valores.index(punto[i]) + paso
            punto[i] = valores[j]
            vecinos[tuple(punto)] = rejilla[tuple(punto)]["sharpe"]
    c6 = all(s >= 0.8 * central for s in vecinos.values())
    sharpes = np.array([m["sharpe"] for m in rejilla.values()])
    filas = [{"nombre": f"vol {int(o * 100)} %, banda {int(b * 100)}, ventanas x{e}" + (" ← V8" if (o, b, e) == (0.40, 0.10, 1.0) else ""),
              **rejilla[(o, b, e)]} for o, b, e in rejilla]
    matriz = pd.DataFrame(rent_diarias).dropna()
    ruta_pbo = SALIDA / "rejilla_rentabilidades_diarias.csv"
    matriz.index = matriz.index.strftime("%Y-%m-%d")
    matriz.index.name = "fecha"
    matriz.round(8).to_csv(ruta_pbo, lineterminator="\n")
    nombres, valores = pbo.leer_variantes(str(ruta_pbo))
    res_pbo = pbo.pbo_cscv(nombres, valores, s=16)
    L += [tabla_md(filas, COLS), "",
          f"Sharpe de la V8: {central:.2f}. Rejilla: mínimo {sharpes.min():.2f}, mediana {np.median(sharpes):.2f}, "
          f"máximo {sharpes.max():.2f}. Vecinos: " + ", ".join(f"{k} → {v:.2f}" for k, v in vecinos.items()) + ".", "",
          f"**C6 {'SE CUMPLE' if c6 else 'NO SE CUMPLE'}**: todos los vecinos con Sharpe ≥ 0,8 x {central:.2f} = {0.8 * central:.2f}.", "",
          f"PBO de la rejilla (CSCV, 16 bloques, {res_pbo['n_combinaciones']} combinaciones): **{res_pbo['pbo']:.2f}**. "
          "Informativo: aquí no se eligió la mejor celda (la V8 se fijó antes); mide cuánto engañaría elegir "
          "\"la mejor\" de esta rejilla.", ""]
    resumen["C6"] = {"cumple": c6, "sharpe_central": central, "vecinos": {str(k): v for k, v in vecinos.items()},
                     "pbo_rejilla": res_pbo["pbo"]}

    # 5) Actividad esperada
    act = actividad_esperada([ventanas_c[a].estrategia for a in ventanas_c], dias=90)
    L += ["## 5. Actividad esperada en 90 días (cartera de 2 activos)", "",
          f"- Entradas nuevas (episodios): {act['entradas_esperadas']:.1f} de media, IC 90 % "
          f"{act['entradas_ic90'][0]}-{act['entradas_ic90'][1]}.",
          f"- Órdenes (entradas, reajustes y salidas): {act['ordenes_esperadas']:.1f} de media, IC 90 % "
          f"{act['ordenes_ic90'][0]}-{act['ordenes_ic90'][1]}.",
          "- Con tan pocas operaciones, 90 días **demuestran el proceso, no la rentabilidad**.", ""]
    resumen["actividad_90_dias"] = act

    (SALIDA / "DESARROLLO.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    (SALIDA / "desarrollo.json").write_text(json.dumps(resumen, indent=2, ensure_ascii=False, default=float) + "\n",
                                            encoding="utf-8", newline="\n")
    print(f"C6: {c6} | P(V8>BHigual) {p_igual:.2f} | DSR8 {dsr8['dsr']:.2f} | informe {SALIDA / 'DESARROLLO.md'}")


if __name__ == "__main__":
    main_desarrollo()
