"""Módulo 4: ejecución, orden de eventos, costes, métricas, partición y
exportación (auditoría P2, P3, P4, P6, P10)."""

import math

import numpy as np
import pandas as pd
import pytest

from conftest import marco_motor
from modulo_4_backtesting import (
    MotorBacktest,
    ParametrosBacktest,
    calcular_metricas,
    exportar_operaciones_csv,
    exportar_rentabilidades_periodicas,
    particionar_resultado,
)

SIN_COSTES = dict(comision_pct=0.0, slippage_pct=0.0)


def poner(df, i, **valores):
    for columna, valor in valores.items():
        df.iloc[i, df.columns.get_loc(columna)] = valor


def evento_largo(df, i, hasta=None):
    """Evento de entrada en la vela i y estado largo desde i hasta `hasta` (incluida)."""
    poner(df, i, entrada=1)
    df.iloc[i:(hasta + 1 if hasta is not None else None), df.columns.get_loc("senal")] = 1


def motor(**kwargs):
    base = dict(SIN_COSTES, usar_take_profit=False)
    base.update(kwargs)
    return MotorBacktest(ParametrosBacktest(**base))


def test_entrada_en_la_apertura_siguiente_con_atr_de_la_vela_de_senal():
    df = marco_motor()
    evento_largo(df, 2)
    poner(df, 2, Close=101.0)                                              # cierre de la vela de señal
    poner(df, 3, Open=105.0, High=106.5, Low=104.5, Close=106.0, atr=50.0)  # ATR de i: no debe usarse
    r = motor().ejecutar(df)
    t = r.trades[0]
    assert t.fecha_entrada == df.index[3]
    assert t.precio_entrada_referencia == 105.0
    # stop = entrada - 2 x ATR(vela 2) = 105 - 2 -> el ATR de 50 de la vela 3 no se usó
    assert t.unidades == pytest.approx(100.0 / 2.0, rel=1e-6)


def test_stop_se_comprueba_en_la_propia_vela_de_entrada():
    df = marco_motor()
    evento_largo(df, 2)
    poner(df, 3, Low=90.0)                 # stop en 98: se toca en la vela de entrada
    t = motor().ejecutar(df).trades[0]
    assert t.motivo_salida == "stop_loss" and t.fecha_salida == df.index[3]
    assert t.precio_salida == pytest.approx(98.0)


def test_hueco_en_contra_se_ejecuta_a_la_apertura():
    df = marco_motor()
    evento_largo(df, 2)
    poner(df, 6, Open=95.0, High=95.5, Low=94.0, Close=95.0)   # abre por debajo del stop (98)
    t = motor().ejecutar(df).trades[0]
    assert t.motivo_salida == "stop_loss" and t.precio_salida == pytest.approx(95.0)


def test_cierre_por_senal_en_apertura_va_antes_que_el_take_profit_intravela():
    df = marco_motor()
    evento_largo(df, 2, hasta=4)           # la señal se apaga en la vela 5
    poner(df, 6, High=200.0)               # el TP (104) se tocaría dentro de la vela 6
    t = motor(usar_take_profit=True).ejecutar(df).trades[0]
    assert t.motivo_salida == "senal_contraria"
    assert t.fecha_salida == df.index[6] and t.precio_salida == pytest.approx(100.0)


def test_no_se_reabre_tras_un_stop_sin_evento_nuevo():
    df = marco_motor(n=12)
    evento_largo(df, 2)                    # estado largo hasta el final
    poner(df, 4, Low=90.0)                 # stop en la vela 4
    r = motor().ejecutar(df)
    assert [t.motivo_salida for t in r.trades] == ["stop_loss"]   # la v4 reabría en la vela 5


def test_reabre_con_un_evento_nuevo_pero_no_en_la_vela_de_cierre():
    df = marco_motor(n=12)
    evento_largo(df, 2)
    poner(df, 4, Low=90.0)                 # stop en la vela 4
    poner(df, 3, entrada=1)                # evento en 3 -> pediría entrar en 4 (vela del stop: ya hay posición)
    poner(df, 7, entrada=1)                # evento nuevo en 7 -> entra en 8
    r = motor().ejecutar(df)
    assert [t.fecha_entrada for t in r.trades] == [df.index[3], df.index[8]]


