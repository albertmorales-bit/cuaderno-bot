#!/usr/bin/env python3
"""
Motor de significancia estadistica - Auditor Anti-Overfitting

Sustituye el umbral fijo de "30 operaciones minimo" por comprobaciones que se
adaptan a los datos reales de cada cliente:

  1. Embargo en la frontera in/out-of-sample (evita fuga de informacion).
  2. Bootstrap por bloques (no asume operaciones independientes entre si).
  3. Ajuste de N efectiva cuando hay varios activos correlacionados (cesta).
  4. Deflated Sharpe Ratio / PSR (descuenta la suerte de probar N variantes).
  5. Aviso de sesgo de supervivencia si la cesta no es point-in-time.
  6. Robustez del corte: repite el veredicto en 60/40, 70/30 y 80/20 y exige
     que coincidan antes de dar APTO o NO APTO.
  7. Probability of Backtest Overfitting (--pbo, calculado aparte con pbo.py
     sobre una rejilla real de variantes): gate adicional sobre el veredicto.
  8. Metricas de riesgo adicionales (Calmar, Ulcer Index, VaR/CVaR): se
     muestran junto a las metricas clasicas, no deciden el veredicto.
  9. Fraccion de Kelly (teorica y ajustada por incertidumbre via bootstrap
     de bloques): informativa sobre dimensionamiento, no decide el veredicto.

Uso:
    python3 significancia.py operaciones.csv [--conf 0.90] [--boot 10000]
                              [--variantes N] [--cesta-point-in-time] [--pbo P]

CSV esperado (mismas columnas que ya usa el proyecto):
    fecha_entrada,fecha_salida,activo,tipo,precio_entrada,precio_salida,resultado_%
"""
import csv
import math
import random
import argparse
import datetime as dt
from statistics import mean, pstdev
from itertools import combinations


PISO_ABSOLUTO = 5    # por debajo de esto, ni se calcula: no hay datos ni para un bootstrap razonable
PISO_FIABLE = 20      # por debajo de esto (en N efectiva), el bootstrap no decide el veredicto por si solo
EULER_MASCHERONI = 0.5772156649015329
RATIOS_ROBUSTEZ = [0.60, 0.70, 0.80]   # corte principal = 0.70, los otros dos son el chequeo de robustez


# ----------------------------------------------------------------------
# Lectura y particion
# ----------------------------------------------------------------------

def leer_operaciones(path):
    filas = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            filas.append(r)
    filas.sort(key=lambda r: r["fecha_entrada"])
    return filas


def particionar_con_embargo(filas, fraccion_is=0.7):
    """
    Parte cronologicamente en in-sample / out-of-sample, y EMBARGA (descarta de
    los dos tramos) cualquier operacion cuya entrada sea anterior al corte pero
    cuya salida sea posterior -- evita que una operacion "a caballo" filtre
    informacion de un tramo al otro.
    """
    n = len(filas)
    if n == 0:
        return [], [], []
    corte_idx = min(n - 1, max(0, int(round(n * fraccion_is))))
    fecha_corte = filas[corte_idx]["fecha_entrada"]

    is_trades = [t for t in filas if t["fecha_salida"] < fecha_corte]
    oos_trades = [t for t in filas if t["fecha_entrada"] >= fecha_corte]
    ids_usados = {id(t) for t in is_trades} | {id(t) for t in oos_trades}
    embargadas = [t for t in filas if id(t) not in ids_usados]
    return is_trades, oos_trades, embargadas


# ----------------------------------------------------------------------
# Metricas clasicas
# ----------------------------------------------------------------------

def curva_equity(pcts, base=100.0):
    """Curva de capital operacion a operacion (no diaria), reutilizada por MDD,
    Ulcer Index y Calmar."""
    equity = [base]
    for p in pcts:
        equity.append(equity[-1] * (1 + p / 100))
    return equity


def serie_drawdown(equity):
    """Drawdown (%) en cada punto de la curva de capital, respecto al pico previo."""
    peak = equity[0]
    serie = []
    for e in equity:
        peak = max(peak, e)
        serie.append((e - peak) / peak * 100)
    return serie


def metricas_clasicas(trades):
    pcts = [float(t["resultado_%"]) for t in trades]
    n = len(pcts)
    if n == 0:
        return None
    wins = [p for p in pcts if p > 0]
    losses = [p for p in pcts if p <= 0]
    win_rate = len(wins) / n * 100
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf")

    equity = curva_equity(pcts)
    rent_neta = (equity[-1] / equity[0] - 1) * 100
    mdd = min(serie_drawdown(equity))

    return dict(n=n, win_rate=win_rate, pf=pf, rent_neta=rent_neta, mdd=mdd)


# ----------------------------------------------------------------------
# Metricas de riesgo adicionales (Calmar, Ulcer Index, VaR/CVaR)
# ----------------------------------------------------------------------

def _fecha(s):
    return dt.date.fromisoformat(s[:10])


