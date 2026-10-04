# Pre-registro · Día 0 de 90

> **Dinero ficticio, no es asesoramiento financiero, resultados pasados no garantizan nada.**

Generado el 2026-10-04 18:05 UTC sobre el commit `411728c8fb41bc1dbb061d1951933084e4560630`. Nada de lo que aquí se fija se cambia durante los 90 días. Cualquier cambio exige una versión nueva del experimento, con el contador a cero, y se documenta en público.

## 1. Qué es y qué no es

- Paper trading: **cero órdenes reales**, solo datos públicos de Kraken (BTC/EUR y ETH/EUR, velas diarias).
- La estrategia (variante 8) **salió NO APTO** en su validación fuera de muestra (2022-01 → 2024-06): ganó un +22,6 % con una caída máxima del -23 % (comprar y mantener: +15,7 % / -66 %), pero **no batió** a tener invertida de forma fija la misma exposición media, en torno al 30 % (Sharpe 0,48 frente a 0,46; probabilidad de ser mejor 0,49; Sharpe deflactado 0,24). Detalle: `informes/fase4/VALIDACION_RESULTADOS.md`.
- Se arranca igualmente para poner a prueba **el proceso** (ejecución fiable, registro verificable, honestidad de las cuentas) y comparar en vivo con la alternativa trivial.
- En 90 días se esperan **1,3 entradas nuevas** (intervalo del 90 % 0-3) y **10 órdenes** (5-16). **90 días no pueden demostrar rentabilidad**; lo que se publique se presentará así.

## 2. Carteras

| Cartera | Qué hace | Capital |
|---|---|---|
| V8 | Conjunto Donchian 20/10, 55/20 y 100/50 (solo largos) con objetivo de volatilidad del 40 % y banda de reajuste de 10 puntos | 10.000 € (5.000 € por activo) |
| FIJO30 | 30 % invertido de forma fija en cada activo, misma banda de reajuste | 10.000 € (5.000 € por activo) |

Las dos con comisión del 0,80 % (Kraken Pro, taker, nivel 1) y slippage del 0,10 % por orden. Decisión con la vela diaria cerrada (00:00 UTC) y ejecución simulada en la apertura de la vela siguiente. Sin apalancamiento, sin cortos y sin funding.

**Riesgo del día 1, declarado de antemano:** si al arrancar los sistemas ya están "en tendencia", la V8 comprará en la primera apertura sin esperar a una ruptura nueva, que es como se validó. Puede comprar en un máximo.

## 3. Reglas de seguridad y de parada

- **Parada del experimento:** si la cartera V8 cae un 35 % desde su máximo, se liquida en la siguiente apertura, se detiene y se publica.
- Avisos visibles (no cambian nada): pérdida diaria ≥ 10 %, semanal ≥ 20 %, 3 o más días seguidos sin ejecutarse.
- Salto de precio sospechoso (más del 50 % en una vela): ese día no se decide y se mantiene la posición.
- Un día en que el bot no se ejecute queda como **vela perdida**: no se opera sobre ella a posteriori.
- Duración: 90 días de decisión. Después se publica el resultado final, sea cual sea.

## 4. Qué se publicará al final

- Integridad: la cadena de hashes del registro completa y verificable; número de velas perdidas.
- Las dos carteras: rentabilidad, Sharpe, caída máxima, operaciones, comisiones y slippage, frente a comprar y mantener al 100 %.
- Sin afirmar ninguna ventaja: con este tamaño de muestra, cualquier diferencia entre V8 y FIJO30 se presentará como **no concluyente**.

## 5. Configuración congelada

SHA-256 de la configuración: `6ab80b0368056ab62a9311d46ce54101cae9062382968e4d59f603e785281cb4`. El motor se niega a ejecutarse si cambia.

