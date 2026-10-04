"""
Ejecución diaria del paper trading (la llama GitHub Actions; también se puede
lanzar a mano). CERO órdenes reales: solo datos públicos de Kraken.

Uso (PowerShell, desde la raíz):
    .venv\\Scripts\\python scripts\\ejecutar_diario.py --inicializar   # día 0, una sola vez
    .venv\\Scripts\\python scripts\\ejecutar_diario.py                 # cada día

Sale con código 1 si algo falla (registro alterado, configuración cambiada,
red caída tras los reintentos): Actions lo marca en rojo y el día queda como
vela perdida, visible en el panel.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import main  # noqa: E402
from modulo_8_vivo import CARTERAS, FuenteKraken, MotorVivo, ReglasSeguridad  # noqa: E402
from modulo_9_salidas import generar_salidas  # noqa: E402

logging.disable(logging.INFO)
DIRECTORIO_VIVO = RAIZ / "vivo"


def commit_actual() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=RAIZ, capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:
        return "desconocido"


def dia_del_experimento(motor: MotorVivo) -> int:
    """Día N = número de ciclos operados (con decisión) desde el inicio."""
    fechas = sorted({e["datos"]["fecha"] for e in motor.registro.eventos() if e["tipo"] == "decision"})
    return len(fechas)


def cerrar_si_procede(motor: MotorVivo, reglas: ReglasSeguridad, ahora: pd.Timestamp) -> None:
    ev = motor.registro.eventos()
    if any(e["tipo"] == "fin_experimento" for e in ev) or dia_del_experimento(motor) < reglas.dias_experimento:
        return
    ultimas = {}
    for e in ev:
        if e["tipo"] == "valoracion":
            ultimas[(e["datos"]["cartera"], e["datos"]["par"])] = e["datos"]
    equity = {c.nombre: sum(v["equity"] for (cart, _), v in ultimas.items() if cart == c.nombre) for c in CARTERAS}
    motor.registro.anadir("fin_experimento", {
        "dias": reglas.dias_experimento, "equity_final": equity,
        "nota": "Fin de los 90 días pre-registrados. El motor puede seguir valorando, pero el experimento termina aquí.",
    }, ahora)


def main_diario() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inicializar", action="store_true")
    ap.add_argument("--raiz", default=str(DIRECTORIO_VIVO))
    args = ap.parse_args()
    reglas = ReglasSeguridad()
    motor = MotorVivo(Path(args.raiz), main.Configuracion(), reglas, FuenteKraken())
    ahora = pd.Timestamp.now(tz="UTC")
    if args.inicializar:
        evento = motor.inicializar(ahora, commit=commit_actual())
        print(json.dumps(evento["datos"], indent=2, ensure_ascii=False))
        return
    resumen = motor.ejecutar(ahora)
    cerrar_si_procede(motor, reglas, ahora)
    if any(c.get("completado") for c in resumen["ciclos"]):   # Fase 6: resumen, tuit, imagen e hilo del día
        publicacion = json.loads((RAIZ / "publicacion.json").read_text(encoding="utf-8"))
        carpeta = generar_salidas(Path(args.raiz), motor.config.comision_pct, motor.config.slippage_pct,
                                  publicacion["url_web"], publicacion["url_repo"])
        resumen["salidas"] = str(carpeta.relative_to(RAIZ)) if carpeta and carpeta.is_relative_to(RAIZ) else str(carpeta)
    resumen["dia"] = dia_del_experimento(motor)
    resumen["hash_dia"] = motor.registro.verificar().ultimo_hash
    ruta = Path(args.raiz) / "ultimo_resumen.json"
    previo = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    if previo.get("hash_dia") != resumen["hash_dia"]:   # solo si el registro cambió: sin commits vacíos
        ruta.write_text(json.dumps(resumen, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(resumen, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main_diario()
    except Exception as exc:   # noqa: BLE001 - se informa y se sale con error a propósito
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