def calmar_ratio(trades, rent_neta, mdd):
    """
    Calmar = rentabilidad ANUALIZADA / |Max Drawdown|.
    Se anualiza con el numero real de dias que cubre el tramo (primera entrada
    a ultima salida) -- no un supuesto generico de frecuencia. None si el tramo
    cubre menos de 30 dias (anualizar sobre una ventana tan corta amplifica
    el numero hasta hacerlo inservible) o si el MDD es 0.
    """
    if not trades or mdd == 0:
        return None
    dias = (_fecha(trades[-1]["fecha_salida"]) - _fecha(trades[0]["fecha_entrada"])).days
    if dias < 30:
        return None
    factor_final = 1 + rent_neta / 100
    if factor_final <= 0:
        return None  # perdida total o mas: la anualizacion geometrica no esta definida
    rent_anualizada = (factor_final ** (365.25 / dias) - 1) * 100
    return rent_anualizada / abs(mdd)


def ulcer_index(equity):
    """RMS del drawdown en toda la curva -- a diferencia del MDD (el peor momento
    puntual), el Ulcer Index castiga pasar mucho tiempo en drawdown, no solo
    tocar un minimo profundo una vez."""
    serie = serie_drawdown(equity)
    return math.sqrt(mean(d * d for d in serie))


def var_cvar(pcts, conf=0.90):
    """
    VaR y CVaR (Expected Shortfall) historicos sobre la distribucion de
    resultado_% por operacion, al mismo nivel de confianza fijo del proyecto
    (90%, ver criterios-operativos.md seccion 2 -- nunca un numero distinto
    aqui tampoco, por la misma razon de objetividad).

    VaR: el retorno que separa el peor 10% de operaciones del resto (percentil
    10, metodo del peor-k para que tenga sentido tambien con muestras pequenas).
    CVaR: la media de ese peor 10% -- cuanto se pierde EN PROMEDIO cuando se cae
    en la cola mala, no solo donde empieza la cola.
    Ambos se devuelven como retorno (negativo = perdida), no como magnitud.
    """
    n = len(pcts)
    if n == 0:
        return None
    ordenados = sorted(pcts)
    k = max(1, round((1 - conf) * n))
    cola = ordenados[:k]
    var = cola[-1]           # el "mejor" de los peores k -- el limite de la cola
    cvar = mean(cola)        # la media de toda la cola
    return dict(var=var, cvar=cvar, n_cola=k)


# ----------------------------------------------------------------------
# Criterio de Kelly (dimensionamiento, informativo -- no decide el veredicto)
# ----------------------------------------------------------------------
#
# La formula clasica de Kelly (f* = p - (1-p)/b) asume que p (probabilidad de
# ganar) y b (ratio ganancia media / perdida media) son los valores REALES,
# no una estimacion sobre una muestra finita. Usar el punto estimado tal
# cual -- el error clasico -- sobreapalanca en cuanto la muestra es pequena
# o el resultado tiene algo de suerte metida, que es exactamente el problema
# que el resto de este motor existe para detectar. Por eso se calculan DOS
# numeros, no uno: el Kelly "de libro" (punto estimado) y un Kelly ajustado
# por incertidumbre, usando el mismo bootstrap por bloques ya validado en el
# resto del criterio pero aplicado a la fraccion de Kelly en si, no a la
# rentabilidad media -- y tomando el limite INFERIOR de ese intervalo como
# la cifra prudente.

def kelly_fraccion(pcts):
    """
    Fraccion de Kelly clasica sobre una lista de resultado_% de operaciones:
        f* = p - (1-p)/b
    p = proporcion de operaciones ganadoras, b = ganancia media / perdida
    media (en valor absoluto). None si no hay operaciones ganadoras Y
    perdedoras a la vez (el calculo no tiene sentido sin las dos).
    """
    wins = [p for p in pcts if p > 0]
    losses = [p for p in pcts if p <= 0]
    n = len(pcts)
    if n == 0 or not wins or not losses:
        return None
    p = len(wins) / n
    avg_win = mean(wins)
    avg_loss = abs(mean(losses))
    if avg_loss == 0:
        return None
    b = avg_win / avg_loss
    return p - (1 - p) / b


