"""
Fase 2 · Diagnóstico por regímenes en el tramo de DESARROLLO.

Aplica exactamente los criterios de `informes/fase2/CRITERIOS.md` (fijados
antes de ejecutar) y escribe los resultados en `informes/fase2/`.

Uso (PowerShell):
    .venv\\Scripts\\python scripts\\fase2_regimenes.py
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main  # noqa: E402
from modulo_2_estrategia import generar_senales  # noqa: E402
from modulo_4_backtesting import MotorBacktest  # noqa: E402
from modulo_4b_exposicion import benchmark_exposicion_constante  # noqa: E402
from modulo_5_regimenes import (  # noqa: E402
    DIMENSIONES,
    SIN_DATOS,
    bootstrap_por_bloques,
    clasificar_regimenes,
    diferencia_anual,
    media_anual_en,
    resumen_por_regimen,
)

logging.disable(logging.INFO)

FIN_DESARROLLO = "2022-01-01"
ACTIVOS = ("BTC/EUR", "ETH/EUR")
PARES = {
    "regimen_tendencia": ("alcista", "bajista"),
    "regimen_volatilidad": ("alta", "baja"),
    "regimen_fuerza": ("fuerte", "debil"),
}
MIN_DIAS = 60
N_BOOT, BLOQUE, SEMILLA, NIVEL = 5000, 20, 12345, 0.90
SALIDA = Path(__file__).resolve().parents[1] / "informes" / "fase2"


def metricas_curva(curva: pd.Series) -> dict:
    r = curva.pct_change().dropna()
    anios = (curva.index[-1] - curva.index[0]).days / 365.25
    abajo = np.sqrt(np.mean(np.minimum(r.to_numpy(), 0) ** 2))
    return {
        "rent_total_pct": (curva.iloc[-1] / curva.iloc[0] - 1) * 100,
        "cagr_pct": ((curva.iloc[-1] / curva.iloc[0]) ** (1 / anios) - 1) * 100,
        "vol_anual_pct": r.std() * np.sqrt(365) * 100,
        "sharpe": r.mean() / r.std() * np.sqrt(365) if r.std() > 0 else 0.0,
        "sortino": r.mean() / abajo * np.sqrt(365) if abajo > 0 else 0.0,
        "max_dd_pct": ((curva / curva.cummax()) - 1).min() * 100,
    }


def ic(muestras: np.ndarray) -> tuple[float, float]:
    m = muestras[~np.isnan(muestras)]
    return float(np.quantile(m, (1 - NIVEL) / 2)), float(np.quantile(m, 1 - (1 - NIVEL) / 2))


def main_fase2() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    config = main.Configuracion(fecha_fin=FIN_DESARROLLO)
    filas_globales, por_activo, curvas = [], {}, {}

    for activo in ACTIVOS:
        datos = main.obtener_velas(config, activo)
        assert datos.index.max() < pd.Timestamp(FIN_DESARROLLO, tz="UTC"), "fuga del tramo de validación"
        v8 = main.ejecutar_conjunto(config, activo, datos=datos)
        senales_v7 = generar_senales(datos, **main.kwargs_senales(config))
        v7 = MotorBacktest(main.parametros_backtest(config, activo)).ejecutar(senales_v7)
        base = main.preparar_conjunto(config, datos)
        params = main.parametros_exposicion(config, activo)
        bh = benchmark_exposicion_constante(base, params, 1.0, activo)
        bh_igual = benchmark_exposicion_constante(base, params, v8.metricas["exposicion_media"], activo)
        efectivo = pd.Series(config.capital_inicial, index=v8.curva_capital.index)
        assert v7.curva_capital.index[0] == v8.curva_capital.index[0] == bh.curva_capital.index[0]

        candidatos = {
            "V8 conjunto + vol 40 %": (v8.curva_capital, v8.metricas),
            "V7 v5 Donchian 20/10 + EMA200": (v7.curva_capital, v7.metricas),
            "Comprar y mantener 100 %": (bh.curva_capital, bh.metricas),
            f"Comprar y mantener {v8.metricas['exposicion_media']:.0%} (misma exposición)": (
                bh_igual.curva_capital, bh_igual.metricas),
            "Efectivo": (efectivo, {}),
        }
        for nombre, (curva, m) in candidatos.items():
            fila = {"activo": activo, "estrategia": nombre, **metricas_curva(curva)}
            fila.update({k: m.get(k, np.nan) for k in (
                "exposicion_media", "num_trades", "profit_factor", "win_rate_pct",
                "comisiones_totales", "num_ordenes", "rotacion_anual")})
            filas_globales.append(fila)
        curvas[activo] = {k: v[0] for k, v in candidatos.items() if k != "Efectivo"}

        regimenes = clasificar_regimenes(datos).loc[v8.curva_capital.index]
        mercado = datos["Close"].pct_change().loc[v8.curva_capital.index]
        por_activo[activo] = {
            "ret_v8": v8.curva_capital.pct_change(),
            "ret_v7": v7.curva_capital.pct_change(),
            "mercado": mercado,
            "exposicion": v8.exposicion,
            "regimenes": regimenes,
        }
        v8_ep = v8.episodios
        print(f"{activo}: {len(v8.curva_capital)} días operables | V8 {len(v8_ep)} episodios, "
              f"{v8.metricas['num_ordenes']} órdenes | V7 {v7.metricas['num_trades']} operaciones")

    tabla_global = pd.DataFrame(filas_globales)
    tabla_global.to_csv(SALIDA / "metricas_desarrollo.csv", index=False, float_format="%.4f")

    # ---------------------------------------------------- análisis por régimen
    lineas_reg, veredictos = [], {}
    for dim in DIMENSIONES:
        lineas_reg += ["", f"### {dim.replace('regimen_', '').capitalize()}", ""]
        for activo, d in por_activo.items():
            for clave, nombre in (("ret_v8", "V8"), ("ret_v7", "V7")):
                t = resumen_por_regimen(d[clave], d["mercado"], d["exposicion"], d["regimenes"][dim])
                t.to_csv(SALIDA / f"regimen_{dim}_{activo.replace('/', '-')}_{nombre}.csv", float_format="%.4f")
            t8 = resumen_por_regimen(d["ret_v8"], d["mercado"], d["exposicion"], d["regimenes"][dim])
            t7 = resumen_por_regimen(d["ret_v7"], d["mercado"], d["exposicion"], d["regimenes"][dim])
            lineas_reg += [f"**{activo}**", "",
                           "| Régimen | Días | % días | Exposición V8 | V8 rent. anual | V8 Sharpe | V7 rent. anual | Mercado rent. anual | Mercado Sharpe |",
                           "|---------|-----:|-------:|--------------:|---------------:|----------:|---------------:|--------------------:|---------------:|"]
            for reg, f in t8.iterrows():
                lineas_reg.append(
                    f"| {reg} | {int(f['dias'])} | {f['pct_dias']:.0f} % | {f['exposicion_media']:.0%} | "
                    f"{f['estrategia_rent_anual_pct']:+.0f} % | {f['estrategia_sharpe']:.2f} | "
                    f"{t7.loc[reg, 'estrategia_rent_anual_pct']:+.0f} % | {f['comprar_mantener_rent_anual_pct']:+.0f} % | "
                    f"{f['comprar_mantener_sharpe']:.2f} |")
            lineas_reg.append("")

        # Series para los criterios: (retorno V8 del día t, régimen al cierre t-1)
        def serie(activo, desde=None, hasta=None):
            d = por_activo[activo]
            df = pd.DataFrame({"r": d["ret_v8"], "g": d["regimenes"][dim].shift(1)}).dropna()
            df = df[df["g"] != SIN_DATOS]
            if desde is not None:
                df = df[df.index >= desde]
            if hasta is not None:
                df = df[df.index < hasta]
            return df

        mitades = {}
        for activo in ACTIVOS:
            s = serie(activo)
            corte = s.index[0] + (s.index[-1] - s.index[0]) / 2
            mitades[activo] = (serie(activo, hasta=corte), serie(activo, desde=corte))
        conjunto = pd.concat([serie(a) for a in ACTIVOS])
        r_c, g_c = conjunto["r"].to_numpy(), conjunto["g"].to_numpy(dtype=str)
        submuestras = {f"{a} mitad {i + 1}": m for a in ACTIVOS for i, m in enumerate(mitades[a])}
        submuestras.update({a: serie(a) for a in ACTIVOS})

        a, b = PARES[dim]
        dif = bootstrap_por_bloques(r_c, g_c, diferencia_anual(a, b), N_BOOT, BLOQUE, SEMILLA)
        punto = diferencia_anual(a, b)(r_c, g_c)
        signos, insuficiente = {}, []
        for nombre, sm in submuestras.items():
            for reg in (a, b):
                if (sm["g"] == reg).sum() < MIN_DIAS:
                    insuficiente.append(f"{reg} en {nombre} ({int((sm['g'] == reg).sum())} días)")
            signos[nombre] = np.sign(diferencia_anual(a, b)(sm["r"].to_numpy(), sm["g"].to_numpy(dtype=str)))
        lo, hi = ic(dif)
        a_cumple = (lo > 0 or hi < 0) and len(set(signos.values()) - {0.0}) == 1 and not insuficiente
        apagables = {}
        for reg in sorted(set(g_c)):
            boot = bootstrap_por_bloques(r_c, g_c, media_anual_en(reg), N_BOOT, BLOQUE, SEMILLA)
            lo_r, hi_r = ic(boot)
            negativos = all(
                media_anual_en(reg)(sm["r"].to_numpy(), sm["g"].to_numpy(dtype=str)) < 0
                for sm in submuestras.values() if (sm["g"] == reg).sum() >= MIN_DIAS
            )
            pocos = [n for n, sm in submuestras.items() if (sm["g"] == reg).sum() < MIN_DIAS]
            apagables[reg] = {
                "media_anual_pct": media_anual_en(reg)(r_c, g_c) * 100,
                "ic90_pct": (lo_r * 100, hi_r * 100),
                "cumple_B": bool(hi_r < 0 and negativos and not pocos),
                "submuestras_insuficientes": pocos,
            }
        veredictos[dim] = {
            "par": f"{a} - {b}",
            "diferencia_anual_pct": punto * 100,
            "ic90_pct": (lo * 100, hi * 100),
            "signos": {k: int(v) for k, v in signos.items()},
            "insuficiente": insuficiente,
            "cumple_A": bool(a_cumple),
            "regimenes": apagables,
        }

    justificada = any(
        any(r["cumple_B"] for r in v["regimenes"].values()) for v in veredictos.values()
    ) or veredictos["regimen_volatilidad"]["cumple_A"] or veredictos["regimen_fuerza"]["cumple_A"]
    (SALIDA / "veredicto.json").write_text(
        json.dumps({"fase3_justificada": justificada, "dimensiones": veredictos}, indent=2,
                   ensure_ascii=False, default=float) + "\n", encoding="utf-8", newline="\n")

    # --------------------------------------------------------------- gráfico
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ejes = plt.subplots(2, 1, figsize=(11, 8))
    for eje, (activo, cs) in zip(ejes, curvas.items()):
        for nombre, c in cs.items():
            eje.plot(c.index, c.values / c.iloc[0] * 10_000, label=nombre, linewidth=1.2)
        eje.set_yscale("log")
        eje.set_title(f"{activo} · tramo de desarrollo (log)")
        eje.grid(alpha=0.3)
        eje.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(SALIDA / "curvas_desarrollo.png", dpi=120)
    plt.close(fig)

    # --------------------------------------------------------------- informe
    lineas = ["# Fase 2 · Resultados en el tramo de desarrollo", "",
              "> Dinero ficticio, no es asesoramiento financiero, resultados pasados no garantizan nada.", "",
              "Criterios fijados antes de ejecutar: [`CRITERIOS.md`](CRITERIOS.md). Solo datos hasta el "
              f"{FIN_DESARROLLO} (exclusiva). Costes: comisión 0,80 % y slippage 0,10 % por orden.", "",
              "## Rendimiento global", "",
              "| Activo | Estrategia | Rent. total | CAGR | Vol. | Sharpe | Sortino | Máx. DD | Exposición media | Nº ops/episodios | PF | Comisiones € |",
              "|--------|------------|-----------:|-----:|-----:|-------:|--------:|--------:|-----------------:|-----------------:|---:|------------:|"]
    for _, f in tabla_global.iterrows():
        exp = "—" if np.isnan(f["exposicion_media"]) else f"{f['exposicion_media']:.0%}"
        nops = "—" if np.isnan(f["num_trades"]) else f"{int(f['num_trades'])}"
        pf = "—" if np.isnan(f["profit_factor"]) else f"{f['profit_factor']:.2f}"
        com = "—" if np.isnan(f["comisiones_totales"]) else f"{f['comisiones_totales']:,.0f}"
        lineas.append(f"| {f['activo']} | {f['estrategia']} | {f['rent_total_pct']:+,.0f} % | {f['cagr_pct']:+.1f} % | "
                      f"{f['vol_anual_pct']:.0f} % | {f['sharpe']:.2f} | {f['sortino']:.2f} | {f['max_dd_pct']:.0f} % | "
                      f"{exp} | {nops} | {pf} | {com} |")
    lineas += ["", "![Curvas](curvas_desarrollo.png)", "", "## Rendimiento por régimen", *lineas_reg,
               "## Aplicación de los criterios (variante 8)", ""]
    for dim, v in veredictos.items():
        lineas += [f"**{dim.replace('regimen_', '').capitalize()}** ({v['par']}): diferencia anual "
                   f"{v['diferencia_anual_pct']:+.0f} puntos, IC 90 % [{v['ic90_pct'][0]:+.0f}, {v['ic90_pct'][1]:+.0f}] · "
                   f"signos por submuestra {v['signos']} · insuficiente: {v['insuficiente'] or 'no'} · "
                   f"**(A) {'CUMPLE' if v['cumple_A'] else 'no cumple'}**", ""]
        for reg, r in v["regimenes"].items():
            lineas.append(f"- {reg}: media anual {r['media_anual_pct']:+.0f} %, IC 90 % "
                          f"[{r['ic90_pct'][0]:+.0f}, {r['ic90_pct'][1]:+.0f}] · (B) "
                          f"{'CUMPLE' if r['cumple_B'] else 'no cumple'}"
                          f"{' · submuestras con menos de 60 días: ' + ', '.join(r['submuestras_insuficientes']) if r['submuestras_insuficientes'] else ''}")
        lineas.append("")
    lineas += ["## Veredicto", "",
               f"**Fase 3 {'JUSTIFICADA' if justificada else 'NO JUSTIFICADA'}** según los criterios pre-registrados."]
    (SALIDA / "RESULTADOS.md").write_text("\n".join(lineas) + "\n", encoding="utf-8", newline="\n")
    print(f"Fase 3 justificada: {justificada}. Informe en {SALIDA / 'RESULTADOS.md'}")


if __name__ == "__main__":
    main_fase2()
