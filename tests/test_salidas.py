"""Módulo 9: salidas diarias (tuit, comentario, hilo, resumen e imagen)."""

import pytest

import main
from modulo_9_salidas import (
    PLANTILLAS,
    cabe_en_x,
    comentario_diario,
    construir_estado,
    eur,
    generar_salidas,
    hilo_semanal,
    imagen_diaria,
    longitud_x,
    pct,
    tuit_diario,
)
from test_vivo import N_INICIAL, arrancar, correr, datos_sinteticos

CONFIG = main.Configuracion()
WEB, REPO = "https://usuario.github.io/cuaderno-bot/", "https://github.com/usuario/cuaderno-bot"


@pytest.fixture(scope="module")
def experimento(tmp_path_factory):
    datos = datos_sinteticos()
    motor, fuente, indice = arrancar(tmp_path_factory.mktemp("salidas"), datos)
    estados = []
    for i in range(N_INICIAL + 1, N_INICIAL + 31):
        correr(motor, fuente, indice, i, i + 1)
        ev = motor.registro.eventos()
        estados.append(construir_estado(ev, motor.registro.verificar().ultimo_hash, CONFIG.comision_pct, CONFIG.slippage_pct))
    return motor, estados


def test_longitud_x_sigue_twitter_text():
    assert longitud_x("hola") == 4
    assert longitud_x("€") == 2 and longitud_x("…") == 2 and longitud_x("á ñ ü") == 5
    assert longitud_x("mira https://ejemplo.com/una/ruta/muy/larga") == 5 + 23
    assert not cabe_en_x("x" * 279 + "€") and cabe_en_x("x" * 278 + "€")


def test_formato_espanol():
    assert eur(10234.5) == "10.234 €" or eur(10234.5) == "10.235 €"
    assert eur(-12.3, 2, True) == "-12,30 €" and eur(5, 0, True) == "+5 €"
    assert pct(0.0123, 2, True) == "+1,23 %" and pct(-0.05) == "-5,0 %"


def test_dia_0_no_tiene_estado(tmp_path):
    motor, _, _ = arrancar(tmp_path, datos_sinteticos())
    assert construir_estado(motor.registro.eventos(), "0" * 64, 0.008, 0.001) is None


def test_estado_cuadra_con_el_registro(experimento):
    motor, estados = experimento
    e = estados[-1]
    assert e.dia == 30
    # Fe de erratas 1: valor tras ejecutar las órdenes del día, a precio de apertura.
    ev = motor.registro.eventos()
    tenencias = {p: (5_000.0, 0.0) for p in ("BTC/EUR", "ETH/EUR")}
    apertura = {}
    for x in ev:
        d = x["datos"]
        if x["tipo"] in ("ejecucion", "sin_orden") and d["cartera"] == "V8" and d["fecha_decision"] <= e.fecha:
            if x["tipo"] == "ejecucion":
                tenencias[d["par"]] = (d["efectivo_despues"], d["unidades_despues"])
            if d["fecha_decision"] == e.fecha:
                apertura[d["par"]] = d.get("apertura", d.get("precio_referencia"))
    esperado = sum(ef + un * apertura[p] for p, (ef, un) in tenencias.items())
    assert e.carteras["V8"].equity == pytest.approx(esperado)
    assert e.fecha_apertura > e.fecha and e.series.index[-1] == e.fecha_apertura
    assert e.series["V8"].iloc[0] == 10_000
    assert 0 <= e.carteras["V8"].caida_actual <= e.carteras["V8"].caida_maxima


def test_tuits_caben_llevan_las_cifras_y_cambian_cada_dia(experimento):
    _, estados = experimento
    tuits = [tuit_diario(e) for e in estados]
    for e, t in zip(estados, tuits):
        assert cabe_en_x(t), (longitud_x(t), t)
        assert f"{e.dia} de 90" in t
        assert eur(e.carteras["V8"].equity) in t and e.hash_dia[:8] in t
        assert pct(e.carteras["V8"].caida_actual, 1) in t
        assert "http" not in t
    assert all(a != b for a, b in zip(tuits, tuits[1:]))
    assert len({t.split("\n")[0][:12] for t in tuits[:len(PLANTILLAS)]}) > 3   # varía la forma, no solo las cifras


def test_comentario_y_hilo(experimento):
    _, estados = experimento
    c = comentario_diario(estados[-1], WEB, REPO)
    assert cabe_en_x(c) and WEB in c and estados[-1].hash_dia in c and "Dinero ficticio" in c
    assert hilo_semanal(estados[5], []) is None
    motor, _ = experimento
    hilo = hilo_semanal(estados[6], motor.registro.eventos())
    assert hilo and all(cabe_en_x(t) for t in hilo) and "NO APTO" in hilo[-1]


def test_imagen_y_salidas_completas(experimento, tmp_path):
    motor, estados = experimento
    assert imagen_diaria(estados[0], tmp_path / "dia1.png").stat().st_size > 10_000   # día 1: dos puntos
    carpeta = generar_salidas(motor.raiz, CONFIG.comision_pct, CONFIG.slippage_pct, WEB, REPO)
    for archivo in ("resumen.json", "resumen.md", "tuit.txt", "comentario.txt", "imagen.png"):
        assert (carpeta / archivo).exists()
