/*
 * Panel de transparencia del cuaderno-bot. Sin dependencias externas.
 *
 * Todo lo que se muestra se recalcula aquí, en el navegador, a partir de
 * registro.jsonl (la única fuente de verdad), igual que en modulo_9_salidas.py.
 *
 * Verificación de la cadena (igual que modulo_7_registro.py): cada línea es
 *   <contenido sin el último "}">,"hash":"<64 hex>"}
 * El contenido es el texto EXACTO de la línea sin el sufijo; nunca se vuelve
 * a serializar, para que no importe cómo escribe cada lenguaje los números.
 */
"use strict";

const CAPITAL = 10000;
const DIAS = 90;
const GENESIS = "0".repeat(64);
const SUFIJO = /^(.*),"hash":"([0-9a-f]{64})"}$/;
const CARTERAS = [
  { id: "V8", nombre: "V8 (estrategia)", corto: "V8", color: "var(--v8)" },
  { id: "FIJO30", nombre: "30 % fijo", corto: "30 % fijo", color: "var(--fijo30)" },
  { id: "BH100", nombre: "Comprar y mantener", corto: "Comprar y mantener", color: "var(--bh100)" },
];
const ETIQUETA = { debil: "débil" };

// ------------------------------------------------------------- formato
const nf0 = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 0, minimumFractionDigits: 0, useGrouping: "always" });
const nf2 = new Intl.NumberFormat("es-ES", { maximumFractionDigits: 2, minimumFractionDigits: 2, useGrouping: "always" });
const eur = (x, dec = 0) => `${(dec ? nf2 : nf0).format(x)} €`;
const eurSigno = (x, dec = 0) => `${x > 0 ? "+" : ""}${eur(x, dec)}`;
const pct = (x, dec = 1, signo = false) => `${signo && x > 0 ? "+" : ""}${(x * 100).toFixed(dec).replace(".", ",")} %`;
const num = (x, dec = 6) => x.toFixed(dec).replace(".", ",");
const fechaCorta = (iso) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
const fechaLarga = (iso) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
const el = (id) => document.getElementById(id);
function crear(etiqueta, atributos = {}, hijos = []) {
  const n = document.createElement(etiqueta);
  for (const [k, v] of Object.entries(atributos)) {
    if (k === "texto") n.textContent = v; else if (k === "clase") n.className = v; else n.setAttribute(k, v);
  }
  for (const h of hijos) n.append(h);
  return n;
}