def kelly_bootstrap_ci(pcts, conf=0.90, n_boot=10000, seed=43, block=None):
    """
    Igual mecanica que bootstrap_ci_media (remuestreo por bloques contiguos,
    circular) pero calculando en cada remuestreo la fraccion de Kelly en vez
    de la rentabilidad media -- da un intervalo de confianza sobre CUANTO
    varia el Kelly estimado segun la incertidumbre real de la muestra.
    Semilla distinta a bootstrap_ci_media a proposito: son remuestreos
    independientes sobre el mismo criterio (bloques por raiz de n).
    Duplicado (no reutiliza bootstrap_ci_media) para no acoplar el calculo
    de Kelly a la mecanica interna de la funcion ya validada.
    None si n < PISO_ABSOLUTO, o si menos de la mitad de los remuestreos
    tuvieron ganadoras Y perdedoras a la vez (no hay base para un intervalo
    fiable -- tipico en tramos muy pequenos o con un signo muy dominante).
    """
    n = len(pcts)
    if n < PISO_ABSOLUTO:
        return None
    if block is None:
        block = max(2, round(n ** 0.5))
    block = min(block, n)

    rng = random.Random(seed)
    valores = []
    n_bloques = math.ceil(n / block)
    for _ in range(n_boot):
        muestra = []
        for _ in range(n_bloques):
            inicio = rng.randrange(n)
            for k in range(block):
                muestra.append(pcts[(inicio + k) % n])
        f = kelly_fraccion(muestra[:n])
        if f is not None:
            valores.append(f)

    if len(valores) < n_boot * 0.5:
        return None
    valores.sort()
    alpha = 1 - conf
    lo_idx = int(len(valores) * (alpha / 2))
    hi_idx = int(len(valores) * (1 - alpha / 2)) - 1
    return valores[lo_idx], valores[hi_idx]


# ----------------------------------------------------------------------
# N efectiva (cesta multiactivo con posible correlacion)
# ----------------------------------------------------------------------

def n_efectiva(trades):
    """
    Si el tramo mezcla varios activos, aproxima cuanto se solapan en el tiempo
    (proxy de correlacion, sin necesitar series de precios) y descuenta la N
    efectiva con la formula clasica de tamano de muestra bajo equicorrelacion:
        N_eff = N / (1 + (N-1)*rho)
    Devuelve (n_eff, rho) -- rho es None si solo hay un activo (no aplica).
    """
    n = len(trades)
    activos = {t["activo"] for t in trades}
    if len(activos) <= 1 or n <= 1:
        return float(n), None

    def solapan(a, b):
        return a["fecha_entrada"] <= b["fecha_salida"] and b["fecha_entrada"] <= a["fecha_salida"]

    cross_total = 0
    cross_overlap = 0
    for i in range(n):
        for j in range(i + 1, n):
            if trades[i]["activo"] != trades[j]["activo"]:
                cross_total += 1
                if solapan(trades[i], trades[j]):
                    cross_overlap += 1
    rho = (cross_overlap / cross_total) if cross_total > 0 else 0.0
    n_eff = n / (1 + (n - 1) * rho)
    return n_eff, rho


# ----------------------------------------------------------------------
# Bootstrap por bloques
# ----------------------------------------------------------------------

def bootstrap_ci_media(pcts, conf=0.90, n_boot=10000, seed=42, block=None):
    """
    IC bootstrap de la rentabilidad media por operacion, por BLOQUES contiguos
    (no operacion a operacion) para no asumir que las operaciones son
    independientes entre si -- una racha o un regimen de mercado puede
    encadenar varias operaciones parecidas.
    None si n < PISO_ABSOLUTO.
    """
    n = len(pcts)
    if n < PISO_ABSOLUTO:
        return None
    if block is None:
        block = max(2, round(n ** 0.5))
    block = min(block, n)

    rng = random.Random(seed)
    medias = []
    n_bloques = math.ceil(n / block)
    for _ in range(n_boot):
        muestra = []
        for _ in range(n_bloques):
            inicio = rng.randrange(n)
            for k in range(block):
                muestra.append(pcts[(inicio + k) % n])  # circular, mantiene el bloque completo
        muestra = muestra[:n]
        medias.append(mean(muestra))
    medias.sort()
    alpha = 1 - conf
    lo_idx = int(n_boot * (alpha / 2))
    hi_idx = int(n_boot * (1 - alpha / 2)) - 1
    return medias[lo_idx], medias[hi_idx]


# ----------------------------------------------------------------------
# Deflated Sharpe Ratio / PSR
# ----------------------------------------------------------------------

def _norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _norm_ppf(p):
    """Inversa de la normal estandar (aproximacion racional de Acklam)."""
    if p <= 0:
        return -8.0
    if p >= 1:
        return 8.0
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow = 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > 1 - plow:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def deflated_sharpe(pcts, n_variantes=1, t_efectiva=None):
    """
    Deflated Sharpe Ratio (Bailey & Lopez de Prado, 2014).

    t_efectiva: si se pasa (N efectiva tras el ajuste por correlacion en cesta
    multiactivo), se usa en vez de len(pcts) para la escala de la significancia
    -- la media/desviacion se calculan siempre con los datos reales, pero
    "cuanta evidencia independiente" hay se juzga con la N efectiva.
    """
    T_real = len(pcts)
    if T_real < PISO_ABSOLUTO:
        return None
    T = t_efectiva if t_efectiva is not None else T_real
    if T < 2:
        return None

    mu = mean(pcts)
    sd = pstdev(pcts)
    if sd == 0:
        return None
    sr_hat = mu / sd

    m3 = sum((p - mu) ** 3 for p in pcts) / T_real
    m4 = sum((p - mu) ** 4 for p in pcts) / T_real
    skew = m3 / (sd ** 3)
    kurt = m4 / (sd ** 4)  # curtosis normal (no excess); Gauss = 3

    def psr(sr_star):
        denom = math.sqrt(max(1e-12, 1 - skew*sr_hat + ((kurt-1)/4)*sr_hat**2))
        z = (sr_hat - sr_star) * math.sqrt(T - 1) / denom
        return _norm_cdf(z)

    if n_variantes <= 1:
        sr_star = 0.0
    else:
        var_sr_hat = max(0.0, 1 - skew*sr_hat + ((kurt-1)/4)*sr_hat**2) / (T - 1)
        sr_star = math.sqrt(var_sr_hat) * (
            (1 - EULER_MASCHERONI) * _norm_ppf(1 - 1/n_variantes)
            + EULER_MASCHERONI * _norm_ppf(1 - 1/(n_variantes*math.e))
        )

    return dict(sr_hat=sr_hat, skew=skew, kurt=kurt, sr_star=sr_star, dsr=psr(sr_star))


