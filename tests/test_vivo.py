"""Módulo 8: test de repetición (vivo = backtest), idempotencia, velas
perdidas, configuración congelada, registro alterado y regla de parada."""

from dataclasses import replace

import pandas as pd
import pytest

import main
from conftest import velas_sinteticas
from modulo_4b_exposicion import MotorExposicion, benchmark_exposicion_constante
from modulo_8_vivo import FuenteHistorica, MotorVivo, ReglasSeguridad

N_TOTAL, N_INICIAL = 1000, 760
HORA = pd.Timedelta(minutes=17)


def datos_sinteticos():
    salida = {}
    for semilla, par in ((21, "BTC/EUR"), (22, "ETH/EUR")):
        v = velas_sinteticas(n=N_TOTAL, semilla=semilla).round(2)   # precisión de exchange: sin pérdidas al archivar
        v.index = pd.date_range("2023-01-01", periods=N_TOTAL, freq="1D", tz="UTC")
        salida[par] = v
    return salida


def arrancar(tmp_path, datos, reglas=ReglasSeguridad(), config=None):
    fuente = FuenteHistorica(datos)
    motor = MotorVivo(tmp_path / "vivo", config or main.Configuracion(), reglas, fuente)
    indice = datos["BTC/EUR"].index
    fuente.ahora = indice[N_INICIAL] + HORA          # día 0: cerradas hasta N_INICIAL - 1
    motor.inicializar(fuente.ahora, commit="test")
    return motor, fuente, indice


def correr(motor, fuente, indice, desde, hasta, saltar=()):
    for i in range(desde, hasta):
        if i in saltar:
            continue
        fuente.ahora = indice[i] + HORA
        motor.ejecutar(fuente.ahora)


@pytest.fixture(scope="module")
def repeticion(tmp_path_factory):
    datos = datos_sinteticos()
    motor, fuente, indice = arrancar(tmp_path_factory.mktemp("rep"), datos)
    correr(motor, fuente, indice, N_INICIAL + 1, N_TOTAL)
    return motor, datos, indice


def ordenes_vivo(motor, cartera, par):
    return [(e["datos"]["fecha"], e["datos"]["lado"], e["datos"]["unidades"], e["datos"]["precio_efectivo"],
             e["datos"]["comision"]) for e in motor.registro.eventos()
            if e["tipo"] == "ejecucion" and e["datos"]["cartera"] == cartera and e["datos"]["par"] == par]


def ordenes_backtest(resultado):
    return [(o.fecha.strftime("%Y-%m-%dT%H:%M:%SZ"), o.lado, o.unidades, o.precio_efectivo, o.comision)
            for o in resultado.operaciones if o.motivo != "fin_de_datos"]


def test_repeticion_vivo_reproduce_el_backtest(repeticion):
    motor, datos, indice = repeticion
    config = main.Configuracion()
    for par in ("BTC/EUR", "ETH/EUR"):
        df = main.preparar_conjunto(config, datos[par])
        df["calentamiento_ok"] = df["calentamiento_ok"] & (df.index >= indice[N_INICIAL])
        params = main.parametros_exposicion(config, par, config.capital_inicial / 2)
        v8 = MotorExposicion(params, par).ejecutar(df)
        fijo = benchmark_exposicion_constante(df, params, 0.30, par)
        vivo_v8, bt_v8 = ordenes_vivo(motor, "V8", par), ordenes_backtest(v8)
        assert len(vivo_v8) > 5, "el escenario debería tener actividad"
        assert vivo_v8 == bt_v8                     # igualdad exacta, no aproximada
        assert ordenes_vivo(motor, "FIJO30", par) == ordenes_backtest(fijo)
        # La valoración al cierre coincide con la curva del backtest.
        val = {e["datos"]["fecha"]: e["datos"]["equity"] for e in motor.registro.eventos()
               if e["tipo"] == "valoracion" and e["datos"]["cartera"] == "V8" and e["datos"]["par"] == par}
        for fecha, equity in list(val.items())[:-1]:
            assert equity == pytest.approx(v8.curva_capital.loc[pd.Timestamp(fecha)], rel=1e-12)


