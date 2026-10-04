#!/usr/bin/env python3
"""
Probability of Backtest Overfitting (PBO) - Auditor Anti-Overfitting

Implementa Combinatorially Symmetric Cross-Validation (CSCV), el metodo de
Bailey, Borwein, Lopez de Prado y Zhu (2014), "The Probability of Backtest
Overfitting", Journal of Computational Finance.

A diferencia del Deflated Sharpe Ratio (deflated_sharpe en significancia.py),
que se conforma con UNA sola serie de resultados (la variante ganadora) y
aproxima la dispersion entre variantes con la varianza propia, el PBO exige
los resultados REALES de todas las configuraciones candidatas -- no hay forma
honesta de aproximarlo con menos datos. Por eso este script solo tiene
sentido cuando el cliente aporta reglas parametrizables (input B, ver
criterios-operativos.md seccion 1) y se genero una rejilla de variantes real
sobre datos historicos con el motor Bot-Predict (yfinance/ccxt). Si el
cliente solo trae un CSV de operaciones ya cerradas (input A) con una unica
configuracion, el PBO no se puede calcular con rigor -- el informe se apoya
en el Deflated Sharpe Ratio para esa parte del analisis.

Formato de entrada esperado: CSV con una fila por periodo (cronologico) y una
columna por variante, con la rentabilidad de cada variante en ese periodo
(equity curve periodica, no operaciones sueltas -- las variantes no operan
los mismos dias, asi que hay que alinearlas en el calendario, con 0% en los
periodos sin operacion abierta):

    fecha,variante_1,variante_2,variante_3,...
    2024-01-02,0.00,0.15,-0.05,...
    2024-01-03,0.42,0.00,0.00,...
    ...

Uso:
    python3 pbo.py variantes.csv [--bloques S] [--metrica sharpe]
"""
import csv
import math
import argparse
from statistics import mean, pstdev
from itertools import combinations


MIN_BLOQUE = 5   # advertencia si algun bloque queda con menos periodos que esto
PBO_UMBRAL_GATE = 0.50    # decision de politica (2026-09-14): unico punto no arbitrario -- por encima,
                          # elegir la configuracion ganadora fue peor o igual que elegir al azar
PBO_UMBRAL_AVISO = 0.20   # por encima de esto (y por debajo del gate) se avisa mas fuerte en el informe