# ----------------------------------------------------------------------
# Veredictos
# ----------------------------------------------------------------------

def signo_tramo(ci, n_eff):
    if ci is None or n_eff < PISO_FIABLE:
        return "sin evidencia suficiente"
    lo, hi = ci
    if lo > 0:
        return "positivo"
    if hi < 0:
        return "negativo"
    return "no concluyente"


def veredicto_tramo_texto(ci, n, n_eff, rho):
    if ci is None:
        return "MUESTRA INSUFICIENTE (menos de 5 operaciones: ni bootstrap tiene sentido aqui)"
    lo, hi = ci
    avisos = []
    if n_eff < PISO_FIABLE:
        detalle = f"n={n}" if rho is None else f"n={n}, N efectiva={n_eff:.1f} tras ajustar por correlacion entre activos"
        avisos.append(f"[AVISO: con {detalle}, por debajo de {PISO_FIABLE}, este resultado NO decide el veredicto por si solo]")
    if rho is not None and rho > 0.05:
        avisos.append(f"[activos correlacionados: solapamiento temporal usado como proxy de correlacion, rho~{rho:.2f}]")
    aviso = ("  " + " ".join(avisos)) if avisos else ""
    if lo > 0:
        return f"ventaja aparente (intervalo [{lo:.2f}%, {hi:.2f}%], todo por encima de 0){aviso}"
    if hi < 0:
        return f"desventaja aparente (intervalo [{lo:.2f}%, {hi:.2f}%], todo por debajo de 0){aviso}"
    return f"no concluyente (intervalo [{lo:.2f}%, {hi:.2f}%], cruza el 0){aviso}"


def evaluar_split(filas, fraccion_is, conf, n_boot, n_variantes):
    """Ejecuta el pipeline completo (embargo + N efectiva + bootstrap + DSR) para
    un ratio de corte concreto. Devuelve el signo del tramo out-of-sample."""
    is_trades, oos_trades, _ = particionar_con_embargo(filas, fraccion_is)
    if not oos_trades:
        return "sin evidencia suficiente"
    n_eff_oos, _ = n_efectiva(oos_trades)
    pcts_oos = [float(t["resultado_%"]) for t in oos_trades]
    ci = bootstrap_ci_media(pcts_oos, conf=conf, n_boot=n_boot)
    s = signo_tramo(ci, n_eff_oos)
    if s != "positivo":
        return s
    dsr = deflated_sharpe(pcts_oos, n_variantes=n_variantes, t_efectiva=n_eff_oos)
    if dsr is not None and dsr["dsr"] < conf:
        return "no concluyente"  # el DSR desmonta lo que decia el bootstrap
    return s


# ----------------------------------------------------------------------
# CPCV -- Combinatorial Purged Cross-Validation (robustez del corte, version
# completa; evolucion de evaluar_split/RATIOS_ROBUSTEZ)
# ----------------------------------------------------------------------
#
# RATIOS_ROBUSTEZ (arriba) solo repite el veredicto en 3 cortes fijos, y los
# tres son "cola out-of-sample al final" -- nunca prueba que el tramo bueno o
# malo caiga en medio del historico. CPCV (Lopez de Prado, cap. 12 de
# "Advances in Financial Machine Learning") generaliza eso: parte el
# historico en S bloques, prueba TODAS las formas de elegir un subconjunto de
# bloques como "out-of-sample" (no solo el ultimo tramo), purga las
# operaciones que se solapan en cada frontera train/test (no solo en una),
# y calcula el signo del tramo out-of-sample en cada una de esas particiones
# con el mismo bootstrap por bloques ya validado -- en vez de 2 chequeos
# adicionales, se obtienen decenas o cientos.