// ---------------------------------------------------------- criptografía
async function sha256(datos) {
  const bytes = typeof datos === "string" ? new TextEncoder().encode(datos) : datos;
  const resumen = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(resumen)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function verificarCadena(texto) {
  let anterior = GENESIS;
  let n = 0;
  const lineas = texto.split("\n");
  for (let i = 0; i < lineas.length; i++) {
    const linea = lineas[i];
    if (linea === "") continue;
    n += 1;
    const m = SUFIJO.exec(linea);
    if (!m) return { valido: false, lineas: n, linea: i + 1, error: "formato de línea inválido", ultimo: anterior };
    const contenido = m[1] + "}";
    if ((await sha256(contenido)) !== m[2]) {
      return { valido: false, lineas: n, linea: i + 1, error: "el hash no corresponde al contenido", ultimo: anterior };
    }
    const evento = JSON.parse(contenido);
    if (evento.hash_anterior !== anterior) {
      return { valido: false, lineas: n, linea: i + 1, error: "la línea no encadena con la anterior", ultimo: anterior };
    }
    if (evento.n !== n) {
      return { valido: false, lineas: n, linea: i + 1, error: "numeración rota (línea borrada o insertada)", ultimo: anterior };
    }
    anterior = m[2];
  }
  return { valido: true, lineas: n, ultimo: anterior };
}

function leerEventos(texto) {
  return texto.split("\n").filter(Boolean).map((linea) => {
    const m = SUFIJO.exec(linea);
    const e = JSON.parse(m[1] + "}");
    e.hash = m[2];
    return e;
  });
}

// --------------------------------------------------------------- cálculo
// Fe de erratas 1 (2026-10-05, ver CAMBIOS.md): cada día se valora la cartera JUSTO DESPUÉS de
// ejecutar las órdenes de la decisión, al precio de apertura al que se ejecutaron (igual que
// construir_estado en modulo_9_salidas.py). Así capital, comisiones, posiciones y exposición
// describen el mismo instante.
function masUnDia(iso) {
  const d = new Date(iso);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().replace(".000Z", "Z");
}

function calcular(eventos, costes) {
  const porTipo = {};
  for (const e of eventos) (porTipo[e.tipo] ||= []).push(e.datos);
  const inicio = (porTipo.inicio || [])[0];
  if (!inicio) return null;
  const pares = Object.keys(inicio.archivo_inicial);
  const decisiones = (porTipo.decision || []).filter((d) => d.cartera === "V8");
  const fechasDecision = [...new Set(decisiones.map((d) => d.fecha))].sort();
  const ejecuciones = porTipo.ejecucion || [];

  // Precio de apertura en el que se ejecutó cada decisión (está en `ejecucion` y en `sin_orden`).
  const aperturas = {};
  for (const e of [...ejecuciones, ...(porTipo.sin_orden || [])]) {
    (aperturas[e.fecha_decision] ||= {})[e.par] = e.apertura ?? e.precio_referencia;
  }
  const completas = fechasDecision.filter((f) => pares.every((p) => aperturas[f] && aperturas[f][p] !== undefined));

  const fechaBase = masUnDia(pares.map((p) => inicio.archivo_inicial[p].ultima_vela).sort().at(-1));
  const fechas = [fechaBase];
  const serie = { V8: [CAPITAL], FIJO30: [CAPITAL], BH100: [CAPITAL] };
  const tenencias = {};
  for (const c of ["V8", "FIJO30"]) for (const p of pares) tenencias[`${c}|${p}`] = [CAPITAL / pares.length, 0];
  const unidadesBH = completas.length
    ? Object.fromEntries(pares.map((p) => [p, CAPITAL / pares.length / (aperturas[completas[0]][p] * (1 + costes.slippage) * (1 + costes.comision))]))
    : null;
  for (const f of completas) {
    for (const e of ejecuciones) if (e.fecha_decision === f) tenencias[`${e.cartera}|${e.par}`] = [e.efectivo_despues, e.unidades_despues];
    const a = aperturas[f];
    fechas.push(masUnDia(f));
    for (const c of ["V8", "FIJO30"]) serie[c].push(pares.reduce((s, p) => s + tenencias[`${c}|${p}`][0] + tenencias[`${c}|${p}`][1] * a[p], 0));
    serie.BH100.push(pares.reduce((s, p) => s + unidadesBH[p] * a[p], 0));
  }

  const resumen = {};
  for (const c of ["V8", "FIJO30", "BH100"]) {
    const s = serie[c];
    let pico = CAPITAL, maxima = 0;
    const caidas = s.map((v) => { pico = Math.max(pico, v); const d = 1 - v / pico; maxima = Math.max(maxima, d); return d; });
    const ultimo = s.at(-1), previo = s.length > 1 ? s.at(-2) : CAPITAL;
    resumen[c] = {
      equity: ultimo, hoy: ultimo - previo, hoyPct: ultimo / previo - 1, acumulado: ultimo / CAPITAL - 1,
      caidaActual: caidas.at(-1), caidaMaxima: maxima, caidas,
    };
  }
  const ultima = completas.at(-1);
  for (const c of ["V8", "FIJO30"]) {
    const invertido = ultima ? pares.reduce((s, p) => s + tenencias[`${c}|${p}`][1] * aperturas[ultima][p], 0) : 0;
    resumen[c].exposicion = invertido / resumen[c].equity;
    const ops = ejecuciones.filter((o) => o.cartera === c && ultima && o.fecha_decision <= ultima);
    resumen[c].ordenes = ops.length;
    resumen[c].comisiones = ops.reduce((s, o) => s + o.comision, 0);
    resumen[c].slippage = ops.reduce((s, o) => s + o.slippage, 0);
  }
  resumen.BH100.exposicion = ultima ? 1 : 0;

  return {
    pares, fechas, serie, resumen, fechasDecision,
    dia: ultima ? fechasDecision.indexOf(ultima) + 1 : 0,
    ultimaDecision: ultima,
    decisiones: (porTipo.decision || []),
    ejecuciones,
    velasPerdidas: porTipo.vela_perdida || [],
    alertas: porTipo.alerta || [],
    paradas: porTipo.parada || [],
    fin: (porTipo.fin_experimento || [])[0],
    ultimoTs: eventos.at(-1).ts_utc,
  };
}

// ------------------------------------------------------------ renderizado
function tarjetas(c) {
  const cont = el("tarjetas");
  cont.replaceChildren();
  for (const cart of CARTERAS) {
    const r = c.resumen[cart.id];
    const clase = (x) => (x > 0 ? "sube" : x < 0 ? "baja" : "");
    const dl = crear("dl");
    const filas = [
      ["Hoy", `${eurSigno(r.hoy)} (${pct(r.hoyPct, 2, true)})`, clase(r.hoy)],
      ["Desde el inicio", pct(r.acumulado, 2, true), clase(r.acumulado)],
      ["Caída actual", pct(r.caidaActual), ""],
      ["Caída máxima", pct(r.caidaMaxima), ""],
      ["Invertido", pct(r.exposicion, 0), ""],
    ];
    if (cart.id !== "BH100") filas.push(["Comisiones", eur(r.comisiones, 2), ""]);
    for (const [k, v, cl] of filas) dl.append(crear("dt", { texto: k }), crear("dd", { texto: v, clase: cl }));
    const t = crear("article", { clase: "tarjeta", style: `--color:${cart.color}` },
      [crear("p", { clase: "nombre", texto: cart.nombre }), crear("p", { clase: "valor", texto: eur(r.equity) }), dl]);
    cont.append(t);
  }
  el("dia").textContent = `Día ${c.dia}`;
  const fin = c.fin ? " · experimento terminado" : "";
  el("actualizado").textContent = `${c.ultimaDecision ? `Valores tras la apertura del ${fechaLarga(c.fechas.at(-1))} (decisión del cierre del ${fechaLarga(c.ultimaDecision)})` : "Aún sin decisiones"} · último evento ${c.ultimoTs.replace("T", " ").replace("Z", " UTC")}${fin}`;
}

function avisos(c) {
  const cont = el("avisos");
  cont.replaceChildren();
  for (const p of c.paradas) {
    cont.append(crear("div", { clase: "aviso critico", texto: `Experimento DETENIDO el ${fechaLarga(p.fecha)} por la regla de parada pre-registrada (caída de ${pct(p.drawdown)}).` }));
  }
  if (c.velasPerdidas.length) {
    const lista = c.velasPerdidas.map((v) => `${v.par.split("/")[0]} ${fechaLarga(v.fecha)}`).join(", ");
    cont.append(crear("div", { clase: "aviso", texto: `Velas perdidas (el bot no se ejecutó y no se operó a posteriori): ${c.velasPerdidas.length} · ${lista}` }));
  }
  const recientes = c.alertas.slice(-5);
  for (const a of recientes) {
    const que = a.regla === "perdida_diaria" ? `pérdida diaria de ${pct(a.variacion)} en ${a.cartera}`
      : a.regla === "perdida_semanal" ? `pérdida semanal de ${pct(a.variacion)} en ${a.cartera}`
      : a.motivo || a.regla;
    cont.append(crear("div", { clase: "aviso", texto: `Aviso (${a.fecha ? fechaLarga(a.fecha) : ""}): ${que}.` }));
  }
}

const SVG = "http://www.w3.org/2000/svg";
function nodo(etiqueta, atributos = {}) {
  const n = document.createElementNS(SVG, etiqueta);
  for (const [k, v] of Object.entries(atributos)) n.setAttribute(k, v);
  return n;
}
function ticksLimpios(min, max, n = 5) {
  const paso0 = (max - min) / n || 1;
  const mag = 10 ** Math.floor(Math.log10(paso0));
  const paso = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((p) => p >= paso0);
  const salida = [];
  for (let v = Math.ceil(min / paso) * paso; v <= max + 1e-9; v += paso) salida.push(+v.toFixed(6));
  return salida;
}

const graficos = [];
function graficoLineas(contenedor, c, series, opciones) {
  const ancho = contenedor.clientWidth || 600, alto = contenedor.clientHeight || 300;
  // Mismo margen derecho en todos los gráficos para que un día caiga en la misma vertical en los dos.
  const margen = { izq: opciones.margenIzq, der: ancho < 520 ? 12 : 150, arr: 10, aba: 26 };
  const w = ancho - margen.izq - margen.der, h = alto - margen.arr - margen.aba;
  const n = c.fechas.length;
  const valores = series.flatMap((s) => s.valores);
  let min = Math.min(...valores, opciones.minimo ?? Infinity), max = Math.max(...valores, opciones.maximo ?? -Infinity);
  if (max - min < opciones.rangoMinimo) { const m = (max + min) / 2; min = m - opciones.rangoMinimo / 2; max = m + opciones.rangoMinimo / 2; }
  const ticks = ticksLimpios(min, max, opciones.nTicks || 5);
  min = Math.min(min, ticks[0]); max = Math.max(max, ticks.at(-1));
  const x = (i) => margen.izq + (n === 1 ? w / 2 : (i / (n - 1)) * w);
  const y = (v) => margen.arr + (1 - (v - min) / (max - min)) * h;

  const svg = nodo("svg", { viewBox: `0 0 ${ancho} ${alto}`, "aria-hidden": "true" });
  const rej = nodo("g", { class: "rejilla" }), eje = nodo("g", { class: "eje" });
  for (const t of ticks) {
    rej.append(nodo("line", { x1: margen.izq, x2: margen.izq + w, y1: y(t), y2: y(t) }));
    const txt = nodo("text", { x: margen.izq - 8, y: y(t) + 4, "text-anchor": "end" });
    txt.textContent = opciones.formatoY(t);
    eje.append(txt);
  }
  const pasoX = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(w / 80))));
  for (let i = 0; i < n; i += pasoX) {
    const txt = nodo("text", { x: x(i), y: alto - 6, "text-anchor": "middle" });
    txt.textContent = fechaCorta(c.fechas[i]);
    eje.append(txt);
  }
  svg.append(rej, eje);
  if (opciones.lineaBase !== undefined) svg.append(nodo("line", { class: "base", x1: margen.izq, x2: margen.izq + w, y1: y(opciones.lineaBase), y2: y(opciones.lineaBase) }));
  for (const s of series) {
    const d = s.valores.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
    if (opciones.area) svg.append(nodo("path", { class: "area", d: `${d}L${x(n - 1)},${y(0)}L${x(0)},${y(0)}Z`, fill: s.color }));
    svg.append(nodo("path", { class: "linea", d, stroke: s.color, "stroke-width": s.ancho || 2 }));
    if (n < 4) s.valores.forEach((v, i) => svg.append(nodo("circle", { class: "punto", cx: x(i), cy: y(v), r: 4, fill: s.color })));
  }
  // Etiquetas al final de las líneas (texto en tinta, nunca en el color de la serie), separadas si chocan.
  if (opciones.etiquetas && margen.der > 12) {
    const fin = series.map((s) => ({ s, v: s.valores.at(-1) })).sort((a, b) => b.v - a.v);
    let previa = -Infinity;
    for (const { s, v } of fin) {
      const yy = Math.max(y(v), previa + 16);
      previa = yy;
      if (Math.abs(yy - y(v)) > 1) svg.append(nodo("line", { class: "base", x1: x(n - 1), y1: y(v), x2: x(n - 1) + 8, y2: yy }));
      const txt = nodo("text", { class: "etiqueta-final", x: x(n - 1) + 10, y: yy + 4 });
      txt.textContent = `${s.corto} ${opciones.formatoY(v)}`;
      svg.append(txt);
    }
  }
  const cursor = nodo("line", { class: "cursor", y1: margen.arr, y2: margen.arr + h, visibility: "hidden" });
  const puntos = series.map((s) => nodo("circle", { class: "punto", r: 4.5, fill: s.color, visibility: "hidden" }));
  svg.append(cursor, ...puntos);
  contenedor.replaceChildren(svg);
  graficos.push({ contenedor, x, y, n, series, cursor, puntos, margen, w, formato: opciones.formatoTooltip, c });
}

