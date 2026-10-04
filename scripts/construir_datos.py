"""
Construye una versión congelada del histórico diario (Fase 1).

Uso (PowerShell, desde la raíz del repositorio):
    .venv\\Scripts\\python scripts\\construir_datos.py --version v1

Descarga cada fuente de `modulo_1b_historico.FUENTES`, guarda los CSV crudos,
los diagnostica y compara, construye la serie limpia (principal: coinbase,
respaldo: bitstamp) y escribe `datos/<version>/MANIFIESTO.json` con el
SHA-256 de cada archivo y `datos/<version>/CALIDAD.md` legible.

No sobrescribe una versión existente: los datos publicados no se tocan; si
hace falta cambiar algo, se crea una versión nueva.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modulo_1b_historico import (  # noqa: E402
    FUENTES,
    RAIZ_DATOS,
    comparar_fuentes,
    construir_serie_limpia,
    descargar_fuente,
    diagnosticar_calidad,
    escribir_manifiesto,
    guardar_csv,
    nombre_archivo,
)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s | %(name)s | %(message)s")

PRINCIPAL, RESPALDO = "coinbase", "bitstamp"


def commit_actual() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "desconocido"


def arbol_limpio() -> bool:
    """True si no hay cambios sin commitear fuera de datos/ (que es lo que se genera)."""
    try:
        salida = subprocess.run(["git", "status", "--porcelain", "--", ".", ":(exclude)datos"],
                                capture_output=True, text=True, check=True).stdout
        return salida.strip() == ""
    except Exception:
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v1")
    ap.add_argument("--inicio", default="2014-01-01")
    ap.add_argument("--fin", default="2026-10-01", help="exclusiva; fija el final de la versión")
    ap.add_argument("--intervalo", default="1d")
    args = ap.parse_args()

    directorio = RAIZ_DATOS / args.version
    if (directorio / "MANIFIESTO.json").exists():
        sys.exit(f"datos/{args.version} ya existe y no se sobrescribe. Usa otra --version.")

    manifiesto: dict = {
        "version": args.version,
        "creado_utc": pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit_codigo": commit_actual(),
        # False = había cambios sin commitear en el código al generar los datos.
        "arbol_git_limpio": arbol_limpio(),
        "rango_pedido": {"inicio": args.inicio, "fin_exclusiva": args.fin},
        "intervalo": args.intervalo,
        "convencion": "marca de tiempo = apertura de vela, UTC; solo velas cerradas",
        "principal": PRINCIPAL,
        "respaldo": RESPALDO,
        "archivos": {},
        "simbolos": {},
    }

    for simbolo, fuentes in FUENTES.items():
        print(f"\n=== {simbolo} ===")
        series: dict[str, pd.DataFrame] = {}
        info: dict = {"fuentes": {}, "comparaciones": {}, "incidencias": []}
        for fuente in fuentes:
            try:
                df = descargar_fuente(fuente, args.inicio, args.fin, args.intervalo)
            except Exception as exc:
                print(f"  {fuente.nombre:9s} ERROR: {exc}")
                info["fuentes"][fuente.nombre] = {"error": str(exc)}
                continue
            series[fuente.nombre] = df
            nombre = nombre_archivo(simbolo, args.intervalo, f"_crudo_{fuente.nombre}")
            manifiesto["archivos"][f"crudo/{nombre}"] = guardar_csv(df, directorio / "crudo" / nombre)
            calidad = diagnosticar_calidad(df, args.intervalo)
            calidad["proveedor"] = f"{fuente.proveedor}:{fuente.simbolo}"
            info["fuentes"][fuente.nombre] = calidad
            print(f"  {fuente.nombre:9s} {calidad['velas']:5d} velas {calidad['desde'][:10]} -> "
                  f"{calidad['hasta'][:10]} | huecos {calidad['huecos']} | OHLC mal "
                  f"{calidad['ohlc_incoherente']} | vol 0: {calidad['volumen_cero']} | "
                  f"extremos {len(calidad['movimientos_extremos'])}")

        if PRINCIPAL not in series:
            print(f"  Sin fuente principal para {simbolo}: no se construye serie limpia.")
            manifiesto["simbolos"][simbolo] = info
            continue

        for nombre, df in series.items():
            if nombre == PRINCIPAL:
                continue
            comp = comparar_fuentes(series[PRINCIPAL], df)
            info["comparaciones"][f"{nombre}_vs_{PRINCIPAL}"] = comp
            if comp["dias_comunes"]:
                print(f"  {nombre:9s} vs {PRINCIPAL}: {comp['dias_comunes']} días comunes | mediana "
                      f"{comp['mediana_dif_pct']} % | p95 {comp['p95_dif_pct']} % | máx {comp['max_dif_pct']} %")

        limpia, incidencias = construir_serie_limpia(
            series[PRINCIPAL], series.get(RESPALDO), PRINCIPAL, RESPALDO, args.intervalo
        )
        info["incidencias"] = incidencias
        info["serie_limpia"] = diagnosticar_calidad(limpia, args.intervalo)
        info["serie_limpia"]["filas_por_fuente"] = limpia["fuente"].value_counts().to_dict()
        manifiesto["archivos"][nombre_archivo(simbolo, args.intervalo)] = guardar_csv(
            limpia, directorio / nombre_archivo(simbolo, args.intervalo)
        )
        print(f"  Serie limpia: {len(limpia)} velas, incidencias {len(incidencias)}, "
              f"filas por fuente {info['serie_limpia']['filas_por_fuente']}")
        manifiesto["simbolos"][simbolo] = info

    ruta = escribir_manifiesto(directorio, manifiesto)
    print(f"\nManifiesto: {ruta}")


if __name__ == "__main__":
    main()