def dividir_bloques_operaciones(n, s):
    """Parte n operaciones (ya ordenadas cronologicamente) en s bloques
    contiguos lo mas iguales posible. Igual que dividir_bloques en pbo.py,
    pero sobre el numero de OPERACIONES, no de periodos -- se duplica aqui
    a proposito para que este script siga sin depender de pbo.py."""
    base = n // s
    resto = n % s
    bloques = []
    inicio = 0
    for i in range(s):
        tam = base + (1 if i < resto else 0)
        bloques.append(list(range(inicio, inicio + tam)))
        inicio += tam
    return bloques


def purgar_en_transiciones(filas, bloques, test_ids):
    """
    Asigna cada operacion a train/test segun los bloques elegidos como test,
    y purga (descarta de los dos lados) cualquier operacion cuyo rango de
    fechas se solape con la operacion inmediatamente vecina cuando esa vecina
    tiene la etiqueta contraria -- purga en CADA frontera train/test de la
    combinacion, no solo en la unica frontera del split 70/30 original.
    """
    n = len(filas)
    label = [None] * n
    for b, idxs in enumerate(bloques):
        etiqueta = "test" if b in test_ids else "train"
        for i in idxs:
            label[i] = etiqueta

    def se_solapan(a, b):
        return a["fecha_entrada"] <= b["fecha_salida"] and b["fecha_entrada"] <= a["fecha_salida"]

    purgadas = set()
    for i in range(n):
        for j in (i - 1, i + 1):
            if 0 <= j < n and label[j] != label[i] and se_solapan(filas[i], filas[j]):
                purgadas.add(i)

    train = [filas[i] for i in range(n) if label[i] == "train" and i not in purgadas]
    test = [filas[i] for i in range(n) if label[i] == "test" and i not in purgadas]
    return train, test, purgadas


def robustez_cpcv(filas, s=8, fraccion_test=0.30, conf=0.90, n_boot=2000):
    """
    Ejecuta CPCV sobre las operaciones: parte en s bloques, prueba todas las
    combinaciones de k = round(fraccion_test * s) bloques como out-of-sample
    (purgando cada frontera), y calcula el signo del tramo test en cada una
    con el mismo bootstrap por bloques del resto del motor.

    Devuelve un dict con el recuento de signos, el porcentaje que coincide
    con `signo_principal`, y diagnosticos (bloques demasiado pequenos, etc.).
    """
    n = len(filas)
    k = max(1, round(fraccion_test * s))
    if k >= s:
        k = s - 1
    bloques = dividir_bloques_operaciones(n, s)
    tam_min_bloque = min(len(b) for b in bloques)

    combos = list(combinations(range(s), k))
    signos = []
    purgas_totales = 0
    for test_ids in combos:
        train, test, purgadas = purgar_en_transiciones(filas, bloques, set(test_ids))
        purgas_totales += len(purgadas)
        if len(test) < PISO_ABSOLUTO:
            signos.append("sin evidencia suficiente")
            continue
        pcts = [float(t["resultado_%"]) for t in test]
        n_eff, _ = n_efectiva(test)
        ci = bootstrap_ci_media(pcts, conf=conf, n_boot=n_boot)
        signos.append(signo_tramo(ci, n_eff))

    total = len(signos)
    recuento = {et: signos.count(et) for et in
                ("positivo", "negativo", "no concluyente", "sin evidencia suficiente")}
    return dict(
        s=s, k=k, n_combinaciones=total, tam_min_bloque=tam_min_bloque,
        recuento=recuento, signos=signos,
        purgas_promedio=purgas_totales / total if total else 0,
    )


PBO_UMBRAL_GATE = 0.50    # por encima o igual: elegir esta configuracion fue peor que el azar (gate automatico)
PBO_UMBRAL_AVISO = 0.20   # por encima: se avisa en el informe aunque no baje el veredicto por si solo
CPCV_UMBRAL_ACUERDO = 0.90   # decision de politica (2026-09-14): mismo 90% que el resto del criterio,
                              # por consistencia -- % minimo de particiones CPCV que deben coincidir con
                              # el signo principal para que el veredicto se considere robusto


def _pct_acuerdo_cpcv(cpcv, signo_principal):
    """% de particiones CPCV cuyo signo coincide con el del corte principal."""
    if cpcv is None or cpcv.get("n_combinaciones", 0) == 0:
        return None
    return cpcv["recuento"].get(signo_principal, 0) / cpcv["n_combinaciones"]