function mostrarCursor(i, evento) {
  const tt = el("tooltip");
  for (const g of graficos) {
    if (i === null) { g.cursor.setAttribute("visibility", "hidden"); g.puntos.forEach((p) => p.setAttribute("visibility", "hidden")); continue; }
    g.cursor.setAttribute("x1", g.x(i)); g.cursor.setAttribute("x2", g.x(i)); g.cursor.setAttribute("visibility", "visible");
    g.series.forEach((s, k) => {
      g.puntos[k].setAttribute("cx", g.x(i)); g.puntos[k].setAttribute("cy", g.y(s.valores[i])); g.puntos[k].setAttribute("visibility", "visible");
    });
  }
  if (i === null) { tt.hidden = true; return; }
  const c = graficos[0].c;
  tt.replaceChildren(crear("div", { clase: "fecha", texto: `Apertura del ${fechaLarga(c.fechas[i])}${i === 0 ? " (día 0)" : ""}` }));
  for (const cart of CARTERAS) {
    const v = c.serie[cart.id][i];
    const caida = c.resumen[cart.id].caidas[i];
    tt.append(crear("div", { clase: "fila" }, [
      crear("span", {}, [crear("i", { style: `--color:${cart.color}` }), ` ${cart.corto}`]),
      crear("span", { texto: `${eur(v)} · caída ${pct(caida)}` }),
    ]));
  }
  tt.hidden = false;
  const r = graficos[0].contenedor.getBoundingClientRect();
  const px = evento && "clientX" in evento ? evento.clientX : r.left + graficos[0].x(i);
  const py = evento && "clientY" in evento ? evento.clientY : r.top + 20;
  const izquierda = Math.min(window.innerWidth - tt.offsetWidth - 12, px + 14);
  tt.style.left = `${Math.max(12, izquierda)}px`;
  tt.style.top = `${Math.max(12, py - tt.offsetHeight - 14)}px`;
}

