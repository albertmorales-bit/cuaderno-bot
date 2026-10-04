"""Módulo 1: velas cerradas, intervalos y limpieza (auditoría P7)."""

import pandas as pd
import pytest

from modulo_1_datos import ProveedorDatos, descartar_vela_en_curso, duracion_intervalo


def test_duracion_intervalo():
    assert duracion_intervalo("4h") == pd.Timedelta(hours=4)
    assert duracion_intervalo("1d") == pd.Timedelta(days=1)
    assert duracion_intervalo("15m") == pd.Timedelta(minutes=15)
    with pytest.raises(ValueError):
        duracion_intervalo("4x")


def test_descarta_vela_diaria_en_curso():
    indice = pd.date_range("2026-10-01", periods=4, freq="1D", tz="UTC")  # 1..4 oct
    df = pd.DataFrame({"Close": [1.0, 2.0, 3.0, 4.0]}, index=indice)
    # A las 09:08 del 4 de octubre la vela del día 4 sigue abierta.
    resultado = descartar_vela_en_curso(df, "1d", ahora=pd.Timestamp("2026-10-04 09:08", tz="UTC"))
    assert list(resultado.index.day) == [1, 2, 3]


def test_vela_4h_cerrada_justo_en_su_cierre():
    indice = pd.date_range("2026-10-04 04:00", periods=2, freq="4h", tz="UTC")  # 04:00 y 08:00
    df = pd.DataFrame({"Close": [1.0, 2.0]}, index=indice)
    # La vela de las 08:00 cierra a las 12:00 en punto: a esa hora ya cuenta como cerrada.
    assert len(descartar_vela_en_curso(df, "4h", ahora=pd.Timestamp("2026-10-04 12:00", tz="UTC"))) == 2
    assert len(descartar_vela_en_curso(df, "4h", ahora=pd.Timestamp("2026-10-04 11:59", tz="UTC"))) == 1


def test_normalizacion_quita_duplicados_y_precios_invalidos():
    indice = pd.to_datetime(["2024-01-02", "2024-01-01", "2024-01-02", "2024-01-03"], utc=True)
    df = pd.DataFrame(
        {"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": [5.0, 4.0, 6.0, -1.0], "Volume": 1.0}, index=indice
    )
    limpio = ProveedorDatos._validar_y_normalizar(df, "TEST")
    assert limpio.index.is_monotonic_increasing
    assert list(limpio["Close"]) == [4.0, 6.0]  # duplicado: se queda el último; precio <= 0 fuera