def test_registro_valido_y_decision_antes_que_ejecucion(repeticion):
    motor, _, _ = repeticion
    assert motor.registro.verificar(completa=True).valido
    vistos = set()
    for e in motor.registro.eventos():
        d = e["datos"]
        if e["tipo"] == "decision":
            vistos.add((d["cartera"], d["par"], d["fecha"]))
        if e["tipo"] in ("ejecucion", "sin_orden"):
            assert (d["cartera"], d["par"], d["fecha_decision"]) in vistos
            assert d["fecha"] > d["fecha_decision"]          # se ejecuta en la apertura SIGUIENTE


def test_reintento_no_duplica_nada(tmp_path):
    datos = datos_sinteticos()
    motor, fuente, indice = arrancar(tmp_path, datos)
    correr(motor, fuente, indice, N_INICIAL + 1, N_INICIAL + 30)
    lineas = motor.registro.verificar().lineas
    motor.ejecutar(fuente.ahora)                          # misma hora: reintento
    motor.ejecutar(fuente.ahora + pd.Timedelta(hours=2))  # segundo cron del mismo día
    assert motor.registro.verificar().lineas == lineas


def test_vela_perdida_se_registra_y_no_se_opera(tmp_path):
    datos = datos_sinteticos()
    motor, fuente, indice = arrancar(tmp_path, datos)
    k = N_INICIAL + 20
    correr(motor, fuente, indice, N_INICIAL + 1, N_INICIAL + 40, saltar={k})
    perdida = indice[k - 1].strftime("%Y-%m-%dT%H:%M:%SZ")
    ev = motor.registro.eventos()
    assert any(e["tipo"] == "vela_perdida" and e["datos"]["fecha"] == perdida for e in ev)
    assert not any(e["tipo"] == "decision" and e["datos"]["fecha"] == perdida for e in ev)
    assert not any(e["tipo"] == "ejecucion" and e["datos"]["fecha_decision"] == perdida for e in ev)


def test_configuracion_cambiada_bloquea(tmp_path):
    datos = datos_sinteticos()
    motor, fuente, indice = arrancar(tmp_path, datos)
    otro = MotorVivo(motor.raiz, replace(main.Configuracion(), objetivo_volatilidad=0.5), ReglasSeguridad(), fuente)
    with pytest.raises(RuntimeError, match="congelada"):
        otro.ejecutar(indice[N_INICIAL + 1] + HORA)


def test_registro_manipulado_bloquea(tmp_path):
    datos = datos_sinteticos()
    motor, fuente, indice = arrancar(tmp_path, datos)
    correr(motor, fuente, indice, N_INICIAL + 1, N_INICIAL + 5)
    texto = motor.registro.texto()
    motor.registro.ruta.write_text(texto.replace('"cartera":"V8"', '"cartera":"V9"', 1), encoding="utf-8", newline="\n")
    with pytest.raises(RuntimeError, match="alterado"):
        MotorVivo(motor.raiz, main.Configuracion(), ReglasSeguridad(), fuente).ejecutar(indice[N_INICIAL + 6] + HORA)


def test_no_se_inicializa_dos_veces(tmp_path):
    datos = datos_sinteticos()
    motor, fuente, _ = arrancar(tmp_path, datos)
    with pytest.raises(RuntimeError, match="ya existe"):
        motor.inicializar(fuente.ahora)


def test_regla_de_parada(tmp_path):
    datos = datos_sinteticos()
    motor, fuente, indice = arrancar(tmp_path, datos, reglas=ReglasSeguridad(parada_drawdown=0.03))
    correr(motor, fuente, indice, N_INICIAL + 1, N_TOTAL)
    ev = motor.registro.eventos()
    paradas = [e for e in ev if e["tipo"] == "parada"]
    assert len(paradas) == 1
    n_parada = paradas[0]["n"]
    posteriores = [e for e in ev if e["n"] > n_parada and e["tipo"] == "decision" and e["datos"]["cartera"] == "V8"]
    assert posteriores and all(e["datos"]["exposicion_objetivo"] == 0.0 for e in posteriores)
    assert not any(e["n"] > n_parada and e["tipo"] == "ejecucion" and e["datos"]["cartera"] == "V8"
                   and e["datos"]["lado"] == "compra" for e in ev)
    for par in ("BTC/EUR", "ETH/EUR"):
        assert motor.estado("V8", par).unidades == 0