```json
{
  "configuracion": {
    "fuente_datos": "disco",
    "version_datos": "v1",
    "ticker": "BTC/EUR",
    "tipo_activo": "cripto",
    "exchange_id": "kraken",
    "intervalo": "1d",
    "periodo_historico": "3y",
    "fecha_inicio": null,
    "fecha_fin": null,
    "activos": [
      "BTC/EUR",
      "ETH/EUR"
    ],
    "tamanos_minimos": {
      "BTC/EUR": 5e-05,
      "ETH/EUR": 0.001
    },
    "cobertura_minima_pct": 95.0,
    "capital_inicial": 10000.0,
    "riesgo_por_operacion": 0.01,
    "ratio_riesgo_beneficio": 2.0,
    "usar_take_profit": false,
    "interes_compuesto": true,
    "disparador_entrada": "ruptura_donchian",
    "periodo_ruptura_entrada": 20,
    "periodo_ruptura_salida": 10,
    "ema_rapida": 20,
    "ema_lenta": 50,
    "periodo_atr": 14,
    "periodo_rsi": 14,
    "usar_filtro_rsi": false,
    "permitir_cortos": false,
    "atr_mult_stop_largo": 2.0,
    "atr_mult_stop_corto": 1.5,
    "factor_calentamiento_ema": 2.0,
    "usar_filtro_macro": true,
    "periodo_ema_macro": 200,
    "usar_adx": false,
    "periodo_adx": 14,
    "umbral_adx": 18.0,
    "comision_pct": 0.008,
    "slippage_pct": 0.001,
    "sistemas_donchian": [
      [
        20,
        10
      ],
      [
        55,
        20
      ],
      [
        100,
        50
      ]
    ],
    "objetivo_volatilidad": 0.4,
    "ventana_volatilidad": 30,
    "banda_reajuste": 0.1,
    "velas_calentamiento": 400,
    "fraccion_oos": 0.3,
    "divisa": "€",
    "periodos_por_anio": null,
    "unidades_fraccionables": true,
    "permitir_apalancamiento": false,
    "ruta_grafico": "equity_drawdown.png"
  },
  "reglas": {
    "parada_drawdown": 0.35,
    "alerta_perdida_diaria": 0.1,
    "alerta_perdida_semanal": 0.2,
    "alerta_velas_perdidas_seguidas": 3,
    "salto_sospechoso": 0.5,
    "dias_experimento": 90
  },
  "carteras": [
    {
      "nombre": "V8",
      "exposicion_fija": null
    },
    {
      "nombre": "FIJO30",
      "exposicion_fija": 0.3
    }
  ],
  "pares": [
    "BTC/EUR",
    "ETH/EUR"
  ]
}
```

## 6. Huellas del código y de los datos

| Archivo | SHA-256 |
|---|---|
| `main.py` | `75a46c3b3b3e429fbbbcaeb5012bf4a3fd2ad26108143a381cf7f68e0daadb93` |
| `modulo_1_datos.py` | `61961a13f6a975ec905cc5d1645ee7a39c2be1c5875d58f21d0d06f4fc7109dd` |
| `modulo_1b_historico.py` | `24537e0061c919dce99d69f3a4d4fe1273b661e133fe530f703729ccbd1930c3` |
| `modulo_2_estrategia.py` | `c62c4f7c156efabd9053616bdee6aecb6515cfb31a1a2385cde14778fb1a6d40` |
| `modulo_3_riesgo.py` | `490ec8a4ffa1718566d43945e3cbeeb227b16e211c56dacc256c1c624d48f8f0` |
| `modulo_4_backtesting.py` | `33682ef7bfbad2058531cf1329b9c19ee48bbc9f2271dfcc11c3bf300795eac8` |
| `modulo_4b_exposicion.py` | `ca82a52a016270f8c6da2b12035ca64330d3c39bc360a4e4759bf436d2ec2498` |
| `modulo_5_regimenes.py` | `293745204eec3cb5cfe8fc27741a31d2a18bb50a016bfc0f1e8762163f5f8b46` |
| `modulo_6_validacion.py` | `008034f5d670a8caf7fbcbfcd81506d16a02e7bb34262ddcb46f1b91c4df67d8` |
| `modulo_7_registro.py` | `4b41462543db631bc6ccef5d1c966f6c6a7e3a35d439739c8225674d377fac2b` |
| `modulo_8_vivo.py` | `9cf4586cef961ad245e4ff984ea79146bad857a5cb2d9debdfebae868fe113a6` |
| `modulo_9_salidas.py` | `2300febcaef2a53345536ebb405da3a4a385f643b2d0fb9ad8f6ed1a8d089c4d` |
| `requirements.txt` | `40e14ff4b02551ffe127dd2e450034a6946c214e9efc2058fea5cd69b97b86f7` |
| `publicacion.json` | `462029066ef86b6bdd7868e8ad2538eaaaadda634d1431deefc7ec0701303c88` |
| `datos/v1/MANIFIESTO.json` | `3bd81e7998a463784b0538679802f8b5c70f0826981869c8c33c74d1d201601e` |
| `informes/fase4/CRITERIOS_ACEPTACION.md` | `aa043223d51efb14fda57d03f2295b0c1bb2dafcb3ff9bcfeb13b0f2eabb3e3b` |
| `informes/fase4/validacion.json` | `b178b789907f1414d2acdd5dbe0e53aa1b47d0fb4ec7cffa30b7d092431a8422` |
| `web/index.html` | `8abd1e13eb4604f446db5e04e1da300fba734990a392817d3761f780d4b42d7e` |
| `web/app.js` | `3f5f1498a577ea56662a43be5f55fe15e5028185e0e00eaa425d94952e4f0678` |
| `web/styles.css` | `60023f2a74e42696438c93895f6a3e92af5b58581d421be07aab2aeff60becba` |
| `.github/workflows/diario.yml` | `6ef352355959f41f1b5c35b39e8769a96a09f36457d436eef520e83a5b1784ea` |

Pares: BTC/EUR, ETH/EUR. Carteras: V8, FIJO30. Variantes probadas antes de arrancar: 8. Tramo de reserva (2024-07 → 2026-05): sin abrir.
