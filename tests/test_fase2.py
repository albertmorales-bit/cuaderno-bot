"""Fase 2: conjunto Donchian, escala por volatilidad, motor por exposición
objetivo y clasificación de regímenes (sin red)."""

import numpy as np
import pandas as pd
import pytest

from conftest import velas_sinteticas
from modulo_2_estrategia import generar_senales_conjunto
from modulo_3_riesgo import escala_por_volatilidad
from modulo_4b_exposicion import MotorExposicion, ParametrosExposicion, benchmark_exposicion_constante
from modulo_5_regimenes import (
    SIN_DATOS,
    atribuir_por_regimen,
    bootstrap_por_bloques,
    clasificar_regimenes,
    diferencia_anual,
    percentil_expansivo,
    resumen_por_regimen,
)

SIN_COSTES = dict(comision_pct=0.0, slippage_pct=0.0)


# --------------------------------------------------------------- conjunto
def test_conjunto_no_depende_del_futuro():
    velas = velas_sinteticas(n=1200, semilla=4)
    completo = generar_senales_conjunto(velas)
    for k in (700, 1000):
        parcial = generar_senales_conjunto(velas.iloc[:k])
        columnas = ["estado_20_10", "estado_55_20", "estado_100_50", "senal_conjunto", "calentamiento_ok"]
        pd.testing.assert_frame_equal(parcial[columnas], completo[columnas].iloc[:k])


def test_conjunto_es_la_media_de_estados_y_cero_en_calentamiento():
    s = generar_senales_conjunto(velas_sinteticas(n=900, semilla=2))
    estados = s[["estado_20_10", "estado_55_20", "estado_100_50"]]
    assert set(np.unique(estados.to_numpy())) <= {0, 1}
    tras = s["calentamiento_ok"]
    assert np.allclose(s.loc[tras, "senal_conjunto"], estados[tras].mean(axis=1))
    assert (s.loc[~tras, "senal_conjunto"] == 0).all()


def test_sistema_entra_en_ruptura_y_sale_en_canal_corto():
    n = 60
    indice = pd.date_range("2024-01-01", periods=n, freq="1D", tz="UTC")
    cierre = np.full(n, 100.0)
    cierre[30] = 105.0     # rompe el máximo de 20 velas
    cierre[31:40] = 104.0
    cierre[40] = 90.0      # pierde el mínimo de 10 velas
    df = pd.DataFrame({"Open": cierre, "High": cierre + 0.5, "Low": cierre - 0.5, "Close": cierre,
                       "Volume": 1.0}, index=indice)
    s = generar_senales_conjunto(df, sistemas=((20, 10),), velas_calentamiento=0)
    assert s["estado_20_10"].iloc[29] == 0 and s["estado_20_10"].iloc[30] == 1
    assert s["estado_20_10"].iloc[39] == 1 and s["estado_20_10"].iloc[40] == 0


def test_conjunto_rechaza_salida_mas_larga_que_entrada():
    with pytest.raises(ValueError):
        generar_senales_conjunto(velas_sinteticas(n=900), sistemas=((10, 20),))


# --------------------------------------------------- escala por volatilidad
def test_escala_por_volatilidad_formula_tope_y_causalidad():
    rng = np.random.default_rng(0)
    cierre = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.03, 400))),
                       index=pd.date_range("2020", periods=400, freq="1D", tz="UTC"))
    escala = escala_por_volatilidad(cierre, objetivo_anual=0.40, ventana=30)
    vol = np.log(cierre).diff().iloc[-30:].std() * np.sqrt(365)
    assert escala.iloc[-1] == pytest.approx(min(1.0, 0.40 / vol))
    assert (escala.iloc[:30] == 0).all() and escala.max() <= 1.0
    assert escala_por_volatilidad(cierre.iloc[:300], 0.40, 30).equals(escala.iloc[:300])


