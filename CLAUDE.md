# Reglas permanentes del proyecto (cuaderno-bot)

Bot de trading cripto en **paper trading** público durante 90 días para la serie
"Día N de 90 con 10.000 € ficticios" (@cuadernoalbert, El Cuaderno de Albert).

## No negociables

1. **Cero órdenes reales.** Ninguna clave API con permisos de trading, ningún
   envío de órdenes. Solo datos públicos de mercado.
2. **Honestidad total.** Nada de embellecer resultados, ajustar mirando el fuera
   de muestra ni elegir la mejor variante a posteriori sin descontarla. Un
   resultado malo se dice tal cual. Si hay sospecha de lookahead, fuga de datos
   o error propio, se avisa ANTES de presentar resultados.
3. **No afirmar que el bot es rentable** salvo que lo respalden los criterios
   pre-registrados y el paper trading en vivo.
4. **Pérdidas con el mismo detalle que las ganancias.** Siempre capital total y
   curva completa, nunca solo la parte favorable.
5. **Nada se cambia a mitad del experimento** sin versión nueva documentada y
   reinicio del contador.
6. **Tamaño de muestra e incertidumbre siempre visibles.** Con pocas
   operaciones, la conclusión es "insuficiente para concluir".
7. **Contador de variantes honesto.** Cada configuración evaluada suma (ver
   `VALIDACION.md`). Al usar `validacion/significancia.py`, `--variantes` con
   ese número, nunca el 1 por defecto.
8. **Benchmark obligatorio:** toda métrica junto a comprar y mantener y a
   efectivo, también ajustada por riesgo.

## Estilo de trabajo

- Responder en español. Código comentado, PEP 8, tipado donde aporte.
- Módulos separados; todo parametrizado desde `Configuracion` (`main.py`).
  Los argumentos de los módulos se construyen SOLO en `kwargs_senales` y
  `parametros_backtest`: backtest y motor en vivo usan el mismo código.
- Fase a fase. Al terminar cada una: qué se hizo, qué se probó, resultado
  real, limitaciones y decisiones abiertas. Actualizar `ESTADO.md` y
  `DECISIONES.md`.
- Windows (PowerShell) y Colab: `pathlib`, nada de comandos solo de Linux.
- Si faltan datos o red, decirlo y proponer alternativa; nunca inventar datos.
- Tuits: máximo 280 caracteres verificados con `len()` (enlace = 23).
  Sin enlaces en el tuit principal. Siempre la nota "dinero ficticio, no es
  asesoramiento financiero, resultados pasados no garantizan nada".

## Comprobar antes de entregar

```powershell
.venv\Scripts\python -m pytest -q
```
