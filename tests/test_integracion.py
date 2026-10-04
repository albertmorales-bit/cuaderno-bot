"""Pipeline completo sin red: causalidad de extremo a extremo y coherencia
entre `Configuracion` y los módulos."""

import inspect

import pandas as pd
import pytest

import main
from conftest import velas_sinteticas
from modulo_2_estrategia import generar_senales
from modulo_4_backtesting import MotorBacktest


def _operaciones(config, velas):
    df = generar_senales(velas, **main.kwargs_senales(config))
    return MotorBacktest(main.parametros_backtest(config, "BTC/EUR")).ejecutar(df).trades


@pytest.mark.parametrize("disparador", ["ruptura_donchian", "pullback"])
def test_anadir_velas_futuras_no_cambia_operaciones_pasadas(disparador):
    """Precursor del test de repetición de la Fase 4: un motor que solo
    conoce el pasado debe reproducir exactamente las operaciones ya
    cerradas del backtest con todo el histórico."""
    config = main.Configuracion(disparador_entrada=disparador)
    velas = velas_sinteticas(n=1500, semilla=3)
    completo = _operaciones(config, velas)
    for k in (900, 1200):
        corte = velas.index[k - 1]
        parcial = [t for t in _operaciones(config, velas.iloc[:k]) if t.motivo_salida != "fin_de_datos"]
        esperado = [t for t in completo if t.fecha_salida <= corte]
        assert len(parcial) > 0
        assert [(t.fecha_entrada, t.fecha_salida, round(t.pnl_neto, 9)) for t in parcial] == \
               [(t.fecha_entrada, t.fecha_salida, round(t.pnl_neto, 9)) for t in esperado]


def test_kwargs_de_configuracion_existen_en_generar_senales():
    parametros = inspect.signature(generar_senales).parameters
    assert set(main.kwargs_senales(main.CONFIG)) <= set(parametros)


def test_periodos_anuales_se_derivan_del_intervalo():
    assert main.Configuracion(intervalo="1d").periodos_anuales() == 365
    assert main.Configuracion(intervalo="4h").periodos_anuales() == 2190


def test_pipeline_con_datos_locales(tmp_path, capsys):
    config = main.Configuracion(ruta_grafico=str(tmp_path / "eq.png"))
    resultado = main.ejecutar_pipeline(config, datos=velas_sinteticas(n=1500, semilla=5))
    assert resultado.metricas["num_trades"] > 0
    assert "FUERA DE MUESTRA" in capsys.readouterr().out


def test_multiactivo_con_datos_locales():
    config = main.Configuracion()
    datos = {"BTC/EUR": velas_sinteticas(n=1200, semilla=1), "ETH/EUR": velas_sinteticas(n=1200, semilla=2)}
    r = main.ejecutar_pipeline_multiactivo(config, datos_por_activo=datos)
    assert set(r.resultados_por_activo) == {"BTC/EUR", "ETH/EUR"}
    assert r.resultado_combinado.curva_capital.iloc[0] == pytest.approx(10_000.0)


def test_historico_truncado_aborta_en_vez_de_seguir(monkeypatch):
    """Auditoría P1: la v4 seguía adelante con 120 días cuando pedía 3 años."""
    corto = velas_sinteticas(n=120)
    monkeypatch.setattr(main.ProveedorDatos, "__init__", lambda self, exchange_id="kraken": None)
    monkeypatch.setattr(main.ProveedorDatos, "obtener_datos", lambda self, params: corto)
    with pytest.raises(ValueError, match="cubre"):
        main.descargar(main.Configuracion(periodo_historico="3y"), "BTC/EUR")


def test_datos_v1_en_disco_pasan_el_checksum():
    """Solo comprueba que los datos congelados se cargan íntegros. NO ejecuta
    la estrategia sobre ellos (eso contaría como mirar los datos)."""
    for simbolo in ("BTC/EUR", "ETH/EUR"):
        df = main.obtener_velas(main.Configuracion(fecha_fin="2022-01-01"), simbolo)
        assert df.index.max() < pd.Timestamp("2022-01-01", tz="UTC")
        assert df.index.is_monotonic_increasing and not df.index.duplicated().any()
        assert set(df["fuente"].unique()) <= {"coinbase", "bitstamp"}


def test_conjunto_desde_configuracion_con_datos_locales():
    config = main.Configuracion()
    r = main.ejecutar_conjunto(config, "BTC/EUR", datos=velas_sinteticas(n=1500, semilla=8))
    assert 0 < r.metricas["exposicion_media"] <= 1
    assert r.curva_capital.index[0] == velas_sinteticas(n=1500, semilla=8).index[config.velas_calentamiento]
    assert all(o.precio_referencia > 0 for o in r.operaciones)