def leer_variantes(path):
    """Lee el CSV -> (nombres_variantes, matriz T x N como lista de listas)."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        nombres = header[1:]
        filas = []
        for r in reader:
            if not r:
                continue
            filas.append([float(x) for x in r[1:]])
    return nombres, filas


def dividir_bloques(t, s):
    """Parte T periodos en S bloques contiguos lo mas iguales posible.
    Devuelve una lista de S listas de indices de fila."""
    base = t // s
    resto = t % s
    bloques = []
    inicio = 0
    for i in range(s):
        tam = base + (1 if i < resto else 0)
        bloques.append(list(range(inicio, inicio + tam)))
        inicio += tam
    return bloques


def _sharpe_de_momentos(suma, suma_cuadrados, n):
    """Sharpe simple (media/desviacion poblacional) a partir de momentos agregados,
    para no recorrer la serie entera en cada combinacion (ver pbo_cscv)."""
    if n < 2:
        return 0.0
    mu = suma / n
    var = suma_cuadrados / n - mu * mu
    if var <= 0:
        return 0.0
    return mu / math.sqrt(var)


def pbo_cscv(nombres, matriz, s=16):
    """
    Combinatorially Symmetric Cross-Validation.

    matriz: lista de T filas, cada una con N valores (uno por variante),
    ya alineada en el tiempo.
    s: numero de bloques en que se parte el histórico (debe ser par).
    Devuelve un dict con el PBO, la distribucion de lambdas, y diagnosticos.

    Nota de implementacion: en vez de recortar la serie completa en cada una
    de las C(S,S/2) combinaciones (coste O(T) por variante y por combinacion,
    inviable para S=16 con miles de combinaciones), se precalculan suma y
    suma de cuadrados por bloque y por variante una sola vez, y cada
    combinacion se resuelve sumando esos agregados por bloque (coste O(S)).
    El resultado es matematicamente identico a calcular el Sharpe sobre la
    serie recortada; solo cambia la velocidad.
    """
    t = len(matriz)
    n = len(nombres)
    if s % 2 != 0:
        raise ValueError("El numero de bloques (--bloques) debe ser par.")
    if n < 2:
        raise ValueError("Hacen falta al menos 2 variantes para poder comparar (columnas del CSV).")

    bloques = dividir_bloques(t, s)
    tam_min_bloque = min(len(b) for b in bloques)
    aviso_bloque_pequeno = tam_min_bloque < MIN_BLOQUE

    # Momentos agregados por bloque y por variante: block_n[b], block_sum[j][b], block_sumsq[j][b]
    block_n = [len(b) for b in bloques]
    block_sum = [[0.0] * s for _ in range(n)]
    block_sumsq = [[0.0] * s for _ in range(n)]
    for b, idxs in enumerate(bloques):
        for i in idxs:
            fila = matriz[i]
            for j in range(n):
                v = fila[j]
                block_sum[j][b] += v
                block_sumsq[j][b] += v * v

    total_n = t
    total_sum = [sum(block_sum[j]) for j in range(n)]
    total_sumsq = [sum(block_sumsq[j]) for j in range(n)]

    combos = list(combinations(range(s), s // 2))
    lambdas = []

    for combo_train in combos:
        n_is = sum(block_n[b] for b in combo_train)
        n_oos = total_n - n_is
        if n_is < 2 or n_oos < 2:
            continue

        r_is = []
        r_oos = []
        for j in range(n):
            sum_is = sum(block_sum[j][b] for b in combo_train)
            sumsq_is = sum(block_sumsq[j][b] for b in combo_train)
            r_is.append(_sharpe_de_momentos(sum_is, sumsq_is, n_is))
            sum_oos = total_sum[j] - sum_is
            sumsq_oos = total_sumsq[j] - sumsq_is
            r_oos.append(_sharpe_de_momentos(sum_oos, sumsq_oos, n_oos))

        n_estrella = max(range(n), key=lambda j: r_is[j])
        orden = sorted(range(n), key=lambda j: r_oos[j])  # ascendente
        rango = orden.index(n_estrella) + 1  # 1 = peor, n = mejor
        omega = rango / (n + 1)  # en (0,1), evita bordes exactos 0/1
        omega = min(max(omega, 1e-6), 1 - 1e-6)
        lam = math.log(omega / (1 - omega))
        lambdas.append(lam)

    total = len(lambdas)
    pbo = sum(1 for lam in lambdas if lam <= 0) / total

    return dict(
        pbo=pbo,
        n_combinaciones=total,
        n_bloques=s,
        tam_min_bloque=tam_min_bloque,
        aviso_bloque_pequeno=aviso_bloque_pequeno,
        lambdas=lambdas,
    )


def elegir_s_por_defecto(t, s_max=16):
    """Elige el mayor S par <= s_max tal que cada bloque tenga >= MIN_BLOQUE periodos."""
    s = s_max if s_max % 2 == 0 else s_max - 1
    while s >= 4:
        if t // s >= MIN_BLOQUE:
            return s
        s -= 2
    return 4  # minimo operativo; se avisara si aun asi los bloques son pequenos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--bloques", type=int, default=None,
                     help="numero de bloques S para CSCV (par). Por defecto se elige "
                          "automaticamente segun el tamano de la serie (hasta 16).")
    args = ap.parse_args()

    nombres, matriz = leer_variantes(args.csv_path)
    t = len(matriz)
    n = len(nombres)
    s = args.bloques if args.bloques else elegir_s_por_defecto(t)

    print(f"Periodos: {t}  |  Variantes: {n} ({', '.join(nombres)})")
    print(f"Bloques (S): {s}  |  combinaciones CSCV a evaluar: C({s},{s//2})")

    resultado = pbo_cscv(nombres, matriz, s=s)

    print(f"Tamano minimo de bloque: {resultado['tam_min_bloque']} periodos", end="")
    if resultado["aviso_bloque_pequeno"]:
        print(f"  [AVISO: por debajo de {MIN_BLOQUE}, el resultado es menos fiable -- "
              f"considera bajar --bloques o aportar mas historico]")
    else:
        print()
    print()
    print(f"PBO (probabilidad de que la configuracion ganadora in-sample sea overfitting): "
          f"{resultado['pbo']*100:.1f}%")
    print(f"(calculado sobre {resultado['n_combinaciones']} particiones combinatorias in/out-of-sample)")
    print()
    if resultado["pbo"] >= PBO_UMBRAL_GATE:
        print(f"Interpretacion: PBO >= {PBO_UMBRAL_GATE:.0%} -- elegir esta configuracion como la mejor fue, "
              f"en las particiones probadas, peor o igual que elegir al azar entre las variantes. "
              f"GATE: esto fuerza MUESTRA INSUFICIENTE en el veredicto final (ver significancia.py --pbo), "
              f"aunque el bootstrap y el DSR del tramo out-of-sample parezcan buenos.")
    elif resultado["pbo"] >= PBO_UMBRAL_AVISO:
        print(f"Interpretacion: PBO moderado (entre {PBO_UMBRAL_AVISO:.0%} y {PBO_UMBRAL_GATE:.0%}) -- hay algo "
              f"de senal, pero una parte no desdeñable de por que esta configuracion parecio la mejor in-sample "
              f"es suerte de haber buscado, no ventaja real. No fuerza el veredicto por si solo, pero se avisa "
              f"en el informe (ver significancia.py --pbo).")
    else:
        print(f"Interpretacion: PBO bajo (< {PBO_UMBRAL_AVISO:.0%}) -- la configuracion que mejor sale in-sample "
              f"tiende tambien a comportarse bien out-of-sample, consistente con ventaja real y no con haber "
              f"elegido la mejor de un grupo de variantes sin ventaja.")
    print()
    print("Pasa este numero a significancia.py con --pbo para que se incorpore al veredicto final:")
    print(f"    python3 significancia.py operaciones_de_la_variante_ganadora.csv --pbo {resultado['pbo']:.4f}")


if __name__ == "__main__":
    main()