def veredicto_final(ci_is, n_eff_is, ci_oos, n_eff_oos, dsr_oos, conf, n_variantes,
                     robustez_signos, cesta_multiactivo, cesta_confirmada_pit, pbo=None, cpcv=None):
    s_oos = signo_tramo(ci_oos, n_eff_oos)
    s_is = signo_tramo(ci_is, n_eff_is)

    if s_oos == "sin evidencia suficiente":
        motivo = (f"el tramo out-of-sample tiene una N efectiva de {n_eff_oos:.1f}, por debajo del minimo "
                  f"fiable ({PISO_FIABLE}) -- aunque el numero de operaciones parezca bueno, no hay base "
                  f"estadistica para confiar en el (puede deberse a pocas operaciones, o a que varias de "
                  f"ellas estan correlacionadas entre si).")
        return "MUESTRA INSUFICIENTE", motivo
    if s_oos == "no concluyente":
        return "MUESTRA INSUFICIENTE", "el tramo out-of-sample no permite distinguir ventaja real de ruido."
    if s_oos == "negativo":
        if "positivo" in robustez_signos:
            motivo = ("el corte principal (70/30) muestra desventaja con confianza, pero el resultado no es "
                      "robusto: con otro punto de corte razonable (60/40 u 80/20) el signo cambia a favorable. "
                      "El veredicto depende de donde cae el corte, asi que no se puede dar un NO APTO firme.")
            return "MUESTRA INSUFICIENTE", motivo
        pct = _pct_acuerdo_cpcv(cpcv, "negativo")
        if pct is not None and pct < CPCV_UMBRAL_ACUERDO:
            motivo = (f"el corte principal y los cortes de robustez (60/40, 80/20) coinciden en desventaja, "
                      f"PERO el CPCV (particiones combinatorias purgadas) solo confirma esa desventaja en el "
                      f"{pct*100:.1f}% de las particiones probadas -- por debajo del {CPCV_UMBRAL_ACUERDO*100:.0f}% "
                      f"exigido. El resultado depende de que zona del historico se use como prueba, asi que no "
                      f"se puede dar un NO APTO firme.")
            return "MUESTRA INSUFICIENTE", motivo
        return "NO APTO", "el tramo out-of-sample muestra desventaja con confianza estadistica real, y se mantiene en distintos puntos de corte (60/40, 70/30, 80/20)."

    # s_oos == "positivo"
    if s_is == "negativo":
        return "MUESTRA INSUFICIENTE", "el in-sample y el out-of-sample no cuentan la misma historia."

    if dsr_oos is not None and dsr_oos["dsr"] < conf:
        extra = f" tras descontar las {n_variantes} variantes de parametros probadas antes de esta," if n_variantes > 1 else ""
        motivo = (f"el bootstrap del tramo out-of-sample mostraba ventaja, pero el Deflated Sharpe Ratio"
                  f"{extra} solo da un {dsr_oos['dsr']*100:.1f}% de confianza en que sea ventaja real "
                  f"(por debajo del {conf*100:.0f}% exigido) -- probablemente sea suerte de haber buscado, no edge.")
        return "MUESTRA INSUFICIENTE", motivo

    if "negativo" in robustez_signos or "no concluyente" in robustez_signos:
        motivo = ("el corte principal (70/30) muestra ventaja con confianza (bootstrap y Deflated Sharpe Ratio "
                  "de acuerdo), pero el resultado no es robusto: con otro punto de corte razonable (60/40 u "
                  "80/20) deja de confirmarse. El veredicto depende de donde cae el corte, asi que no se puede "
                  "dar un APTO firme todavia.")
        return "MUESTRA INSUFICIENTE", motivo

    pct_cpcv = _pct_acuerdo_cpcv(cpcv, "positivo")
    if pct_cpcv is not None and pct_cpcv < CPCV_UMBRAL_ACUERDO:
        motivo = (f"el corte principal y los cortes de robustez (60/40, 80/20) coinciden en ventaja, PERO el "
                  f"CPCV (particiones combinatorias purgadas, no solo cola final) solo confirma esa ventaja en "
                  f"el {pct_cpcv*100:.1f}% de las particiones probadas -- por debajo del "
                  f"{CPCV_UMBRAL_ACUERDO*100:.0f}% exigido. El resultado depende de que zona del historico se "
                  f"use como prueba, asi que no se puede dar un APTO firme todavia.")
        return "MUESTRA INSUFICIENTE", motivo

    if cesta_multiactivo and not cesta_confirmada_pit:
        motivo = ("el tramo out-of-sample muestra ventaja con confianza estadistica real y es robusto al punto "
                  "de corte, PERO la cesta incluye varios activos y no se ha confirmado que sea point-in-time "
                  "(los mismos activos que existian en cada momento historico, no solo los que sobreviven hoy). "
                  "Sin esa confirmacion no se puede descartar sesgo de supervivencia, asi que no se puede dar "
                  "un APTO todavia -- confirmar la composicion historica de la cesta con el cliente y "
                  "volver a pasar el motor con --cesta-point-in-time.")
        return "MUESTRA INSUFICIENTE", motivo

    if pbo is not None and pbo >= PBO_UMBRAL_GATE:
        motivo = (f"el tramo out-of-sample muestra ventaja con confianza estadistica real y es robusto al punto "
                  f"de corte, PERO el Probability of Backtest Overfitting (PBO) de la rejilla de variantes es "
                  f"{pbo*100:.1f}% -- por encima del {PBO_UMBRAL_GATE*100:.0f}%, lo que significa que elegir esta "
                  f"configuracion como la mejor fue, en las particiones combinatorias probadas, peor o igual que "
                  f"elegir al azar entre las variantes. No hay base para dar un APTO.")
        return "MUESTRA INSUFICIENTE", motivo

    motivo = ("el tramo out-of-sample muestra ventaja con confianza estadistica real, de acuerdo con el "
              "bootstrap por bloques y el Deflated Sharpe Ratio, y es robusto al punto de corte elegido.")
    if pbo is not None and pbo >= PBO_UMBRAL_AVISO:
        motivo += (f" [AVISO: el Probability of Backtest Overfitting es {pbo*100:.1f}% -- por debajo del "
                   f"{PBO_UMBRAL_GATE*100:.0f}% que forzaria MUESTRA INSUFICIENTE, pero lo bastante alto como "
                   f"para mencionarlo: una parte no desdeñable de por que esta configuracion parecio la mejor "
                   f"puede deberse a haber probado varias variantes, no solo a ventaja real.]")
    return "APTO", motivo


