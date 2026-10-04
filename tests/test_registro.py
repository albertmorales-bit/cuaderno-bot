"""Módulo 7: cadena de hashes del registro de transparencia."""

import json

import numpy as np
import pandas as pd
import pytest

from modulo_7_registro import GENESIS, Registro, sha256_texto, verificar_texto


@pytest.fixture
def registro(tmp_path):
    r = Registro(tmp_path / "registro.jsonl")
    r.anadir("inicio", {"capital": 10_000.0}, ts_utc=pd.Timestamp("2026-10-10", tz="UTC"))
    r.anadir("decision", {"exposicion": np.float64(0.25), "estados": [1, 0, 1]})
    r.anadir("ejecucion", {"precio": 52_000.12345678, "unidades": 1e-05, "lado": "compra"})
    return r


def test_cadena_valida_y_encadenada(registro):
    v = registro.verificar()
    assert v.valido and v.lineas == 3
    eventos = registro.eventos()
    assert eventos[0]["hash_anterior"] == GENESIS
    assert eventos[1]["hash_anterior"] == eventos[0]["hash"]
    assert v.ultimo_hash == eventos[-1]["hash"]


def test_hash_se_calcula_sobre_el_texto_exacto(registro):
    linea = registro.texto().split("\n")[2]
    contenido, h = linea.rsplit(',"hash":"', 1)
    assert sha256_texto(contenido + "}") == h[:64]
    assert "1e-05" in linea                      # el número tal como lo escribió Python


@pytest.mark.parametrize("alteracion", ["cambiar_dato", "borrar_linea", "reordenar", "cambiar_hash"])
def test_cualquier_alteracion_se_detecta(registro, alteracion):
    lineas = registro.texto().strip("\n").split("\n")
    if alteracion == "cambiar_dato":
        lineas[1] = lineas[1].replace("0.25", "0.26")
    elif alteracion == "borrar_linea":
        del lineas[1]
    elif alteracion == "reordenar":
        lineas[1], lineas[2] = lineas[2], lineas[1]
    else:
        lineas[2] = lineas[2][:-10] + "0000000000"[: 8] + '"}'
    v = verificar_texto("\n".join(lineas) + "\n")
    assert not v.valido and v.linea_error is not None


def test_no_se_escribe_sobre_un_registro_alterado(registro):
    texto = registro.texto().replace("0.25", "0.99")
    registro.ruta.write_text(texto, encoding="utf-8", newline="\n")
    with pytest.raises(RuntimeError, match="alterado"):
        registro.anadir("decision", {"x": 1})


def test_rechaza_nan(tmp_path):
    with pytest.raises(ValueError):
        Registro(tmp_path / "r.jsonl").anadir("x", {"v": float("nan")})


def test_lineas_son_json_valido(registro):
    for linea in registro.texto().strip().split("\n"):
        json.loads(linea)
