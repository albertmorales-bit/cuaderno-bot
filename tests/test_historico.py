"""Módulo 1b: diagnóstico, comparación, serie limpia y checksums (sin red)."""

import json

import pandas as pd
import pytest

from conftest import velas_sinteticas
from modulo_1b_historico import (
    cargar_historico,
    comparar_fuentes,
    construir_serie_limpia,
    diagnosticar_calidad,
    escribir_manifiesto,
    guardar_csv,
    nombre_archivo,
)


def test_diagnostico_detecta_huecos_ohlc_y_extremos():
    df = velas_sinteticas(n=100)
    df = df.drop(df.index[[10, 11]])
    df.iloc[20, df.columns.get_loc("High")] = df["Low"].iloc[20] * 0.5   # High < Low
    df.iloc[30, df.columns.get_loc("Close")] *= 2                          # salto extremo
    c = diagnosticar_calidad(df, "1d")
    assert c["huecos"] == 2 and c["ohlc_incoherente"] >= 1 and len(c["movimientos_extremos"]) >= 1


def test_comparar_fuentes():
    a = velas_sinteticas(n=50)
    b = a.copy()
    b.iloc[5, b.columns.get_loc("Close")] *= 1.05
    c = comparar_fuentes(a, b)
    assert c["dias_comunes"] == 50 and c["max_dif_pct"] == pytest.approx(5.0)
    assert c["dias_dif_mayor_2pct"] == 1


def test_serie_limpia_rellena_con_respaldo_y_recorta_huecos_de_arranque():
    respaldo = velas_sinteticas(n=200)
    principal = respaldo.drop(respaldo.index[[2, 3, 100]])                 # huecos al inicio y en medio
    respaldo_sin_inicio = respaldo.drop(respaldo.index[[2, 3]])            # el respaldo tampoco tiene 2 y 3
    limpia, incidencias = construir_serie_limpia(principal, respaldo_sin_inicio, "a", "b", "1d")
    assert limpia.index.min() == respaldo.index[4]                         # recortada tras el último hueco
    assert limpia.loc[respaldo.index[100], "fuente"] == "b"                # rellenado, y marcado
    assert {i["tipo"] for i in incidencias} == {"hueco", "recorte_inicio"}
    assert diagnosticar_calidad(limpia, "1d")["huecos"] == 0


def test_carga_verifica_checksum(tmp_path):
    df = velas_sinteticas(n=30)
    df["fuente"] = "a"
    nombre = nombre_archivo("BTC/EUR", "1d")
    sha = guardar_csv(df, tmp_path / "v9" / nombre)
    escribir_manifiesto(tmp_path / "v9", {"archivos": {nombre: sha}})
    cargado = cargar_historico("BTC/EUR", "1d", "v9", raiz=tmp_path)
    assert len(cargado) == 30 and str(cargado.index.tz) == "UTC"
    assert (cargado.index == df.index).all()
    assert cargado["Close"].to_numpy() == pytest.approx(df["Close"].round(8).to_numpy(), abs=1e-8)
    # Alterar un solo carácter del archivo debe impedir la carga.
    ruta = tmp_path / "v9" / nombre
    texto = ruta.read_text(encoding="utf-8")
    ruta.write_text(texto.replace(",a\n", ",b\n", 1), encoding="utf-8", newline="\n")
    with pytest.raises(ValueError, match="Checksum"):
        cargar_historico("BTC/EUR", "1d", "v9", raiz=tmp_path)


def test_guardado_es_determinista(tmp_path):
    df = velas_sinteticas(n=30)
    assert guardar_csv(df, tmp_path / "a.csv") == guardar_csv(df, tmp_path / "b.csv")
