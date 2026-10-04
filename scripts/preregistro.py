"""
Genera PREREGISTRO.md (día 0): versión exacta, configuración congelada,
criterios, reglas de seguridad y de parada, resultados de validación y
actividad esperada. Calcula su SHA-256 y prepara el tuit del día 0.

Se ejecuta UNA vez, con el árbol de git limpio, justo antes de arrancar:
    .venv\\Scripts\\python scripts\\preregistro.py
Después: commit firmado de PREREGISTRO.md, tag firmado y publicar el tuit
(ver GUIA_PUBLICACION.md).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import main  # noqa: E402
from modulo_8_vivo import CARTERAS, PARES, ReglasSeguridad, configuracion_congelada, hash_configuracion  # noqa: E402

ARCHIVOS_HUELLA = [
    "main.py", "modulo_1_datos.py", "modulo_1b_historico.py", "modulo_2_estrategia.py", "modulo_3_riesgo.py",
    "modulo_4_backtesting.py", "modulo_4b_exposicion.py", "modulo_5_regimenes.py", "modulo_6_validacion.py",
    "modulo_7_registro.py", "modulo_8_vivo.py", "requirements.txt", "datos/v1/MANIFIESTO.json",
    "informes/fase4/CRITERIOS_ACEPTACION.md", "informes/fase4/validacion.json",
]
LIMITE_TUIT = 280


def es(x: float, decimales: int = 1, signo: bool = False) -> str:
    """Número con coma decimal, como se escribe en español."""
    return f"{x:{'+' if signo else ''}.{decimales}f}".replace(".", ",")


def sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, check=True).stdout.strip()


def tuit_dia_0(hash_prereg: str) -> str:
    texto = ("Día 0 de 90 con 10.000 € ficticios.\n\n"
             "Bot de tendencia en BTC y ETH. En mi propio test fuera de muestra salió NO APTO: "
             "no batió a tener ~30 % invertido fijo. Lo arranco igual, sin tocar nada, "
             "con una cartera del 30 % fijo al lado.\n\n"
             f"Pre-registro SHA-256: {hash_prereg[:16]}…")
    if len(texto) > LIMITE_TUIT:
        raise ValueError(f"El tuit del día 0 tiene {len(texto)} caracteres (máx. {LIMITE_TUIT}).")
    return texto


def main_prereg() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", default=str(RAIZ / "PREREGISTRO.md"))
    ap.add_argument("--permitir-cambios", action="store_true", help="solo para pruebas")
    args = ap.parse_args()
    if git("status", "--porcelain") and not args.permitir_cambios:
        sys.exit("Árbol de git con cambios sin commitear: el pre-registro debe fijar una versión exacta.")
    salida = Path(args.salida)
    if salida.exists() and not args.permitir_cambios:
        sys.exit(f"{salida} ya existe: el pre-registro se hace una sola vez.")

    config, reglas = main.Configuracion(), ReglasSeguridad()
    congelada = configuracion_congelada(config, reglas)
    val = json.loads((RAIZ / "informes/fase4/validacion.json").read_text(encoding="utf-8"))
    des = json.loads((RAIZ / "informes/fase4/desarrollo.json").read_text(encoding="utf-8"))
    act = des["actividad_90_dias"]
    commit = git("rev-parse", "HEAD")
    m8, mb, mi = val["cartera"]["V8"], val["cartera"]["BH100"], val["cartera"]["BHigual"]

    L = [
        "# Pre-registro · Día 0 de 90", "",
        "> **Dinero ficticio, no es asesoramiento financiero, resultados pasados no garantizan nada.**", "",
        f"Generado el {pd.Timestamp.now(tz='UTC'):%Y-%m-%d %H:%M} UTC sobre el commit `{commit}`. "
        "Nada de lo que aquí se fija se cambia durante los 90 días. Cualquier cambio exige una versión nueva "
        "del experimento, con el contador a cero, y se documenta en público.", "",
        "## 1. Qué es y qué no es", "",
        "- Paper trading: **cero órdenes reales**, solo datos públicos de Kraken (BTC/EUR y ETH/EUR, velas diarias).",
        "- La estrategia (variante 8) **salió NO APTO** en su validación fuera de muestra (2022-01 → 2024-06): "
        f"ganó un {es(m8['rent_total_pct'], 1, True)} % con una caída máxima del {es(m8['max_dd_pct'], 0)} % (comprar y "
        f"mantener: {es(mb['rent_total_pct'], 1, True)} % / {es(mb['max_dd_pct'], 0)} %), pero **no batió** a tener "
        f"invertida de forma fija la misma exposición media, en torno al 30 % (Sharpe {es(m8['sharpe'], 2)} frente a "
        f"{es(mi['sharpe'], 2)}; probabilidad de ser mejor {es(val['S2_p_igual'], 2)}; Sharpe deflactado "
        f"{es(val['S1_dsr']['dsr'], 2)}). Detalle: "
        "`informes/fase4/VALIDACION_RESULTADOS.md`.",
        "- Se arranca igualmente para poner a prueba **el proceso** (ejecución fiable, registro verificable, "
        "honestidad de las cuentas) y comparar en vivo con la alternativa trivial.",
        f"- En 90 días se esperan **{es(act['entradas_esperadas'])} entradas nuevas** (intervalo del 90 % "
        f"{act['entradas_ic90'][0]}-{act['entradas_ic90'][1]}) y **{act['ordenes_esperadas']:.0f} órdenes** "
        f"({act['ordenes_ic90'][0]}-{act['ordenes_ic90'][1]}). **90 días no pueden demostrar rentabilidad**; "
        "lo que se publique se presentará así.", "",
        "## 2. Carteras", "",
        "| Cartera | Qué hace | Capital |", "|---|---|---|",
        "| V8 | Conjunto Donchian 20/10, 55/20 y 100/50 (solo largos) con objetivo de volatilidad del 40 % y banda de "
        "reajuste de 10 puntos | 10.000 € (5.000 € por activo) |",
        "| FIJO30 | 30 % invertido de forma fija en cada activo, misma banda de reajuste | 10.000 € (5.000 € por activo) |", "",
        "Las dos con comisión del 0,80 % (Kraken Pro, taker, nivel 1) y slippage del 0,10 % por orden. Decisión con la "
        "vela diaria cerrada (00:00 UTC) y ejecución simulada en la apertura de la vela siguiente. Sin "
        "apalancamiento, sin cortos y sin funding.", "",
        "**Riesgo del día 1, declarado de antemano:** si al arrancar los sistemas ya están \"en tendencia\", la V8 "
        "comprará en la primera apertura sin esperar a una ruptura nueva, que es como se validó. Puede comprar en un "
        "máximo.", "",
        "## 3. Reglas de seguridad y de parada", "",
        f"- **Parada del experimento:** si la cartera V8 cae un {reglas.parada_drawdown * 100:.0f} % desde su máximo, se "
        "liquida en la siguiente apertura, se detiene y se publica.",
        f"- Avisos visibles (no cambian nada): pérdida diaria ≥ {reglas.alerta_perdida_diaria * 100:.0f} %, semanal ≥ "
        f"{reglas.alerta_perdida_semanal * 100:.0f} %, {reglas.alerta_velas_perdidas_seguidas} o más días seguidos "
        "sin ejecutarse.",
        f"- Salto de precio sospechoso (más del {reglas.salto_sospechoso * 100:.0f} % en una vela): ese día no se "
        "decide y se "
        "mantiene la posición.",
        "- Un día en que el bot no se ejecute queda como **vela perdida**: no se opera sobre ella a posteriori.",
        f"- Duración: {reglas.dias_experimento} días de decisión. Después se publica el resultado final, sea cual sea.", "",
        "## 4. Qué se publicará al final", "",
        "- Integridad: la cadena de hashes del registro completa y verificable; número de velas perdidas.",
        "- Las dos carteras: rentabilidad, Sharpe, caída máxima, operaciones, comisiones y slippage, frente a "
        "comprar y mantener al 100 %.",
        "- Sin afirmar ninguna ventaja: con este tamaño de muestra, cualquier diferencia entre V8 y FIJO30 se "
        "presentará como **no concluyente**.", "",
        "## 5. Configuración congelada", "",
        f"SHA-256 de la configuración: `{hash_configuracion(congelada)}`. El motor se niega a ejecutarse si cambia.", "",
        "```json", json.dumps(congelada, indent=2, ensure_ascii=False), "```", "",
        "## 6. Huellas del código y de los datos", "",
        "| Archivo | SHA-256 |", "|---|---|",
        *[f"| `{a}` | `{sha256(RAIZ / a)}` |" for a in ARCHIVOS_HUELLA], "",
        f"Pares: {', '.join(PARES)}. Carteras: {', '.join(c.nombre for c in CARTERAS)}. Variantes probadas antes de "
        "arrancar: 8. Tramo de reserva (2024-07 → 2026-05): sin abrir.", "",
    ]
    salida.write_text("\n".join(L), encoding="utf-8", newline="\n")
    h = sha256(salida)
    (salida.parent / (salida.name + ".sha256")).write_text(f"{h}  {salida.name}\n", encoding="utf-8", newline="\n")
    tuit = tuit_dia_0(h)
    print(f"{salida.name}: SHA-256 {h}\n\nTuit del día 0 ({len(tuit)} caracteres):\n\n{tuit}")


if __name__ == "__main__":
    main_prereg()
