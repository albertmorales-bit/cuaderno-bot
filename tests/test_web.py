"""Web de transparencia: el JavaScript real de web/app.js (ejecutado con Node)
verifica la cadena y calcula las mismas cifras que Python."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import main
from modulo_9_salidas import construir_estado
from test_vivo import N_INICIAL, arrancar, correr, datos_sinteticos

RAIZ = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js no está instalado")

HARNESS = """
const fs = require("fs");
const app = require(process.argv[2]);
(async () => {
  const texto = fs.readFileSync(process.argv[3], "utf8");
  const v = await app.verificarCadena(texto);
  const c = app.calcular(app.leerEventos(texto), { comision: 0.008, slippage: 0.001 });
  const r = (x) => ({ equity: x.equity, caidaActual: x.caidaActual, caidaMaxima: x.caidaMaxima, acumulado: x.acumulado });
  console.log(JSON.stringify({ valido: v.valido, lineas: v.lineas, ultimo: v.ultimo, linea: v.linea || null,
    dia: c.dia, V8: r(c.resumen.V8), FIJO30: r(c.resumen.FIJO30), BH100: r(c.resumen.BH100), n: c.fechas.length }));
})();
"""


@pytest.fixture(scope="module")
def registro(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("web")
    motor, fuente, indice = arrancar(tmp, datos_sinteticos())
    correr(motor, fuente, indice, N_INICIAL + 1, N_INICIAL + 26, saltar={N_INICIAL + 12})
    (tmp / "harness.js").write_text(HARNESS, encoding="utf-8")
    return motor, tmp


def ejecutar_js(tmp: Path, ruta_registro: Path) -> dict:
    salida = subprocess.run([NODE, str(tmp / "harness.js"), str(RAIZ / "web" / "app.js"), str(ruta_registro)],
                            capture_output=True, text=True, check=True)
    return json.loads(salida.stdout)


def test_js_verifica_igual_que_python(registro):
    motor, tmp = registro
    js = ejecutar_js(tmp, motor.registro.ruta)
    py = motor.registro.verificar(completa=True)
    assert js["valido"] and py.valido and js["lineas"] == py.lineas and js["ultimo"] == py.ultimo_hash


def test_js_calcula_las_mismas_cifras_que_python(registro):
    motor, tmp = registro
    js = ejecutar_js(tmp, motor.registro.ruta)
    config = main.Configuracion()
    e = construir_estado(motor.registro.eventos(), motor.registro.verificar().ultimo_hash,
                         config.comision_pct, config.slippage_pct)
    assert js["dia"] == e.dia and js["n"] == len(e.series)
    for c in ("V8", "FIJO30", "BH100"):
        assert js[c]["equity"] == pytest.approx(e.carteras[c].equity, rel=1e-12)
        assert js[c]["caidaActual"] == pytest.approx(e.carteras[c].caida_actual, abs=1e-12)
        assert js[c]["caidaMaxima"] == pytest.approx(e.carteras[c].caida_maxima, abs=1e-12)


def test_js_detecta_una_alteracion(registro):
    motor, tmp = registro
    lineas = motor.registro.texto().split("\n")
    lineas[40] = lineas[40].replace("0", "1", 1)
    alterado = tmp / "alterado.jsonl"
    alterado.write_text("\n".join(lineas), encoding="utf-8", newline="\n")
    js = ejecutar_js(tmp, alterado)
    assert not js["valido"] and js["linea"] == 41


def test_construir_web_copia_byte_a_byte(registro, tmp_path, monkeypatch):
    import construir_web

    motor, _ = registro
    destino = construir_web.construir(tmp_path / "_site", motor.raiz)
    assert (destino / "registro.jsonl").read_bytes() == motor.registro.ruta.read_bytes()
    assert (destino / "index.html").exists() and (destino / ".nojekyll").exists()