# ----------------------------------------------------------------------
# main
# ----------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("--conf", type=float, default=0.90)
    ap.add_argument("--boot", type=int, default=10000)
    ap.add_argument("--variantes", type=int, default=1,
                     help="numero de configuraciones de parametros que el cliente probo antes de "
                          "quedarse con esta (default 1 = no se descuenta nada)")
    ap.add_argument("--cesta-point-in-time", action="store_true", dest="cesta_pit",
                     help="confirma que, si hay varios activos, la cesta refleja los activos que existian "
                          "en cada momento historico (no solo los que sobreviven hoy)")
    ap.add_argument("--pbo", type=float, default=None,
                     help="Probability of Backtest Overfitting (0-1) calculado por separado con pbo.py sobre "
                          "la rejilla real de variantes (solo aplica cuando el cliente aporto reglas, input B). "
                          f"PBO >= {PBO_UMBRAL_GATE:.0%} fuerza MUESTRA INSUFICIENTE; entre {PBO_UMBRAL_AVISO:.0%} "
                          f"y {PBO_UMBRAL_GATE:.0%} se avisa en el informe sin decidir el veredicto por si solo.")
    ap.add_argument("--cpcv", action="store_true",
                     help="ademas de los 2 cortes fijos de robustez (60/40, 80/20), ejecuta Combinatorial "
                          "Purged Cross-Validation: prueba decenas/cientos de particiones in/out-of-sample "
                          "combinatorias (no solo colas finales) con purga en cada frontera. Mas lento; "
                          "todavia informativo, no decide el veredicto por si solo (ver criterios-operativos.md).")
    ap.add_argument("--cpcv-bloques", type=int, default=8, dest="cpcv_s",
                     help="numero de bloques S para el CPCV (default 8 -> C(8,2)=28 particiones con "
                          "fraccion_test=0.30 por defecto)")
    args = ap.parse_args()

    filas = leer_operaciones(args.csv_path)
    activos_totales = {t["activo"] for t in filas}
    cesta_multiactivo = len(activos_totales) > 1

    is_trades, oos_trades, embargadas = particionar_con_embargo(filas, 0.70)

    print(f"Operaciones totales: {len(filas)}  (in-sample: {len(is_trades)}, out-of-sample: {len(oos_trades)}, "
          f"embargadas en la frontera: {len(embargadas)})")
    print(f"Nivel de confianza: {args.conf*100:.0f}%  |  remuestreos: {args.boot}  |  variantes probadas: {args.variantes}")
    if cesta_multiactivo:
        pit = "SI confirmada" if args.cesta_pit else "NO confirmada (ver aviso mas abajo)"
        print(f"Cesta multiactivo: {len(activos_totales)} activos  |  point-in-time: {pit}")
    if args.pbo is not None:
        print(f"PBO (Probability of Backtest Overfitting, de la rejilla de variantes): {args.pbo*100:.1f}%")
    print()

    resultados = {}
    dsr_oos = None
    for etiqueta, trades in [("IN-SAMPLE", is_trades), ("OUT-OF-SAMPLE", oos_trades)]:
        m = metricas_clasicas(trades)
        pcts = [float(t["resultado_%"]) for t in trades]
        n_eff, rho = n_efectiva(trades)
        ci = bootstrap_ci_media(pcts, conf=args.conf, n_boot=args.boot)
        resultados[etiqueta] = (ci, n_eff)
        print(f"--- {etiqueta} ---")
        if m:
            print(f"  n={m['n']}  rentabilidad neta={m['rent_neta']:.2f}%  PF={m['pf']:.2f}  "
                  f"win rate={m['win_rate']:.1f}%  MDD={m['mdd']:.2f}%")
            equity = curva_equity(pcts)
            ulcer = ulcer_index(equity)
            calmar = calmar_ratio(trades, m["rent_neta"], m["mdd"])
            vc = var_cvar(pcts, conf=args.conf)
            calmar_txt = f"{calmar:.2f}" if calmar is not None else "n/d (tramo <30 dias o MDD=0)"
            print(f"  Ulcer Index={ulcer:.2f}  Calmar={calmar_txt}  "
                  f"VaR{(1-args.conf)*100:.0f}%={vc['var']:.2f}%  CVaR{(1-args.conf)*100:.0f}%={vc['cvar']:.2f}% "
                  f"(peor {vc['n_cola']} de {m['n']} operaciones)")
            kelly = kelly_fraccion(pcts)
            kelly_ci = kelly_bootstrap_ci(pcts, conf=args.conf, n_boot=args.boot)
            if kelly is None:
                print("  Kelly: n/d (hace falta al menos una operacion ganadora y una perdedora)")
            else:
                kelly_ci_txt = (f"[{kelly_ci[0]*100:.1f}%, {kelly_ci[1]*100:.1f}%], usar el limite inferior "
                                 f"={kelly_ci[0]*100:.1f}%" if kelly_ci is not None
                                 else "n/d (remuestreos insuficientes con ganadoras y perdedoras a la vez)")
                print(f"  Kelly (teorico, punto estimado)={kelly*100:.1f}%  |  "
                      f"Kelly ajustado por incertidumbre (IC {args.conf*100:.0f}%): {kelly_ci_txt}")
                if kelly < 0:
                    print("    [la fraccion teorica es negativa: con estos datos no hay edge que justifique "
                          "arriesgar capital en esta operativa, ni siquiera con dimensionamiento pequeno]")
        print(f"  {veredicto_tramo_texto(ci, len(trades), n_eff, rho)}")
        if etiqueta == "OUT-OF-SAMPLE":
            dsr_oos = deflated_sharpe(pcts, n_variantes=args.variantes, t_efectiva=n_eff)
            if dsr_oos:
                etiqueta_dsr = "PSR" if args.variantes <= 1 else "Deflated Sharpe Ratio (DSR)"
                print(f"  {etiqueta_dsr}: SR={dsr_oos['sr_hat']:.3f}  SR*(umbral por suerte)={dsr_oos['sr_star']:.3f}  "
                      f"-> {dsr_oos['dsr']*100:.1f}% de confianza en que la ventaja sea real")
        print()

    if embargadas:
        print(f"({len(embargadas)} operacion(es) descartadas por solapar la frontera in/out-of-sample -- "
              f"ni cuentan a favor ni en contra, evitan fuga de informacion entre tramos.)\n")

    # Robustez: repetir el signo del tramo OOS en otros puntos de corte razonables
    robustez_signos = []
    for frac in RATIOS_ROBUSTEZ:
        if abs(frac - 0.70) < 1e-9:
            continue  # el 70/30 ya es el resultado principal
        s = evaluar_split(filas, frac, args.conf, max(2000, args.boot // 5), args.variantes)
        robustez_signos.append(s)
        print(f"Robustez -- corte {round(frac*100)}/{round((1-frac)*100)}: {s}")
    print()

    cpcv = None
    if args.cpcv:
        cpcv = robustez_cpcv(filas, s=args.cpcv_s, conf=args.conf, n_boot=max(1000, args.boot // 10))
        r = cpcv["recuento"]
        print(f"CPCV -- {cpcv['n_combinaciones']} particiones combinatorias "
              f"(S={cpcv['s']} bloques, {cpcv['k']} de test cada vez, purga media "
              f"{cpcv['purgas_promedio']:.1f} operaciones por particion):")
        for etiqueta in ("positivo", "negativo", "no concluyente", "sin evidencia suficiente"):
            pct = (r[etiqueta] / cpcv["n_combinaciones"] * 100) if cpcv["n_combinaciones"] else 0
            print(f"  {etiqueta}: {r[etiqueta]} ({pct:.1f}%)")
        if cpcv["tam_min_bloque"] < PISO_ABSOLUTO:
            print(f"  [AVISO: el bloque mas pequeno tiene {cpcv['tam_min_bloque']} operaciones -- por debajo de "
                  f"{PISO_ABSOLUTO}, considera bajar --cpcv-bloques o hay pocas operaciones para este chequeo]")
        print(f"  (gate: exige >= {CPCV_UMBRAL_ACUERDO*100:.0f}% de acuerdo con el signo principal para "
              f"mantener APTO/NO APTO -- ver criterios-operativos.md seccion 2.6)")
        print()

    (ci_is, n_eff_is), (ci_oos, n_eff_oos) = resultados["IN-SAMPLE"], resultados["OUT-OF-SAMPLE"]
    veredicto, motivo = veredicto_final(
        ci_is, n_eff_is, ci_oos, n_eff_oos, dsr_oos, args.conf, args.variantes,
        robustez_signos, cesta_multiactivo, args.cesta_pit, pbo=args.pbo, cpcv=cpcv,
    )
    print(f"VEREDICTO FINAL: {veredicto}")
    print(f"Motivo: {motivo}")


if __name__ == "__main__":
    main()