# ------------------------------------------------------- motor exposición
def marco(n=12, precio=100.0):
    indice = pd.date_range("2024-01-01", periods=n, freq="1D", tz="UTC")
    return pd.DataFrame({"Open": precio, "High": precio, "Low": precio, "Close": precio,
                         "exposicion_objetivo": 0.0, "calentamiento_ok": True}, index=indice)


def test_objetivo_del_cierre_se_ejecuta_en_la_apertura_siguiente():
    df = marco()
    df.iloc[3:, df.columns.get_loc("exposicion_objetivo")] = 0.5
    df.iloc[4, df.columns.get_loc("Open")] = 110.0
    df.iloc[4:, df.columns.get_loc("Close")] = 110.0
    r = MotorExposicion(ParametrosExposicion(**SIN_COSTES)).ejecutar(df)
    o = r.operaciones[0]
    assert o.fecha == df.index[4] and o.precio_referencia == 110.0 and o.motivo == "entrada"
    assert o.unidades * 110.0 == pytest.approx(5_000.0, rel=1e-6)


def test_banda_evita_reajustes_pequenos_y_respeta_los_grandes():
    df = marco(n=20)
    df.iloc[1:, df.columns.get_loc("exposicion_objetivo")] = 0.50
    df.iloc[5:, df.columns.get_loc("exposicion_objetivo")] = 0.55    # 5 puntos: dentro de la banda
    df.iloc[10:, df.columns.get_loc("exposicion_objetivo")] = 0.80   # 30 puntos: reajusta
    r = MotorExposicion(ParametrosExposicion(**SIN_COSTES, banda_reajuste=0.10)).ejecutar(df)
    assert [o.motivo for o in r.operaciones] == ["entrada", "reajuste", "fin_de_datos"]
    assert r.operaciones[1].fecha == df.index[11]


def test_costes_sin_apalancamiento_y_episodio_cuadra():
    df = marco(n=10)
    df.iloc[1:6, df.columns.get_loc("exposicion_objetivo")] = 1.0
    df.iloc[3:, [df.columns.get_loc("Open"), df.columns.get_loc("Close")]] = 120.0
    r = MotorExposicion(ParametrosExposicion(comision_pct=0.008, slippage_pct=0.001)).ejecutar(df)
    compra, venta = r.operaciones
    assert compra.precio_efectivo == pytest.approx(100.1) and venta.precio_efectivo == pytest.approx(119.88)
    # con objetivo 100 % la compra no puede gastar más del efectivo disponible
    assert compra.unidades * compra.precio_efectivo + compra.comision <= 10_000.0 + 1e-6
    ep = r.episodios[0]
    assert ep.pnl_neto == pytest.approx(r.capital_final - 10_000.0)
    assert ep.comision_total == pytest.approx(compra.comision + venta.comision)
    assert r.metricas["comisiones_totales"] == pytest.approx(ep.comision_total)


def test_posicion_abierta_al_final_se_cierra_y_se_marca():
    df = marco()
    df.iloc[1:, df.columns.get_loc("exposicion_objetivo")] = 0.3
    r = MotorExposicion(ParametrosExposicion(**SIN_COSTES)).ejecutar(df)
    assert r.episodios[-1].motivo_salida == "fin_de_datos" and r.exposicion.iloc[-1] == 0


def test_motor_rechaza_exposicion_fuera_de_rango():
    df = marco()
    df.iloc[2, df.columns.get_loc("exposicion_objetivo")] = 1.5
    with pytest.raises(ValueError):
        MotorExposicion().ejecutar(df)


def test_motor_no_depende_del_futuro():
    velas = velas_sinteticas(n=1300, semilla=9)
    s = generar_senales_conjunto(velas)
    s["exposicion_objetivo"] = s["senal_conjunto"] * escala_por_volatilidad(s["Close"])
    completo = MotorExposicion().ejecutar(s)
    parcial = MotorExposicion().ejecutar(s.iloc[:1000])
    # Antes del último día del recorte (donde se fuerza el cierre) las curvas coinciden.
    pd.testing.assert_series_equal(parcial.curva_capital.iloc[:-1], completo.curva_capital.iloc[:len(parcial.curva_capital) - 1])