function interaccion() {
  let actual = null;
  for (const g of graficos) {
    const indice = (ev) => {
      const r = g.contenedor.getBoundingClientRect();
      const escala = (g.contenedor.clientWidth || 1) / r.width;
      const px = (ev.clientX - r.left) * escala - g.margen.izq;
      return Math.max(0, Math.min(g.n - 1, Math.round((px / g.w) * (g.n - 1))));
    };
    g.contenedor.onpointermove = (ev) => { actual = indice(ev); mostrarCursor(actual, ev); };
    g.contenedor.onpointerleave = () => { actual = null; mostrarCursor(null); };
  }
  const principal = el("grafico-capital");
  principal.onkeydown = (ev) => {
    const n = graficos[0].n;
    if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") {
      actual = actual === null ? n - 1 : Math.max(0, Math.min(n - 1, actual + (ev.key === "ArrowRight" ? 1 : -1)));
      mostrarCursor(actual); ev.preventDefault();
    } else if (ev.key === "Escape") { actual = null; mostrarCursor(null); }
  };
  principal.onblur = () => { actual = null; mostrarCursor(null); };
}

function dibujar(c) {
  graficos.length = 0;
  const leyenda = el("leyenda");
  leyenda.replaceChildren(...CARTERAS.map((k) => crear("span", {}, [crear("i", { style: `--color:${k.color}` }), k.nombre])));
  graficoLineas(el("grafico-capital"), c,
    CARTERAS.slice().reverse().map((k) => ({ valores: c.serie[k.id], color: k.color, corto: k.corto, ancho: k.id === "BH100" ? 1.5 : 2 })),
    { margenIzq: 72, formatoY: (v) => eur(v), rangoMinimo: 400, lineaBase: CAPITAL, etiquetas: true });
  graficoLineas(el("grafico-caida"), c,
    CARTERAS.filter((k) => k.id !== "BH100").map((k) => ({ valores: c.resumen[k.id].caidas.map((d) => -d * 100), color: k.color, corto: k.corto })),
    { margenIzq: 72, formatoY: (v) => `${nf0.format(v)} %`, rangoMinimo: 2, maximo: 0, area: true, nTicks: 3 });
  interaccion();
}

