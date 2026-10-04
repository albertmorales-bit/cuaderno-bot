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
| `modulo_4b_exposicion.py` | Motor por exposición objetivo (0-1) con banda de reajuste; benchmarks con los mismos costes |
| `modulo_5_regimenes.py` | Regímenes causales (tendencia, volatilidad, fuerza), atribución y bootstrap por bloques |
| `modulo_6_validacion.py` | Ventanas que arrancan sin posición, benchmarks, bootstrap, Sharpe deflactado, actividad esperada |
| `modulo_7_registro.py` | Registro JSONL encadenado con SHA-256, verificable sin re-serializar |
| `modulo_8_vivo.py` | Motor de paper trading en vivo (mismo código que el backtest), idempotente |
| `modulo_9_salidas.py` | Resumen, tuit (longitud real de X), comentario, hilo semanal e imagen del día |
| `main.py` | `Configuracion` central y orquestación (uno o varios activos, diagnóstico) |
| `validacion/` | `significancia.py` y `pbo.py` (Auditor Anti-Overfitting), sin modificar |
| `scripts/` | Datos, análisis de las fases 2 y 4, `ejecutar_diario.py`, `commit_firmado.py`, `sellar_hash.py`, `preregistro.py` |
| `.github/workflows/diario.yml` | Ejecución diaria en GitHub Actions |
| `vivo/` | Archivo de velas, registro encadenado y sellos del experimento (lo escribe el bot) |
| `informes/` | Criterios fijados antes de cada análisis y sus resultados |
| `datos/` | Datos congelados por versión: CSV crudos por fuente, serie limpia, `MANIFIESTO.json`, `CALIDAD.md` |
| `tests/` | pytest, sin red |
| `web/` | Panel de transparencia (GitHub Pages): recalcula todo desde el registro y verifica la cadena en el navegador |
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

Publicar y arrancar: [`GUIA_PUBLICACION.md`](GUIA_PUBLICACION.md).

Ver la web con datos de demostración (sintéticos) en local:

```powershell
.venv\Scripts\python scripts\construir_web.py --demo
.venv\Scripts\python -m http.server 8341 --directory _site_demo
```
