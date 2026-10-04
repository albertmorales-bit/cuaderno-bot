"""
=============================================================================
 BOT-PREDICT · MÓDULO 7: Registro de transparencia encadenado (Fase 5)
=============================================================================

Archivo append-only (JSONL). Cada línea es un evento y contiene el hash
SHA-256 de la línea anterior: alterar, borrar o reordenar cualquier línea
rompe la cadena desde ese punto y es detectable por cualquiera.

Formato de una línea (D-031):

    {"datos":{...},"hash_anterior":"<64 hex>","n":7,"tipo":"decision","ts_utc":"2026-..."},"hash":"<64 hex>"}

dicho con precisión: `contenido` es el JSON canónico del evento SIN el campo
`hash` (claves ordenadas, sin espacios, UTF-8); `hash = sha256(contenido)`; y la
línea escrita es `contenido` con `,"hash":"<hash>"` insertado antes de la
última llave. El verificador (Python aquí, JavaScript en la web) recupera
`contenido` quitando ese sufijo del TEXTO de la línea, sin volver a
serializar nada. Así no importa que cada lenguaje escriba los números de
forma distinta.

La primera línea encadena con `hash_anterior = "0" * 64`. El "hash del día"
que se publica en X es el `hash` de la última línea.
=============================================================================
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pandas as pd

GENESIS = "0" * 64
_SUFIJO = re.compile(r'^(?P<contenido>.*),"hash":"(?P<hash>[0-9a-f]{64})"}$')


def _limpiar(valor: Any) -> Any:
    """Convierte tipos de numpy/pandas a tipos JSON y rechaza NaN/inf."""
    if isinstance(valor, dict):
        return {str(k): _limpiar(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_limpiar(v) for v in valor]
    if isinstance(valor, pd.Timestamp):
        return valor.strftime("%Y-%m-%dT%H:%M:%SZ")
    if hasattr(valor, "item") and not isinstance(valor, (str, bytes)):
        valor = valor.item()
    if isinstance(valor, float) and not math.isfinite(valor):
        raise ValueError("El registro no admite NaN ni infinitos.")
    return valor


def contenido_canonico(evento: dict) -> str:
    return json.dumps(_limpiar(evento), sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def sha256_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


@dataclass
class ResultadoVerificacion:
    valido: bool
    lineas: int
    ultimo_hash: str
    error: Optional[str] = None
    linea_error: Optional[int] = None


def verificar_texto(texto: str) -> ResultadoVerificacion:
    """Verifica la cadena completa a partir del texto del archivo."""
    anterior, n = GENESIS, 0
    for numero, linea in enumerate(texto.split("\n"), start=1):
        if linea == "":
            continue
        n += 1
        m = _SUFIJO.match(linea)
        if not m:
            return ResultadoVerificacion(False, n, anterior, "formato de línea inválido", numero)
        contenido, h = m.group("contenido") + "}", m.group("hash")
        if sha256_texto(contenido) != h:
            return ResultadoVerificacion(False, n, anterior, "el hash no corresponde al contenido", numero)
        evento = json.loads(contenido)
        if evento.get("hash_anterior") != anterior:
            return ResultadoVerificacion(False, n, anterior, "la línea no encadena con la anterior", numero)
        if evento.get("n") != n:
            return ResultadoVerificacion(False, n, anterior, "numeración rota (línea borrada o insertada)", numero)
        anterior = h
    return ResultadoVerificacion(True, n, anterior)


class Registro:
    """Registro encadenado en `ruta`. Solo se puede añadir al final."""

    def __init__(self, ruta: Path) -> None:
        self.ruta = Path(ruta)
        # Caché (huella del archivo, verificación, eventos). La huella es el
        # tamaño y la fecha de modificación en nanosegundos: cualquier cambio
        # hecho fuera de `anadir` la altera y obliga a verificar todo de nuevo.
        self._cache: Optional[tuple[tuple[int, int], ResultadoVerificacion, list[dict]]] = None

    def texto(self) -> str:
        return self.ruta.read_text(encoding="utf-8") if self.ruta.exists() else ""

    def _huella(self) -> tuple[int, int]:
        if not self.ruta.exists():
            return (0, 0)
        st = self.ruta.stat()
        return (st.st_size, st.st_mtime_ns)

    def _cargar(self) -> tuple[ResultadoVerificacion, list[dict]]:
        huella = self._huella()
        if self._cache is not None and self._cache[0] == huella:
            return self._cache[1], self._cache[2]
        texto = self.texto()
        verificacion = verificar_texto(texto)
        eventos = []
        if verificacion.valido:
            for linea in texto.split("\n"):
                if linea:
                    m = _SUFIJO.match(linea)
                    evento = json.loads(m.group("contenido") + "}")
                    evento["hash"] = m.group("hash")
                    eventos.append(evento)
        self._cache = (huella, verificacion, eventos)
        return verificacion, eventos

    def verificar(self, completa: bool = False) -> ResultadoVerificacion:
        if completa:
            self._cache = None
        return self._cargar()[0]

    def eventos(self) -> list[dict]:
        verificacion, eventos = self._cargar()
        if not verificacion.valido:
            raise RuntimeError(f"Registro alterado (línea {verificacion.linea_error}: {verificacion.error}).")
        return [dict(e) for e in eventos]

    def anadir(self, tipo: str, datos: dict, ts_utc: Optional[pd.Timestamp] = None) -> dict:
        """Añade un evento al final, encadenado con el último. Verifica antes
        la cadena: nunca se escribe sobre un registro ya alterado."""
        verificacion = self.verificar()
        if not verificacion.valido:
            raise RuntimeError(f"Registro alterado (línea {verificacion.linea_error}: {verificacion.error}). "
                               "No se escribe nada más.")
        ts = pd.Timestamp.now(tz="UTC") if ts_utc is None else pd.Timestamp(ts_utc)
        evento = {
            "n": verificacion.lineas + 1,
            "ts_utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tipo": tipo,
            "datos": datos,
            "hash_anterior": verificacion.ultimo_hash,
        }
        contenido = contenido_canonico(evento)
        h = sha256_texto(contenido)
        linea = contenido[:-1] + f',"hash":"{h}"' + "}"
        assert _SUFIJO.match(linea) and sha256_texto(_SUFIJO.match(linea).group("contenido") + "}") == h
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with self.ruta.open("a", encoding="utf-8", newline="\n") as f:
            f.write(linea + "\n")
            f.flush()
            os.fsync(f.fileno())
        evento = json.loads(contenido)
        evento["hash"] = h
        eventos_previos = self._cache[2] if self._cache is not None else []
        self._cache = (self._huella(), ResultadoVerificacion(True, verificacion.lineas + 1, h),
                       eventos_previos + [evento])
        return dict(evento)
