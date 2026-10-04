"""Módulo 6: ventanas de validación, bootstrap, Sharpe deflactado y actividad."""

import numpy as np
import pandas as pd
import pytest

import main
from conftest import velas_sinteticas
from modulo_6_validacion import (
    actividad_esperada,
    bootstrap_metricas,
    ejecutar_ventana,
    metricas_diarias,
    prob_sharpe_superior,
    sharpe_deflactado,
    sumar_curvas,
)


@pytest.fixture
def velas_largas():
    v = velas_sinteticas(n=1600, semilla=11)
    v.index = pd.date_range("2016-01-01", periods=1600, freq="1D", tz="UTC")
    return v


def test_ventana_arranca_sin_posicion_y_no_mira_despues_del_fin(velas_largas):
    config = main.Configuracion()
    r = ejecutar_ventana(config, "BTC/EUR", "2018-01-01", "2019-01-01", datos=velas_largas)
    curva = r.estrategia.curva_capital
    assert curva.index[0] == pd.Timestamp("2018-01-01", tz="UTC")
    assert curva.index[-1] < pd.Timestamp("2019-01-01", tz="UTC")
    assert curva.iloc[0] == pytest.approx(config.capital_inicial)
    assert all(o.fecha > curva.index[0] for o in r.estrategia.operaciones)
    # Cambiar los datos POSTERIORES al fin no puede cambiar nada de la ventana.
    alterados = velas_largas.copy()
    alterados.loc[alterados.index >= "2019-01-01", ["Open", "High", "Low", "Close"]] *= 3
    r2 = ejecutar_ventana(config, "BTC/EUR", "2018-01-01", "2019-01-01", datos=alterados)
    pd.testing.assert_series_equal(curva, r2.estrategia.curva_capital)


def test_benchmarks_en_la_misma_ventana(velas_largas):
    r = ejecutar_ventana(main.Configuracion(), "BTC/EUR", "2018-01-01", "2019-06-01", datos=velas_largas)
    assert r.comprar_mantener.curva_capital.index.equals(r.estrategia.curva_capital.index)
    assert r.misma_exposicion.metricas["exposicion_media"] == pytest.approx(
        r.estrategia.metricas["exposicion_media"], abs=0.06)


def test_sumar_curvas_y_metricas():
    indice = pd.date_range("2024", periods=3, freq="1D", tz="UTC")
    c = sumar_curvas([pd.Series([100, 110, 121.0], index=indice), pd.Series([100, 100, 100.0], index=indice)])
    assert list(c) == [200, 210, 221]
    m = metricas_diarias(pd.Series([100, 50, 100.0], index=indice))
    assert m["max_dd_pct"] == pytest.approx(-50) and m["rent_total_pct"] == pytest.approx(0)


def test_bootstrap_reproducible_y_ordenado():
    r = pd.Series(np.random.default_rng(0).normal(0.001, 0.02, 1500))
    a, b = bootstrap_metricas(r, 400), bootstrap_metricas(r, 400)
    assert a == b
    assert a["sharpe_ic"][0] < a["sharpe_ic"][1] and a["max_dd_ic_pct"][1] <= 0


def test_prob_sharpe_superior():
    rng = np.random.default_rng(1)
    base = pd.Series(rng.normal(0, 0.02, 2000))
    assert prob_sharpe_superior(base, base, 300) == 0.0                    # empate: nunca estrictamente mayor
    assert prob_sharpe_superior(base + 0.002, base, 300) > 0.95


def test_sharpe_deflactado_baja_con_mas_variantes():
    r = pd.Series(np.random.default_rng(2).normal(0.0015, 0.02, 1000))
    uno, ocho, cien = (sharpe_deflactado(r, n)["dsr"] for n in (1, 8, 100))
    assert uno > ocho > cien


def test_actividad_esperada():
    class R:
        def __init__(self, n_ep, n_ord):
            self.curva_capital = pd.Series(0.0, index=pd.date_range("2020", "2023-12-31", freq="1D", tz="UTC"))
            self.episodios = [None] * n_ep
            self.metricas = {"num_ordenes": n_ord}
    a = actividad_esperada([R(8, 96), R(8, 96)], dias=90)   # 2 activos x 4 años, 2 entradas/año cada uno
    assert a["entradas_esperadas"] == pytest.approx(2 * 2 * 90 / 365.25, rel=0.01)
    lo, hi = a["entradas_ic90"]
    assert lo <= a["entradas_esperadas"] <= hi