def test_aritmetica_de_comision_y_slippage():
    df = marco_motor()
    evento_largo(df, 2, hasta=5)
    poner(df, 7, Open=110.0, High=110.5, Low=109.5, Close=110.0)
    p = dict(comision_pct=0.008, slippage_pct=0.001, usar_take_profit=False)
    t = MotorBacktest(ParametrosBacktest(**p)).ejecutar(df).trades[0]
    assert t.precio_entrada == pytest.approx(100.0 * 1.001)
    assert t.precio_salida == pytest.approx(110.0 * 0.999)
    comision = 0.008 * t.unidades * (t.precio_entrada + t.precio_salida)
    assert t.comision_total == pytest.approx(comision)
    assert t.pnl_neto == pytest.approx((t.precio_salida - t.precio_entrada) * t.unidades - comision)
    assert t.coste_slippage == pytest.approx(t.unidades * (0.1 + 0.11))


def test_equity_flotante_descuenta_la_comision_de_entrada():
    df = marco_motor()
    evento_largo(df, 2)
    r = MotorBacktest(ParametrosBacktest(comision_pct=0.01, slippage_pct=0.0, usar_take_profit=False)).ejecutar(df)
    unidades = r.trades[0].unidades
    assert r.curva_capital.iloc[3] == pytest.approx(10_000.0 - 0.01 * unidades * 100.0)


def test_posicion_abierta_al_final_se_marca_como_fin_de_datos():
    df = marco_motor()
    evento_largo(df, 2)
    r = motor().ejecutar(df)
    assert r.trades[-1].motivo_salida == "fin_de_datos"
    assert r.metricas["num_trades_fin_de_datos"] == 1


def test_motor_respeta_el_calentamiento():
    df = marco_motor()
    evento_largo(df, 1)
    df.iloc[:3, df.columns.get_loc("calentamiento_ok")] = False
    r = motor().ejecutar(df)
    assert r.curva_capital.index[0] == df.index[3] and not r.trades


def test_sortino_usa_la_desviacion_a_la_baja_estandar():
    curva = pd.Series([100.0, 110.0, 99.0, 108.9, 107.8],
                      index=pd.date_range("2024", periods=5, freq="1D", tz="UTC"))
    m = calcular_metricas([], curva, ParametrosBacktest(capital_inicial=100.0, periodos_por_anio=365))
    r = curva.pct_change().dropna().to_numpy()
    esperado = r.mean() / math.sqrt(np.mean(np.minimum(r, 0) ** 2)) * math.sqrt(365)
    assert m["sortino_ratio"] == pytest.approx(esperado)


def _resultado_con_tres_operaciones():
    df = marco_motor(n=30)
    evento_largo(df, 2, hasta=5)       # 3 -> 7
    evento_largo(df, 12, hasta=20)     # 13 -> 22 (a caballo del corte en la vela 15)
    evento_largo(df, 23, hasta=26)     # 24 -> 28
    params = ParametrosBacktest(**SIN_COSTES, usar_take_profit=False)
    return MotorBacktest(params).ejecutar(df), params, df


def test_particion_embarga_la_operacion_a_caballo_del_corte():
    r, params, df = _resultado_con_tres_operaciones()
    part = particionar_resultado(r, params, fecha_corte=df.index[15])
    assert [t.fecha_entrada for t in part.dentro.trades] == [df.index[3]]
    assert [t.fecha_entrada for t in part.fuera.trades] == [df.index[24]]
    assert [t.fecha_entrada for t in part.embargadas] == [df.index[13]]
    assert part.fuera.curva_capital.index[0] == df.index[15]


def test_particion_por_fraccion():
    r, params, _ = _resultado_con_tres_operaciones()
    part = particionar_resultado(r, params, fraccion_oos=0.3)
    assert len(part.fuera.curva_capital) == pytest.approx(0.3 * len(r.curva_capital), abs=1)


def test_csv_de_operaciones_legible_por_significancia(tmp_path):
    import significancia

    r, _, _ = _resultado_con_tres_operaciones()
    for t in r.trades:
        t.activo = "BTC/EUR"
    ruta = exportar_operaciones_csv(r.trades, tmp_path / "ops.csv")
    filas = significancia.leer_operaciones(str(ruta))
    assert len(filas) == 3 and filas[0]["tipo"] == "largo"
    t = r.trades[0]
    assert float(filas[0]["resultado_%"]) == pytest.approx(t.pnl_neto / t.capital_antes * 100, abs=1e-6)


def test_csv_periodico_legible_por_pbo(tmp_path):
    import pbo

    indice = pd.date_range("2024-01-01", periods=5, freq="1D", tz="UTC")
    curvas = {"a": pd.Series([100, 101, 101, 99, 100.0], index=indice),
              "b": pd.Series([100, 100, 102, 102, 103.0], index=indice)}
    nombres, matriz = pbo.leer_variantes(str(exportar_rentabilidades_periodicas(curvas, tmp_path / "v.csv")))
    assert nombres == ["a", "b"] and len(matriz) == 4
    assert matriz[0][0] == pytest.approx(1.0)
