"""Módulo 3: sizing por riesgo fijo, tope sin apalancamiento y mínimos."""

from modulo_3_riesgo import calcular_gestion_riesgo


def test_formula_de_sizing_y_stop():
    plan = calcular_gestion_riesgo(50_000.0, 1_200.0, 1, capital_cuenta=10_000.0, riesgo_por_operacion=0.01)
    assert plan.distancia_stop == 2_400.0
    assert plan.precio_stop_loss == 47_600.0
    assert plan.precio_take_profit == 54_800.0
    assert plan.tamano_posicion == 0.041666           # 100 / 2400, truncado a 6 decimales
    assert plan.perdida_maxima_teorica <= 100.0        # nunca más que el riesgo objetivo


def test_redondeo_hacia_abajo_nunca_supera_el_riesgo():
    for atr in (7.0, 13.0, 333.0, 1_234.5):
        plan = calcular_gestion_riesgo(10_000.0, atr, 1, capital_cuenta=10_000.0, riesgo_por_operacion=0.01)
        assert plan.perdida_maxima_teorica <= 100.0 + 1e-9


def test_tope_sin_apalancamiento_incluye_la_comision():
    # Stop muy cerca: el riesgo pediría más nocional que el capital disponible.
    plan = calcular_gestion_riesgo(100.0, 0.01, 1, capital_cuenta=1_000.0, comision_pct=0.008)
    assert plan.capital_invertido * 1.008 <= 1_000.0
    assert plan.advertencias


def test_por_debajo_del_minimo_de_orden_se_descarta():
    plan = calcular_gestion_riesgo(60_000.0, 3_000.0, 1, capital_cuenta=100.0, tamano_minimo=0.00005)
    # 1 € de riesgo / 6000 € de distancia = 0,000166 BTC > mínimo: se opera
    assert plan.tamano_posicion > 0
    plan = calcular_gestion_riesgo(60_000.0, 3_000.0, 1, capital_cuenta=10.0, tamano_minimo=0.00005)
    assert plan.tamano_posicion == 0.0 and plan.capital_invertido == 0.0
