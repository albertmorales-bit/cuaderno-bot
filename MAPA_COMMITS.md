# Correspondencia de commits (reescritura previa a la publicación)

El 2026-10-04, ANTES de publicar el repositorio por primera vez, se reescribió el autor de los commits
existentes (de un email personal al email *noreply* de GitHub) y se firmaron. Al cambiar el autor cambia el
identificador de cada commit, pero no su contenido, su fecha ni su orden. Se comprobó que el árbol final es
idéntico byte a byte.

Varios archivos citan los identificadores ANTIGUOS, porque se escribieron antes de la reescritura y no se han
tocado: `datos/v1/MANIFIESTO.json` y `datos/v1/CALIDAD.md` (094a4a8), `informes/fase4/VALIDACION_ABIERTA.txt`,
`VALIDACION_RESULTADOS.md` y `validacion.json` (e594140), y `ESTADO.md` y `DECISIONES.md`. Esta tabla los
traduce a los nuevos.

Límite, dicho claro: antes de la publicación no había ningún ancla externa (X, OpenTimestamps) de los
identificadores antiguos, así que esta tabla no añade ninguna prueba; solo permite seguir las referencias. Las
pruebas verificables empiezan con el pre-registro y su tuit del día 0.

| Fecha | Antiguo | Nuevo | Commit |
|---|---|---|---|
| 2026-10-04 11:08 | `5c98d762d7` | `bd377de109` | Punto de partida: módulos v4 extraídos del cuaderno sin modificar |
| 2026-10-04 11:23 | `b2cead3c2c` | `7eaca6d99f` | Fase 0: auditoría, arreglos del motor, v5 Donchian, partición OOS y tests |
| 2026-10-04 11:34 | `094a4a84a0` | `50a7edb6bb` | Fase 1: módulo de histórico versionado y scripts de construcción de datos |
| 2026-10-04 11:35 | `b0a8083d6d` | `8d27fcbb87` | Fase 1: datos/v1 congelados (BTC/EUR y ETH/EUR diario) y documentación |
| 2026-10-04 11:39 | `48d119887f` | `794368ff65` | Reserva final hasta 2026-05-01: todas las variantes v1-v4 se ejecutaron el 2026-09-04 |
| 2026-10-04 11:42 | `3ba86de968` | `6160027ab3` | Fase 1b: investigación citada de familias de estrategias y recomendación |
| 2026-10-04 18:27 | `c02be78962` | `8ceb44ce62` | Fase 2 (antes de ejecutar): conjunto Donchian, objetivo de volatilidad, motor por exposición, regímenes y criterios |
| 2026-10-04 18:30 | `210c095590` | `9c84cd13a8` | Fase 2: resultados del diagnóstico por regímenes en el tramo de desarrollo |
| 2026-10-04 18:38 | `06e7a06957` | `25468ea401` | Fase 4 (antes de ejecutar): criterios de aceptación v1, módulo de validación y scripts |
| 2026-10-04 18:39 | `e594140e4a` | `c29b2ec766` | Fase 4: robustez en desarrollo (meseta, costes, años, bootstrap, Sharpe deflactado) |
| 2026-10-04 18:42 | `86014609bc` | `10e4bc52f3` | Fase 4: validación abierta una sola vez · veredicto NO APTO |
| 2026-10-04 19:07 | `cc065dd51e` | `a2a732e59d` | Fase 5: registro encadenado, motor en vivo y test de repetición |
| 2026-10-04 19:14 | `50d8643f73` | `a064409124` | Fase 5: script diario, commit firmado vía API, sello OpenTimestamps, pre-registro, workflow y guía |
| 2026-10-04 19:30 | `3f3dea7b09` | `69ff3bb5b4` | Fase 6: salidas diarias para X (resumen, tuit, comentario, hilo semanal e imagen) |
| 2026-10-04 19:31 | `0449557f56` | `48fc28dbd2` | Fase 6: documentación y control de longitud de X en el pre-registro |
| 2026-10-04 19:45 | `0ed92cc7c9` | `7dc5044c92` | Fase 7: web de transparencia (GitHub Pages) con botón Verificar |
| 2026-10-04 19:50 | `3645f7367b` | `d4d90f9310` | Enlaces de publicación con el usuario de GitHub (albertmorales-bit) |
