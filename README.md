# cuaderno-bot

Bot de trading cripto en **paper trading** (dinero ficticio) para la serie
"Día N de 90 con 10.000 € ficticios" de El Cuaderno de Albert.

> Dinero ficticio, no es asesoramiento financiero, resultados pasados no garantizan nada.

Estado del proyecto: ver [`ESTADO.md`](ESTADO.md). Decisiones y su motivo:
[`DECISIONES.md`](DECISIONES.md). Resultados y variantes probadas:
[`VALIDACION.md`](VALIDACION.md). Evidencia revisada antes de diseñar:
[`INVESTIGACION.md`](INVESTIGACION.md).

## Arquitectura

| Archivo | Responsabilidad |
|---------|-----------------|
| `modulo_1_datos.py` | Descarga unificada (ccxt / yfinance), limpieza, solo velas cerradas |
| `modulo_1b_historico.py` | Histórico largo multi-fuente: diagnóstico, comparación, serie limpia, versionado con SHA-256 |
| `modulo_2_estrategia.py` | Indicadores y señales: Donchian (v5), pullback (v4), cruce EMA (v3); filtros de régimen |
| `modulo_3_riesgo.py` | Tamaño por riesgo fijo, stop por ATR, tope sin apalancamiento, mínimos de orden |
| `modulo_4_backtesting.py` | Motor vela a vela, costes, métricas, partición con embargo, exportación CSV |
| `main.py` | `Configuracion` central y orquestación (uno o varios activos, diagnóstico) |
| `validacion/` | `significancia.py` y `pbo.py` (Auditor Anti-Overfitting), sin modificar |
| `scripts/` | `construir_datos.py` (crea `datos/<versión>`) e `informe_datos.py` (`CALIDAD.md`) |
| `datos/` | Datos congelados por versión: CSV crudos por fuente, serie limpia, `MANIFIESTO.json`, `CALIDAD.md` |
| `tests/` | pytest, sin red |
| `notebooks/` | Cuaderno de Colab original de la v4 (histórico; no es la fuente del código) |

## Reproducir (Windows, PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest -q
```

En Colab: sube los `.py` (o clona el repositorio) y ejecuta
`!pip install -r requirements.txt` antes de importar `main`.

Datos: los backtests leen `datos/v1` (checksum verificado al cargar). Para
construir una versión nueva desde las APIs públicas:

```powershell
.venv\Scripts\python scripts\construir_datos.py --version v2 --fin 2027-01-01
.venv\Scripts\python scripts\informe_datos.py --version v2
```