function tablaCapital(c) {
  const t = el("tabla-capital");
  const cab = crear("tr", {}, [crear("th", { texto: "Apertura" }), ...CARTERAS.flatMap((k) => [crear("th", { texto: k.corto }), crear("th", { texto: "Caída" })])]);
  const filas = c.fechas.map((f, i) => crear("tr", {}, [crear("td", { texto: fechaLarga(f) + (i === 0 ? " (día 0)" : "") }),
    ...CARTERAS.flatMap((k) => [crear("td", { texto: eur(c.serie[k.id][i], 2) }), crear("td", { texto: pct(c.resumen[k.id].caidas[i]) })])]));
  t.replaceChildren(crear("caption", { texto: "Valor de cada cartera tras ejecutar las órdenes del día, a precio de apertura (incluye comisiones y slippage)" }), crear("thead", {}, [cab]), crear("tbody", {}, filas.reverse()));
}

function decisiones(c) {
  const cont = el("decision-hoy");
  cont.replaceChildren();
  const hoy = c.decisiones.filter((d) => d.cartera === "V8" && d.fecha === c.ultimaDecision);
  if (!hoy.length) cont.append(crear("p", { clase: "vacio", texto: "Aún no hay decisiones: el primer cierre llega tras el día 0." }));
  for (const d of hoy) {
    const r = d.regimen;
    cont.append(crear("article", { clase: "decision" }, [
      crear("h3", { texto: `${d.par} · cierre del ${fechaLarga(d.fecha)}` }),
      crear("div", { clase: "chips" }, [`tendencia ${r.tendencia}`, `volatilidad ${r.volatilidad}`, `fuerza ${ETIQUETA[r.fuerza] || r.fuerza}`]
        .map((txt) => crear("span", { clase: "chip", texto: txt }))),
      crear("p", { texto: d.motivo }),
      crear("p", { clase: "objetivo", texto: d.exposicion_objetivo === null ? "Hoy no se decide (dato sospechoso): se mantiene la posición."
        : `Exposición objetivo: ${pct(d.exposicion_objetivo, 0)} del capital de este activo.` }),
    ]));
  }
  const t = el("tabla-decisiones");
  const filas = c.decisiones.filter((d) => d.cartera === "V8").slice().reverse().map((d) => crear("tr", {}, [
    crear("td", { texto: fechaLarga(d.fecha) }), crear("td", { clase: "texto", texto: d.par }),
    crear("td", { clase: "texto", texto: `${d.regimen.tendencia} / ${d.regimen.volatilidad} / ${ETIQUETA[d.regimen.fuerza] || d.regimen.fuerza}` }),
    crear("td", { texto: d.exposicion_objetivo === null ? "—" : pct(d.exposicion_objetivo, 0) }),
    crear("td", { clase: "motivo", texto: d.motivo }),
  ]));
  t.replaceChildren(crear("caption", { texto: "Régimen (tendencia / volatilidad / fuerza) y motivo de cada decisión de la V8" }),
    crear("thead", {}, [crear("tr", {}, ["Cierre", "Par", "Régimen", "Objetivo", "Motivo"].map((x, i) => crear("th", { texto: x, clase: i && i < 3 || i === 4 ? "texto" : "" })))]),
    crear("tbody", {}, filas));
}

