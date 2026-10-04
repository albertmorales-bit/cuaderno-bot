"""Módulo 2: Donchian sin lookahead, causalidad de todas las señales,
máquina de estados y calentamiento (auditoría P4, P8, P10)."""

import numpy as np
import pandas as pd
import pytest

from modulo_2_estrategia import (
    calcular_canal_donchian,
    ensamblar_estado,
    generar_senales,
    velas_de_calentamiento,
)

DISPARADORES = ["ruptura_donchian", "pullback", "cruce_ema"]


def test_canal_donchian_usa_solo_velas_anteriores(velas):
    alto, bajo = calcular_canal_donchian(velas, 20)
    for i in (25, 100, 500):
        assert alto.iloc[i] == velas["High"].iloc[i - 20:i].max()
        assert bajo.iloc[i] == velas["Low"].iloc[i - 20:i].min()
    assert alto.iloc[:20].isna().all()


def test_pico_de_la_vela_actual_no_entra_en_su_propio_canal(velas):
    df = velas.copy()
    k = 300
    df.iloc[k, df.columns.get_loc("High")] = 1e9
    alto, _ = calcular_canal_donchian(df, 20)
    assert alto.iloc[k] < 1e9          # la vela k no se ve a sí misma
    assert alto.iloc[k + 1] == 1e9     # la siguiente sí la ve (ya está cerrada)


def test_ruptura_exige_superar_estrictamente_el_maximo_previo():
    n = 60
    indice = pd.date_range("2024-01-01", periods=n, freq="1D", tz="UTC")
    df = pd.DataFrame({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 1.0}, index=indice)
    df.iloc[50, df.columns.get_loc("Close")] = 101.0     # igual al máximo previo: no rompe
    df.iloc[55, [df.columns.get_loc("Close"), df.columns.get_loc("High")]] = [101.5, 101.6]  # rompe
    s = generar_senales(df, disparador_entrada="ruptura_donchian", usar_filtro_macro=False,
                        usar_adx=False, usar_filtro_rsi=False)
    assert s["entrada"].iloc[50] == 0
    assert s["entrada"].iloc[55] == 1


@pytest.mark.parametrize("disparador", DISPARADORES)
@pytest.mark.parametrize("usar_adx", [False, True])
def test_senales_no_dependen_del_futuro(velas, disparador, usar_adx):
    """Calcular con datos hasta k debe dar lo mismo, en las primeras k velas,
    que calcular con todo el histórico: si no, alguna columna mira al futuro."""
    kwargs = dict(disparador_entrada=disparador, usar_adx=usar_adx, umbral_adx=15.0,
                  permitir_cortos=True, usar_filtro_rsi=True)
    completo = generar_senales(velas, **kwargs)
    columnas = ["entrada", "senal", "atr", "rsi", "ema_macro", "calentamiento_ok", "evento_entrada_largo"]
    if usar_adx:
        columnas.append("adx")
    for k in (450, 600, 799):
        parcial = generar_senales(velas.iloc[:k], **kwargs)
        pd.testing.assert_frame_equal(parcial[columnas], completo[columnas].iloc[:k])


def test_sin_cortos_no_hay_senal_negativa(velas):
    for disparador in DISPARADORES:
        s = generar_senales(velas, disparador_entrada=disparador, permitir_cortos=False, usar_adx=False)
        assert (s["senal"] >= 0).all() and (s["entrada"] >= 0).all()


def test_maquina_de_estados_salida_de_corto_no_cierra_un_largo():
    f, t = False, True
    estado = ensamblar_estado(
        entrada_larga=np.array([t, f, f, f]),
        entrada_corta=np.array([f, f, f, f]),
        salida_larga=np.array([f, f, f, t]),
        salida_corta=np.array([f, t, f, f]),   # salida de corto con un largo abierto
    )
    assert list(estado) == [1, 1, 1, 0]


def test_maquina_de_estados_entrada_manda_sobre_salida_en_la_misma_vela():
    estado = ensamblar_estado(
        np.array([True, True]), np.array([False, False]),
        np.array([False, True]), np.array([False, False]),
    )
    assert list(estado) == [1, 1]


def test_no_hay_entradas_durante_el_calentamiento(velas):
    s = generar_senales(velas, disparador_entrada="ruptura_donchian", usar_adx=False)
    n = velas_de_calentamiento("ruptura_donchian", 50, 14, 14, True, 200, False, 14, 20, 2.0)
    assert n == 400
    assert not s["calentamiento_ok"].iloc[:n].any() and s["calentamiento_ok"].iloc[n:].all()
    assert (s["entrada"].iloc[:n] == 0).all()


def test_disparador_desconocido_falla(velas):
    with pytest.raises(ValueError):
        generar_senales(velas, disparador_entrada="magia")
