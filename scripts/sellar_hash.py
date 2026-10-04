"""
Ancla el hash del día en Bitcoin con OpenTimestamps (gratis, sin cuenta).

Escribe `vivo/sellos/AAAA-MM-DD.txt` con el hash del día y crea su prueba
`.ots` mediante los servidores de calendario públicos. Las pruebas de días
anteriores se actualizan (`ots upgrade`) cuando el calendario ya las ha
incluido en un bloque de Bitcoin, normalmente unas horas después.

Es un ancla ADICIONAL: si falla (calendarios caídos), el workflow sigue y el
ancla principal es la hora de publicación del tuit en X. Cualquiera puede
verificar una prueba en https://opentimestamps.org subiendo el .txt y su .ots.

Requiere `opentimestamps-client` (solo se instala en el runner de Linux de
GitHub Actions; en Windows su dependencia python-bitcoinlib no encuentra libssl).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SELLOS = RAIZ / "vivo" / "sellos"


def main() -> None:
    resumen = json.loads((RAIZ / "vivo" / "ultimo_resumen.json").read_text(encoding="utf-8"))
    fecha = resumen["ahora"][:10]
    SELLOS.mkdir(parents=True, exist_ok=True)
    archivo = SELLOS / f"{fecha}.txt"
    if not archivo.exists():
        archivo.write_text(f"{resumen['hash_dia']}\n", encoding="utf-8", newline="\n")
        subprocess.run(["ots", "stamp", str(archivo)], check=True)
    for prueba in sorted(SELLOS.glob("*.ots")):
        subprocess.run(["ots", "upgrade", str(prueba)], check=False)   # pendiente = código distinto de 0: normal
    for copia in SELLOS.glob("*.bak"):
        copia.unlink()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:   # noqa: BLE001
        print(f"Sello OpenTimestamps no disponible hoy: {exc}", file=sys.stderr)
        sys.exit(1)