function operaciones(c) {
  const t = el("tabla-operaciones");
  if (!c.ejecuciones.length) {
    t.replaceChildren(crear("caption", { texto: "Todavía no hay operaciones." }));
    return;
  }
  const filas = c.ejecuciones.slice().reverse().map((o) => crear("tr", {}, [
    crear("td", { texto: fechaLarga(o.fecha) }), crear("td", { clase: "texto", texto: o.cartera === "V8" ? "V8" : "30 % fijo" }),
    crear("td", { clase: "texto", texto: o.par }), crear("td", { clase: "texto", texto: `${o.lado} (${o.motivo})` }),
    crear("td", { texto: num(o.unidades) }), crear("td", { texto: eur(o.precio_referencia, 2) }), crear("td", { texto: eur(o.precio_efectivo, 2) }),
    crear("td", { texto: eur(o.comision, 2) }), crear("td", { texto: eur(o.slippage, 2) }), crear("td", { texto: eur(o.funding, 2) }),
    crear("td", { texto: `${pct(o.exposicion_antes, 0)} → ${pct(o.exposicion_objetivo, 0)}` }),
  ]));
  const cab = ["Apertura", "Cartera", "Par", "Orden", "Unidades", "Precio ref.", "Precio efectivo", "Comisión", "Slippage", "Funding", "Exposición"];
  t.replaceChildren(crear("caption", { texto: `${c.ejecuciones.length} órdenes simuladas, de la más reciente a la más antigua` }),
    crear("thead", {}, [crear("tr", {}, cab.map((x, i) => crear("th", { texto: x, clase: i >= 1 && i <= 3 ? "texto" : "" })))]),
    crear("tbody", {}, filas));
}