def test_benchmark_todo_invertido_compra_una_vez():
    df = marco(n=30)
    df["Close"] = np.linspace(100, 130, 30)
    df["Open"] = df["Close"].shift(1).fillna(100.0)
    r = benchmark_exposicion_constante(df, ParametrosExposicion(**SIN_COSTES), 1.0)
    assert [o.motivo for o in r.operaciones] == ["entrada", "fin_de_datos"]
    assert r.metricas["exposicion_media"] > 0.9


# -------------------------------------------------------------- regímenes
def test_percentil_expansivo_solo_mira_el_pasado():
    s = pd.Series(np.random.default_rng(1).normal(size=500))
    completo = percentil_expansivo(s, 100)
    assert percentil_expansivo(s.iloc[:300], 100).equals(completo.iloc[:300])
    assert completo.iloc[:99].isna().all()


def test_regimenes_no_dependen_del_futuro():
    velas = velas_sinteticas(n=1000, semilla=6)
    completo = clasificar_regimenes(velas)
    parcial = clasificar_regimenes(velas.iloc[:700])
    pd.testing.assert_frame_equal(parcial, completo.iloc[:700])


def test_etiquetas_de_regimen():
    r = clasificar_regimenes(velas_sinteticas(n=1000, semilla=6))
    assert set(r["regimen_volatilidad"]) <= {"baja", "media", "alta", SIN_DATOS}
    assert set(r["regimen_tendencia"]) <= {"alcista", "bajista", "mixto", SIN_DATOS}
    assert set(r["regimen_fuerza"]) <= {"fuerte", "debil", SIN_DATOS}
    assert (r["regimen_tendencia"].iloc[:219] == SIN_DATOS).all()
    alcistas = r["regimen_tendencia"] == "alcista"
    assert (velas_sinteticas(n=1000, semilla=6)["Close"][alcistas] > r["sma"][alcistas]).all()


def test_atribucion_usa_el_regimen_del_dia_anterior():
    indice = pd.date_range("2024", periods=4, freq="1D", tz="UTC")
    tabla = atribuir_por_regimen(pd.Series([0.0, 0.1, 0.2, 0.3], index=indice),
                                 pd.Series(["a", "b", "c", "d"], index=indice))
    assert list(tabla["regimen"]) == ["a", "b", "c"] and list(tabla["retorno"]) == [0.1, 0.2, 0.3]


def test_resumen_por_regimen_usa_el_regimen_del_dia_anterior():
    indice = pd.date_range("2024", periods=6, freq="1D", tz="UTC")
    ret = pd.Series([0, 0.01, 0.02, 0.03, 0.04, 0.05], index=indice)
    reg = pd.Series(["a", "b", "a", "b", "a", "b"], index=indice)
    t = resumen_por_regimen(ret, ret, pd.Series(1.0, index=indice), reg)
    # días 1, 3 y 5 se decidieron con régimen "a" (cierres de los días 0, 2 y 4)
    assert t.loc["a", "dias"] == 3 and t.loc["b", "dias"] == 2
    assert t.loc["a", "estrategia_rent_anual_pct"] == pytest.approx(0.03 * 365 * 100)


def test_bootstrap_reproducible_y_centrado():
    rng = np.random.default_rng(3)
    etq = np.where(np.arange(4000) % 200 < 100, "a", "b")
    ret = np.where(etq == "a", 0.002, 0.0) + rng.normal(0, 0.01, 4000)
    f = diferencia_anual("a", "b")
    b1 = bootstrap_por_bloques(ret, etq, f, n_remuestreos=500)
    b2 = bootstrap_por_bloques(ret, etq, f, n_remuestreos=500)
    assert np.array_equal(b1, b2)
    assert np.quantile(b1, 0.05) > 0 and np.median(b1) == pytest.approx(0.002 * 365, rel=0.35)
