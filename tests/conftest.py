"""Utilidades compartidas por los tests (sin red: todo con datos sintéticos)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "validacion"))
sys.path.insert(0, str(RAIZ / "scripts"))
logging.disable(logging.INFO)


def velas_sinteticas(n: int = 800, semilla: int = 7, frecuencia: str = "1D") -> pd.DataFrame:
    """Paseo aleatorio con tendencias alternas y OHLC coherente
    (High >= max(Open, Close), Low <= min(Open, Close))."""
    rng = np.random.default_rng(semilla)
    deriva = np.where((np.arange(n) // 150) % 2 == 0, 0.002, -0.0015)
    cierre = 100 * np.exp(np.cumsum(deriva + rng.normal(0, 0.02, n)))
    apertura = np.concatenate([[cierre[0]], cierre[:-1]]) * (1 + rng.normal(0, 0.002, n))
    alto = np.maximum(apertura, cierre) * (1 + rng.random(n) * 0.015)
    bajo = np.minimum(apertura, cierre) * (1 - rng.random(n) * 0.015)
    indice = pd.date_range("2018-01-01", periods=n, freq=frecuencia, tz="UTC")
    return pd.DataFrame(
        {"Open": apertura, "High": alto, "Low": bajo, "Close": cierre, "Volume": 1.0}, index=indice
    )


def marco_motor(n: int = 10, precio: float = 100.0, atr: float = 1.0) -> pd.DataFrame:
    """Marco plano listo para el motor: señales a 0, sin calentamiento.
    Cada test escribe a mano sus eventos (`entrada`) y estados (`senal`)."""
    indice = pd.date_range("2024-01-01", periods=n, freq="1D", tz="UTC")
    return pd.DataFrame(
        {
            "Open": precio, "High": precio + 0.5, "Low": precio - 0.5, "Close": precio,
            "Volume": 1.0, "atr": atr, "entrada": 0, "senal": 0, "calentamiento_ok": True,
        },
        index=indice,
    )


@pytest.fixture
def velas() -> pd.DataFrame:
    return velas_sinteticas()