async function preregistro() {
  const estado = el("prereg-estado");
  try {
    const [r, rh] = await Promise.all([fetch("PREREGISTRO.md", { cache: "no-store" }), fetch("PREREGISTRO.md.sha256", { cache: "no-store" })]);
    if (!r.ok) throw new Error("sin pre-registro");
    const bytes = new Uint8Array(await r.arrayBuffer());
    const calculado = await sha256(bytes);
    const publicado = rh.ok ? (await rh.text()).trim().split(/\s+/)[0] : null;
    estado.replaceChildren(
      crear("div", { texto: "SHA-256 calculado ahora en tu navegador:" }), crear("div", { clase: "hash", texto: calculado }),
      crear("div", {}, [publicado === calculado ? crear("span", { clase: "ok", texto: "Coincide con el hash publicado en el repositorio." })
        : crear("span", { clase: "mal", texto: "No coincide con el hash publicado en el repositorio." })]),
      crear("div", { clase: "nota", texto: "Compáralo también con el hash del tuit del día 0 en X: esa fecha no la puede cambiar nadie desde el repositorio." }));
    el("prereg-texto").textContent = new TextDecoder().decode(bytes);
  } catch {
    estado.replaceChildren(crear("span", { texto: "El pre-registro todavía no se ha publicado." }));
  }
}

// ------------------------------------------------------------------ inicio
async function iniciar() {
  let texto, config;
  try {
    const [r, rc] = await Promise.all([fetch("registro.jsonl", { cache: "no-store" }), fetch("configuracion_congelada.json", { cache: "no-store" })]);
    if (!r.ok) throw new Error(`registro: ${r.status}`);
    texto = await r.text();
    config = rc.ok ? await rc.json() : null;
  } catch (err) {
    el("avisos").append(crear("div", { clase: "aviso", texto: "Todavía no hay registro publicado (el experimento no ha empezado) o no se pudo cargar." }));
    preregistro();
    return;
  }
  const eventos = leerEventos(texto);
  if (eventos[0] && eventos[0].datos.demo) el("demo").hidden = false;
  const costes = config ? { comision: config.configuracion.comision_pct, slippage: config.configuracion.slippage_pct } : { comision: 0.008, slippage: 0.001 };
  const c = calcular(eventos, costes);
  if (!c) return;
  avisos(c); tarjetas(c); dibujar(c); tablaCapital(c); decisiones(c); operaciones(c);
  let ultimo = eventos.at(-1).hash;
  window.addEventListener("resize", () => { clearTimeout(window.__redibujo); window.__redibujo = setTimeout(() => dibujar(c), 150); });

  const resultado = el("resultado-verificacion");
  const verificar = async () => {
    resultado.textContent = "Verificando…";
    const v = await verificarCadena(texto);
    ultimo = v.valido ? v.ultimo : "";
    resultado.replaceChildren(
      v.valido ? crear("div", { clase: "ok", texto: `Cadena íntegra: ${v.lineas} eventos verificados, ninguno alterado.` })
        : crear("div", { clase: "mal", texto: `Cadena ROTA en la línea ${v.linea}: ${v.error}. Los datos de esta página no son fiables.` }),
      crear("div", { texto: v.valido ? "Hash del día (último eslabón):" : "Último eslabón válido antes del fallo:" }),
      crear("div", { clase: "hash", texto: v.ultimo }));
    if (!v.valido && !el("aviso-cadena")) {
      el("avisos").prepend(crear("div", { id: "aviso-cadena", clase: "aviso critico",
        texto: `El registro publicado NO supera la verificación (línea ${v.linea}: ${v.error}). No te fíes de las cifras de esta página.` }));
    }
    comparar();
  };
  el("boton-verificar").onclick = verificar;
  const comparar = () => {
    const valor = el("hash-x").value.trim().toLowerCase().replace(/[^0-9a-f]/g, "");
    const salida = el("resultado-comparar");
    if (!valor) { salida.textContent = ""; return; }
    salida.replaceChildren(ultimo && ultimo.startsWith(valor) && valor.length >= 8
      ? crear("span", { clase: "ok", texto: "Coincide con el hash de hoy." })
      : crear("span", { clase: "mal", texto: valor.length < 8 ? "Escribe al menos 8 caracteres." : "No coincide con el hash de hoy (puede ser de otro día)." }));
  };
  el("hash-x").oninput = comparar;
  verificar();   // también al cargar: si la cadena está rota, se avisa arriba sin esperar al botón
  preregistro();
}

if (typeof document !== "undefined") {
  iniciar();
} else if (typeof module !== "undefined") {
  module.exports = { verificarCadena, leerEventos, calcular };   // solo para el test de paridad con Python
}
