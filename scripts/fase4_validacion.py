"""
Fase 4 · Apertura ÚNICA del tramo de validación (2022-01-01 → 2024-07-01).

Aplica `informes/fase4/CRITERIOS_ACEPTACION.md` (versión 1). Requisitos para
ejecutarse:
  - el flag explícito --abrir-validacion,
  - el árbol de git limpio (el código que abre la validación queda fijado),
  - que exista `informes/fase4/desarrollo.json` (criterio C6),
  - que la validación no se haya abierto antes (candado).

Uso: .venv\\Scripts\\python scripts\\fase4_validacion.py --abrir-validacion
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import main  # noqa: E402
from modulo_5_regimenes import clasificar_regimenes  # noqa: E402
from modulo_6_validacion import (  # noqa: E402
    ejecutar_ventana,
    metricas_diarias,
    prob_sharpe_superior,
    sharpe_deflactado,
    sumar_curvas,
)

logging.disable(logging.INFO)
INICIO, FIN = "2022-01-01", "2024-07-01"
N_VARIANTES = 8
SALIDA = RAIZ / "informes" / "fase4"
CANDADO = SALIDA / "VALIDACION_ABIERTA.txt"


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, check=True).stdout.strip()


def evaluar(config, datos):
    ventanas = {a: ejecutar_ventana(config, a, INICIO, FIN, capital=config.capital_inicial / 2, datos=d)
                for a, d in datos.items()}
    curvas = {
        "V8": sumar_curvas([v.estrategia.curva_capital for v in ventanas.values()]),
        "BH100": sumar_curvas([v.comprar_mantener.curva_capital for v in ventanas.values()]),
        "BHigual": sumar_curvas([v.misma_exposicion.curva_capital for v in ventanas.values()]),
    }
    return ventanas, curvas


def main_validacion() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--abrir-validacion", action="store_true")
    if not ap.parse_args().abrir_validacion:
        sys.exit("Falta --abrir-validacion. La validación se abre una sola vez: asegúrate antes.")
    if CANDADO.exists():
        sys.exit(f"La validación ya se abrió ({CANDADO.read_text(encoding='utf-8').strip()}). No se repite.")
    if git("status", "--porcelain"):
        sys.exit("El árbol de git tiene cambios sin commitear. Commitea antes de abrir la validación.")
    desarrollo = json.loads((SALIDA / "desarrollo.json").read_text(encoding="utf-8"))
    commit = git("rev-parse", "HEAD")
    CANDADO.write_text(f"abierta {pd.Timestamp.now(tz='UTC'):%Y-%m-%dT%H:%M:%SZ} con el commit {commit}\n",
                       encoding="utf-8", newline="\n")

    config = main.Configuracion()
    datos = {a: main.obtener_velas(replace(config, fecha_fin=FIN), a) for a in ("BTC/EUR", "ETH/EUR")}
    for d in datos.values():
        assert d.index.max() < pd.Timestamp(FIN, tz="UTC"), "fuga de la reserva final"
    ventanas, curvas = evaluar(config, datos)
    m = {k: metricas_diarias(c) for k, c in curvas.items()}
    r = {k: c.pct_change().dropna() for k, c in curvas.items()}

    # C1-C5
    c = {}
    c["C1"] = m["V8"]["rent_total_pct"] > 0
    c["C2"] = abs(m["V8"]["max_dd_pct"]) <= 0.5 * abs(m["BH100"]["max_dd_pct"])
    c["C3"] = m["V8"]["sharpe"] > m["BH100"]["sharpe"] and m["V8"]["sharpe"] > m["BHigual"]["sharpe"]
    por_activo = {}
    for a, v in ventanas.items():
        m8, mi = metricas_diarias(v.estrategia.curva_capital), metricas_diarias(v.misma_exposicion.curva_capital)
        mb = metricas_diarias(v.comprar_mantener.curva_capital)
        por_activo[a] = {"V8": m8, "BHigual": mi, "BH100": mb, "episodios": len(v.estrategia.episodios),
                         "ordenes": v.estrategia.metricas["num_ordenes"],
                         "exposicion_media": v.estrategia.metricas["exposicion_media"],
                         "comisiones": v.estrategia.metricas["comisiones_totales"]}
    c["C4"] = all(p["V8"]["rent_total_pct"] > 0 and p["V8"]["sharpe"] > p["BHigual"]["sharpe"] for p in por_activo.values())
    cfg2 = replace(config, comision_pct=config.comision_pct * 2, slippage_pct=config.slippage_pct * 2)
    _, curvas2 = evaluar(cfg2, datos)
    m_costes2 = metricas_diarias(curvas2["V8"])
    c["C5"] = m_costes2["rent_total_pct"] > 0
    c["C6"] = bool(desarrollo["C6"]["cumple"])

    # C7: regímenes de tendencia (días de ambos activos juntos; régimen al cierre del día anterior)
    filas = []
    for a, v in ventanas.items():
        reg = clasificar_regimenes(datos[a])["regimen_tendencia"].shift(1)
        t = pd.DataFrame({"v8": v.estrategia.curva_capital.pct_change(),
                          "bh": v.comprar_mantener.curva_capital.pct_change(), "reg": reg}).dropna()
        filas.append(t)
    t = pd.concat(filas)
    medias = t.groupby("reg")[["v8", "bh"]].mean() * 365 * 100
    dias_reg = t["reg"].value_counts().to_dict()
    c["C7"] = bool(medias.loc["bajista", "v8"] > medias.loc["bajista", "bh"] and medias.loc["alcista", "v8"] > 0)

    c = {k: bool(v) for k, v in c.items()}

    # S1-S2
    dsr = sharpe_deflactado(r["V8"], N_VARIANTES)
    p_igual = prob_sharpe_superior(r["V8"], r["BHigual"])
    p_bh = prob_sharpe_superior(r["V8"], r["BH100"])
    s1, s2 = dsr["dsr"] >= 0.90, p_igual >= 0.80
    if not all(c.values()):
        veredicto = "NO APTO"
    elif s1 and s2:
        veredicto = "APTO"
    else:
        veredicto = "APTO CON RESERVAS"
    episodios = sum(p["episodios"] for p in por_activo.values())

    # Gráfico
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, (ax, axd) = plt.subplots(2, 1, figsize=(11, 7), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})
    for k, curva in curvas.items():
        ax.plot(curva.index, curva.values, label=k, linewidth=1.3)
        axd.plot(curva.index, (curva / curva.cummax() - 1) * 100, label=k, linewidth=1.0)
    ax.axhline(config.capital_inicial, color="gray", linestyle="--", linewidth=0.8)
    ax.set_title(f"Validación {INICIO} → {FIN} · cartera 50/50 BTC/ETH en EUR · {veredicto}")
    ax.set_ylabel("Capital (€)")
    axd.set_ylabel("Drawdown (%)")
    for a_ in (ax, axd):
        a_.grid(alpha=0.3)
        a_.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(SALIDA / "validacion_curvas.png", dpi=120)
    plt.close(fig)

    def fm(mm):
        return (f"{mm['rent_total_pct']:+.1f} % | {mm['cagr_pct']:+.1f} % | {mm['vol_anual_pct']:.0f} % | "
                f"{mm['sharpe']:.2f} | {mm['sortino']:.2f} | {mm['max_dd_pct']:.0f} %")

    si = lambda b: "✅ se cumple" if b else "❌ NO se cumple"  # noqa: E731
    L = [f"# Validación (apertura única) · veredicto: **{veredicto}**", "",
         "> Dinero ficticio, no es asesoramiento financiero, resultados pasados no garantizan nada.", "",
         f"Ventana {INICIO} → {FIN} (exclusiva). Abierta con el commit `{commit[:10]}` según "
         "[`CRITERIOS_ACEPTACION.md`](CRITERIOS_ACEPTACION.md) (versión 1). Cartera 50/50 empezando sin posición. "
         f"Variantes probadas: {N_VARIANTES}.", "",
         "## Cartera", "",
         "| | Rent. total | CAGR | Vol. | Sharpe | Sortino | Máx. DD |", "|---|---:|---:|---:|---:|---:|---:|",
         f"| V8 | {fm(m['V8'])} |", f"| Comprar y mantener 100 % | {fm(m['BH100'])} |",
         f"| Comprar y mantener con la misma exposición | {fm(m['BHigual'])} |",
         f"| V8 con costes x2 | {fm(m_costes2)} |", "| Efectivo | +0.0 % | +0.0 % | 0 % | — | — | 0 % |", "",
         "![Curvas](validacion_curvas.png)", "", "## Por activo", "",
         "| Activo | Estrategia | Rent. total | CAGR | Vol. | Sharpe | Sortino | Máx. DD |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for a, p in por_activo.items():
        for k in ("V8", "BH100", "BHigual"):
            L.append(f"| {a} | {k} | {fm(p[k])} |")
    L += ["", "| Activo | Episodios | Órdenes | Exposición media | Comisiones |", "|---|---:|---:|---:|---:|"]
    L += [f"| {a} | {p['episodios']} | {p['ordenes']} | {p['exposicion_media']:.0%} | {p['comisiones']:,.0f} € |"
          for a, p in por_activo.items()]
    L += ["", "## Regímenes de tendencia (días de BTC y ETH juntos)", "",
          "| Régimen | Días | V8 rent. anual media | BH100 rent. anual media |", "|---|---:|---:|---:|"]
    L += [f"| {reg} | {dias_reg.get(reg, 0)} | {f['v8']:+.0f} % | {f['bh']:+.0f} % |" for reg, f in medias.iterrows()]
    L += ["", "## Criterios", "",
          f"- C1 rentabilidad > 0: {m['V8']['rent_total_pct']:+.1f} % → {si(c['C1'])}",
          f"- C2 caída máxima ≤ 50 % de la de BH100: {m['V8']['max_dd_pct']:.0f} % frente a {m['BH100']['max_dd_pct']:.0f} % → {si(c['C2'])}",
          f"- C3 Sharpe > BH100 y > BHigual: {m['V8']['sharpe']:.2f} frente a {m['BH100']['sharpe']:.2f} y {m['BHigual']['sharpe']:.2f} → {si(c['C3'])}",
          "- C4 coherencia por activo: " + "; ".join(
              f"{a} rent. {p['V8']['rent_total_pct']:+.1f} %, Sharpe {p['V8']['sharpe']:.2f} frente a {p['BHigual']['sharpe']:.2f}"
              for a, p in por_activo.items()) + f" → {si(c['C4'])}",
          f"- C5 rentabilidad > 0 con costes x2: {m_costes2['rent_total_pct']:+.1f} % → {si(c['C5'])}",
          f"- C6 meseta en desarrollo: {si(c['C6'])}",
          f"- C7 regímenes: bajista V8 {medias.loc['bajista', 'v8']:+.0f} % frente a BH100 {medias.loc['bajista', 'bh']:+.0f} %; "
          f"alcista V8 {medias.loc['alcista', 'v8']:+.0f} % → {si(c['C7'])}",
          f"- S1 Sharpe deflactado ({N_VARIANTES} variantes) ≥ 0,90: {dsr['dsr']:.2f} → {si(s1)}",
          f"- S2 P(Sharpe V8 > BHigual) ≥ 0,80: {p_igual:.2f} → {si(s2)} (P frente a BH100: {p_bh:.2f})", "",
          f"Episodios en la validación: {episodios}. Con menos de 30, las métricas por operación son "
          "**insuficientes para concluir**; el veredicto se apoya en rentabilidades diarias.", "",
          f"## Veredicto: **{veredicto}**", ""]
    (SALIDA / "VALIDACION_RESULTADOS.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    (SALIDA / "validacion.json").write_text(json.dumps({
        "veredicto": veredicto, "commit": commit, "criterios": c, "S1_dsr": dsr, "S2_p_igual": p_igual,
        "p_bh100": p_bh, "cartera": m, "costes_x2": m_costes2, "por_activo": por_activo,
        "regimenes": medias.to_dict(), "dias_regimen": dias_reg, "episodios": episodios,
    }, indent=2, ensure_ascii=False, default=float) + "\n", encoding="utf-8", newline="\n")
    print(f"Veredicto: {veredicto} | criterios {c} | DSR {dsr['dsr']:.2f} | P {p_igual:.2f}")


if __name__ == "__main__":
    main_validacion()
