"""
Construye la carpeta publicable de la web de transparencia.

    .venv\\Scripts\\python scripts\\construir_web.py            # _site/ con los datos reales de vivo/
    .venv\\Scripts\\python scripts\\construir_web.py --demo     # _site_demo/ con un experimento SINTÉTICO

El sitio es la carpeta web/ (HTML, CSS y JS sin dependencias) más copias
exactas de vivo/registro.jsonl, vivo/configuracion_congelada.json,
PREREGISTRO.md y PREREGISTRO.md.sha256. La página recalcula todo a partir
del registro. La demostración lleva una banda bien visible y nunca se publica.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def construir(destino: Path, vivo: Path) -> Path:
    shutil.rmtree(destino, ignore_errors=True)
    shutil.copytree(RAIZ / "web", destino)
    for origen, nombre in ((vivo / "registro.jsonl", "registro.jsonl"),
                           (vivo / "configuracion_congelada.json", "configuracion_congelada.json"),
                           (RAIZ / "PREREGISTRO.md", "PREREGISTRO.md"),
                           (RAIZ / "PREREGISTRO.md.sha256", "PREREGISTRO.md.sha256")):
        if origen.exists():
            shutil.copyfile(origen, destino / nombre)   # copia byte a byte: el hash no cambia
    (destino / ".nojekyll").write_text("", encoding="utf-8")
    return destino


def demo() -> Path:
    """Experimento simulado de 45 días con datos sintéticos, solo para revisar la página."""
    sys.path[:0] = [str(RAIZ), str(RAIZ / "tests")]
    from modulo_7_registro import Registro
    from test_vivo import N_INICIAL, arrancar, correr, datos_sinteticos

    trabajo = RAIZ / "_demo_trabajo"
    shutil.rmtree(trabajo, ignore_errors=True)
    motor, fuente, indice = arrancar(trabajo, datos_sinteticos())
    correr(motor, fuente, indice, N_INICIAL + 1, N_INICIAL + 46, saltar={N_INICIAL + 30})
    # Marca la demostración en un registro aparte (el bueno nunca lleva esta marca).
    marcado = trabajo / "vivo_demo"
    marcado.mkdir()
    eventos = motor.registro.eventos()
    registro = Registro(marcado / "registro.jsonl")
    for e in eventos:
        datos = dict(e["datos"], demo=True) if e["tipo"] == "inicio" else e["datos"]
        registro.anadir(e["tipo"], datos, ts_utc=e["ts_utc"])
    shutil.copyfile(motor.ruta_config, marcado / "configuracion_congelada.json")
    return construir(RAIZ / "_site_demo", marcado)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    args = ap.parse_args()
    print(demo() if args.demo else construir(RAIZ / "_site", RAIZ / "vivo"))
