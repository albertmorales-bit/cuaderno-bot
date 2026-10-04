"""
Commit de los archivos generados por el bot mediante la API GraphQL de GitHub
(`createCommitOnBranch`), para que GitHub lo firme y aparezca como verificado.

Se usa desde GitHub Actions con el GITHUB_TOKEN del propio workflow. Según la
documentación de GitHub, un commit creado por un bot a través de la API, sin
autor ni firma personalizados, queda marcado como verificado. A comprobar en la
primera ejecución real (ver GUIA_PUBLICACION.md).

`expectedHeadOid` hace el commit atómico: si la rama avanzó entretanto (otra
ejecución, un push manual), la API lo rechaza en vez de pisar nada.

Solo usa la biblioteca estándar. Variables de entorno: GITHUB_TOKEN,
GITHUB_REPOSITORY (dueño/repo) y opcionalmente RAMA (por defecto, main).
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CARPETAS = ("vivo", "web")   # lo único que el bot puede modificar


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, check=True).stdout


def archivos_cambiados() -> list[str]:
    salida = git("status", "--porcelain", "--untracked-files=all", "--", *CARPETAS)
    rutas = []
    for linea in salida.splitlines():
        estado, ruta = linea[:2], linea[3:].strip().strip('"')
        if "D" in estado:
            sys.exit(f"El bot no borra archivos y aparece un borrado: {ruta}. Se aborta.")
        rutas.append(ruta)
    fuera = [r for r in git("status", "--porcelain").splitlines() if not r[3:].startswith(CARPETAS)]
    if fuera:
        sys.exit(f"Hay cambios fuera de {CARPETAS}: {fuera}. El bot no los commitea; se aborta.")
    return rutas


def main() -> None:
    rutas = archivos_cambiados()
    if not rutas:
        print("Nada que commitear.")
        return
    resumen = json.loads((RAIZ / "vivo" / "ultimo_resumen.json").read_text(encoding="utf-8")) \
        if (RAIZ / "vivo" / "ultimo_resumen.json").exists() else {}
    titulo = f"Día {resumen.get('dia', '?')} · hash {resumen.get('hash_dia', '?')[:12]}"
    variables = {"input": {
        "branch": {"repositoryNameWithOwner": os.environ["GITHUB_REPOSITORY"],
                   "branchName": os.environ.get("RAMA", "main")},
        "message": {"headline": titulo, "body": "Commit automático del paper trading (dinero ficticio)."},
        "expectedHeadOid": git("rev-parse", "HEAD").strip(),
        "fileChanges": {"additions": [
            {"path": r, "contents": base64.b64encode((RAIZ / r).read_bytes()).decode()} for r in rutas]},
    }}
    consulta = ("mutation($input: CreateCommitOnBranchInput!) { createCommitOnBranch(input: $input) "
                "{ commit { oid url } } }")
    peticion = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": consulta, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {os.environ['GITHUB_TOKEN']}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(peticion, timeout=60) as r:
        respuesta = json.loads(r.read())
    if respuesta.get("errors"):
        sys.exit(f"Error de la API de GitHub: {respuesta['errors']}")
    commit = respuesta["data"]["createCommitOnBranch"]["commit"]
    print(f"{titulo} → {commit['url']}")


if __name__ == "__main__":
    main()
