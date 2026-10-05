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
  { id: "V8", nombre: "V8, la estrategia", corto: "V8", color: "var(--serie-v8)" },
  { id: "FIJO30", nombre: "30 % fijo", corto: "30 % fijo", color: "var(--serie-fijo)" },
  { id: "BH100", nombre: "Comprar y mantener", corto: "Comprar y mantener", color: "var(--serie-bh)" },
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
const signo = (x) => (x > 0 ? "sube" : x < 0 ? "baja" : "");

function portada(c) {
  el("dia").textContent = `Día ${c.dia}`;
  const v8 = c.resumen.V8;
  el("v8-valor").textContent = eur(v8.equity);
  const datos = [
    ["Hoy", `${eurSigno(v8.hoy)} (${pct(v8.hoyPct, 2, true)})`, signo(v8.hoy)],
    ["Desde el inicio", pct(v8.acumulado, 2, true), signo(v8.acumulado)],
    ["Caída desde máximo", pct(v8.caidaActual), ""],
    ["Invertido", pct(v8.exposicion, 0), ""],
  ];
  el("v8-datos").replaceChildren(...datos.map(([k, v, cl]) =>
    crear("div", {}, [crear("dt", { texto: k }), crear("dd", { texto: v, clase: cl })])));
  el("rivales").replaceChildren(...CARTERAS.filter((k) => k.id !== "V8").map((k) => {
    const r = c.resumen[k.id];
    return crear("div", { clase: "rival", style: `--color:${k.color}` }, [
      crear("p", { clase: "rival__nombre", texto: k.nombre }),
      crear("p", { clase: "rival__valor", texto: eur(r.equity) }),
      crear("p", { clase: "rival__delta" }, [crear("span", { clase: signo(r.hoy), texto: `${eurSigno(r.hoy)} hoy` }),
        `  caída ${pct(r.caidaActual)}`]),
    ]);
  }));
  // Pista de 90 días: hecho, con orden de la V8, y el día actual.
  const conOrden = new Set(c.ejecuciones.filter((o) => o.cartera === "V8").map((o) => o.fecha_decision));
  const pista = el("pista");
  pista.replaceChildren();
  for (let i = 0; i < DIAS; i++) {
    const f = c.fechasDecision[i];
    const hecho = i < c.dia;
    const clases = [hecho ? (conOrden.has(f) ? "orden" : "hecho") : "", i === c.dia - 1 ? "hoy" : ""].join(" ").trim();
    pista.append(crear("i", { clase: clases, title: hecho ? `Día ${i + 1}: cierre del ${fechaLarga(f)}${conOrden.has(f) ? ", con órdenes" : ""}` : `Día ${i + 1}` }));
  }
  pista.append(crear("div", { clase: "pista__leyenda" }, [
    crear("span", {}, [crear("b", { style: "background:var(--accent)" }), "con órdenes"]),
    crear("span", {}, [crear("b", { style: "background:var(--line-strong)" }), "sin órdenes"]),
    crear("span", { texto: `${DIAS - c.dia} días por delante` }),
  ]));
  pista.setAttribute("aria-label", `Día ${c.dia} de ${DIAS}: ${conOrden.size} días con órdenes`);
  const fin = c.fin ? " El experimento ha terminado." : "";
  el("actualizado").textContent = c.ultimaDecision
    ? `Valor tras ejecutar las órdenes en la apertura del ${fechaLarga(c.fechas.at(-1))} (decisión al cierre del ${fechaLarga(c.ultimaDecision)}), con comisiones y slippage.${fin}`
    : "El experimento acaba de empezar: aún no hay ninguna decisión.";
}

function avisos(c) {
  const cont = el("avisos");
  cont.replaceChildren();
  for (const p of c.paradas) {
    cont.append(crear("div", { clase: "aviso critico", texto: `Experimento DETENIDO el ${fechaLarga(p.fecha)} por la regla de parada pre-registrada (caída del ${pct(p.drawdown)}).` }));
  }
  if (c.velasPerdidas.length) {
    const lista = c.velasPerdidas.map((v) => `${v.par.split("/")[0]} ${fechaLarga(v.fecha)}`).join(", ");
    cont.append(crear("div", { clase: "aviso", texto: `Velas perdidas (el bot no se ejecutó y no se operó a posteriori): ${c.velasPerdidas.length}. ${lista}.` }));
  }
  for (const a of c.alertas.slice(-5)) {
    const que = a.regla === "perdida_diaria" ? `pérdida diaria del ${pct(a.variacion)} en ${a.cartera}`
      : a.regla === "perdida_semanal" ? `pérdida semanal del ${pct(a.variacion)} en ${a.cartera}`
      : a.motivo || a.regla;
    cont.append(crear("div", { clase: "aviso", texto: `Aviso${a.fecha ? ` del ${fechaLarga(a.fecha)}` : ""}: ${que}.` }));
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
let primerDibujo = true;
function graficoLineas(contenedor, c, series, opciones) {
  const ancho = contenedor.clientWidth || 600, alto = contenedor.clientHeight || 300;
  // Mismo margen derecho en los dos gráficos: un día cae en la misma vertical en ambos.
  const margen = { izq: 64, der: ancho < 520 ? 10 : 132, arr: 8, aba: opciones.sinEjeX ? 6 : 24 };
  const w = ancho - margen.izq - margen.der, h = alto - margen.arr - margen.aba;
  const n = c.fechas.length;
  const valores = series.flatMap((s) => s.valores);
  let min = Math.min(...valores, opciones.minimo ?? Infinity), max = Math.max(...valores, opciones.maximo ?? -Infinity);
  if (max - min < opciones.rangoMinimo) { const m = (max + min) / 2; min = m - opciones.rangoMinimo / 2; max = m + opciones.rangoMinimo / 2; }
  const ticks = ticksLimpios(min, max, opciones.nTicks || 4);
  min = Math.min(min, ticks[0]); max = Math.max(max, ticks.at(-1));
  const x = (i) => margen.izq + (n === 1 ? w / 2 : (i / (n - 1)) * w);
  const y = (v) => margen.arr + (1 - (v - min) / (max - min)) * h;

  const svg = nodo("svg", { viewBox: `0 0 ${ancho} ${alto}`, "aria-hidden": "true" });
  const rej = nodo("g", { class: "rejilla" }), eje = nodo("g", { class: "eje" });
  for (const t of ticks) {
    rej.append(nodo("line", { x1: margen.izq, x2: margen.izq + w, y1: y(t), y2: y(t) }));
    const txt = nodo("text", { x: margen.izq - 10, y: y(t) + 4, "text-anchor": "end" });
    txt.textContent = opciones.formatoY(t);
    eje.append(txt);
  }
  if (!opciones.sinEjeX) {
    const pasoX = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(w / 90))));
    for (let i = 0; i < n; i += pasoX) {
      const txt = nodo("text", { x: x(i), y: alto - 4, "text-anchor": n === 1 ? "middle" : i === 0 ? "start" : "middle" });
      txt.textContent = fechaCorta(c.fechas[i]);
      eje.append(txt);
    }
  }
  svg.append(rej, eje);
  if (opciones.lineaBase !== undefined) svg.append(nodo("line", { class: "base", x1: margen.izq, x2: margen.izq + w, y1: y(opciones.lineaBase), y2: y(opciones.lineaBase) }));
  const trazos = [];
  for (const s of series) {
    const d = s.valores.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
    if (opciones.area) svg.append(nodo("path", { class: "area", d: `${d}L${x(n - 1)},${y(0)}L${x(0)},${y(0)}Z`, fill: s.color }));
    const p = nodo("path", { class: "linea", d, stroke: s.color, "stroke-width": s.ancho || 2 });
    svg.append(p);
    trazos.push(p);
    if (n < 4) s.valores.forEach((v, i) => svg.append(nodo("circle", { class: "punto", cx: x(i), cy: y(v), r: 4, fill: s.color })));
  }
  if (opciones.titulo) {
    const t = nodo("text", { class: "eje", x: margen.izq, y: margen.arr + 10 });
    t.textContent = opciones.titulo;
    t.setAttribute("fill", "var(--text-3)");
    t.setAttribute("style", "font: 400 11.5px var(--font)");
    svg.append(t);
  }
  // Etiquetas al final de cada línea (texto en tinta, nunca en el color de la serie), separadas si chocan.
  if (opciones.etiquetas && margen.der > 10) {
    const fin = series.map((s) => ({ s, v: s.valores.at(-1) })).sort((a, b) => b.v - a.v);
    let previa = -Infinity;
    for (const { s, v } of fin) {
      const yy = Math.max(y(v), previa + 18);
      previa = yy;
      if (Math.abs(yy - y(v)) > 1) svg.append(nodo("line", { class: "base", x1: x(n - 1) + 4, y1: y(v), x2: x(n - 1) + 12, y2: yy }));
      const txt = nodo("text", { class: `etiqueta-final${s.principal ? " principal" : ""}`, x: x(n - 1) + 14, y: yy + 4 });
      txt.textContent = `${s.corto}  ${opciones.formatoY(v)}`;
      svg.append(txt);
    }
  }
  const cursor = nodo("line", { class: "cursor", y1: margen.arr, y2: margen.arr + h, visibility: "hidden" });
  const puntos = series.map((s) => nodo("circle", { class: "punto", r: 4.5, fill: s.color, visibility: "hidden" }));
  svg.append(cursor, ...puntos);
  contenedor.replaceChildren(svg);
  // Un único momento de movimiento: la curva de la V8 se traza al cargar (no en cada redibujo).
  if (primerDibujo && opciones.trazar && n > 1) {
    const principal = trazos[series.findIndex((s) => s.principal)];
    if (principal) {
      const largo = principal.getTotalLength();
      principal.style.setProperty("--largo", `${largo}`);
      principal.classList.add("dibujar");
    }
  }
  graficos.push({ contenedor, x, y, n, series, cursor, puntos, margen, w, c });
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
  tt.replaceChildren(crear("div", { clase: "fecha", texto: `Apertura del ${fechaLarga(c.fechas[i])}${i === 0 ? " (día 0)" : ` (día ${i})`}` }));
  for (const cart of CARTERAS) {
    tt.append(crear("div", { clase: "fila" }, [
      crear("span", {}, [crear("i", { style: `--color:${cart.color}` }), cart.corto]),
      crear("span", { texto: `${eur(c.serie[cart.id][i])}  caída ${pct(c.resumen[cart.id].caidas[i])}` }),
    ]));
  }
  tt.hidden = false;
  const r = graficos[0].contenedor.getBoundingClientRect();
  const px = evento && "clientX" in evento ? evento.clientX : r.left + graficos[0].x(i);
  const py = evento && "clientY" in evento ? evento.clientY : r.top + 20;
  tt.style.left = `${Math.max(12, Math.min(window.innerWidth - tt.offsetWidth - 12, px + 16))}px`;
  tt.style.top = `${Math.max(12, py - tt.offsetHeight - 16)}px`;
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
  el("leyenda").replaceChildren(...CARTERAS.map((k) => crear("span", {}, [crear("i", { style: `--color:${k.color}` }), k.nombre])));
  graficoLineas(el("grafico-capital"), c,
    CARTERAS.slice().reverse().map((k) => ({ valores: c.serie[k.id], color: k.color, corto: k.corto, principal: k.id === "V8", ancho: k.id === "BH100" ? 1.5 : k.id === "V8" ? 2.75 : 2 })),
    { formatoY: (v) => eur(v), rangoMinimo: 400, lineaBase: CAPITAL, etiquetas: true, trazar: true, sinEjeX: true });
  graficoLineas(el("grafico-caida"), c,
    CARTERAS.filter((k) => k.id !== "BH100").map((k) => ({ valores: c.resumen[k.id].caidas.map((d) => -d * 100), color: k.color, corto: k.corto })),
    { formatoY: (v) => `${nf0.format(v)} %`, rangoMinimo: 2, maximo: 0, area: true, nTicks: 2 });
  primerDibujo = false;
  interaccion();
}

function tablaCapital(c) {
  const cab = crear("tr", {}, [crear("th", { texto: "Apertura" }), ...CARTERAS.flatMap((k) => [crear("th", { texto: k.corto }), crear("th", { texto: "Caída" })])]);
  const filas = c.fechas.map((f, i) => crear("tr", {}, [crear("td", { texto: fechaLarga(f) + (i === 0 ? " (día 0)" : "") }),
    ...CARTERAS.flatMap((k) => [crear("td", { texto: eur(c.serie[k.id][i], 2) }), crear("td", { texto: pct(c.resumen[k.id].caidas[i]) })])]));
  el("tabla-capital").replaceChildren(crear("caption", { texto: "Valor de cada cartera tras ejecutar las órdenes del día, a precio de apertura (con comisiones y slippage)" }), crear("thead", {}, [cab]), crear("tbody", {}, filas.reverse()));
}

function decisiones(c) {
  const cont = el("decision-hoy");
  cont.replaceChildren();
  const hoy = c.decisiones.filter((d) => d.cartera === "V8" && d.fecha === c.ultimaDecision);
  if (!hoy.length) cont.append(crear("p", { clase: "vacio", texto: "Aún no hay decisiones: la primera llega con el primer cierre tras el día 0." }));
  for (const d of hoy) {
    const r = d.regimen;
    const objetivo = d.exposicion_objetivo === null ? "sin decisión" : `${pct(d.exposicion_objetivo, 0)} invertido`;
    cont.append(crear("article", { clase: "decision" }, [
      crear("h3", {}, [`${d.par.split("/")[0]} hoy`, crear("span", { texto: objetivo })]),
      crear("div", { clase: "chips" }, [`tendencia ${r.tendencia}`, `volatilidad ${r.volatilidad}`, `fuerza ${ETIQUETA[r.fuerza] || r.fuerza}`]
        .map((txt) => crear("span", { clase: "chip", texto: txt }))),
      crear("p", { texto: d.exposicion_objetivo === null ? "Dato sospechoso: hoy no se decide y se mantiene la posición." : d.motivo, title: d.motivo }),
    ]));
  }
  const filas = c.decisiones.filter((d) => d.cartera === "V8").slice().reverse().map((d) => crear("tr", {}, [
    crear("td", { texto: fechaLarga(d.fecha) }), crear("td", { clase: "texto", texto: d.par }),
    crear("td", { clase: "texto", texto: `${d.regimen.tendencia}, ${d.regimen.volatilidad}, ${ETIQUETA[d.regimen.fuerza] || d.regimen.fuerza}` }),
    crear("td", { texto: d.exposicion_objetivo === null ? "sin decisión" : pct(d.exposicion_objetivo, 0) }),
    crear("td", { clase: "motivo", texto: d.motivo }),
  ]));
  const t = el("tabla-decisiones");
  if (!filas.length) { t.replaceChildren(crear("caption", { texto: "Todavía no hay decisiones." })); return; }
  t.replaceChildren(crear("caption", { texto: "Régimen (tendencia, volatilidad, fuerza) y motivo de cada decisión de la V8" }),
    crear("thead", {}, [crear("tr", {}, [["Cierre", ""], ["Par", "texto"], ["Régimen", "texto"], ["Objetivo", ""], ["Motivo", "texto"]]
      .map(([x, cl]) => crear("th", { texto: x, clase: cl })))]),
    crear("tbody", {}, filas));
}

function operaciones(c) {
  const t = el("tabla-operaciones");
  if (!c.ejecuciones.length) { t.replaceChildren(crear("caption", { texto: "Todavía no hay operaciones." })); return; }
  const filas = c.ejecuciones.slice().reverse().map((o) => crear("tr", {}, [
    crear("td", { texto: fechaLarga(o.fecha) }), crear("td", { clase: "texto", texto: o.cartera === "V8" ? "V8" : "30 % fijo" }),
    crear("td", { clase: "texto", texto: o.par }), crear("td", { clase: "texto", texto: `${o.lado} (${o.motivo})` }),
    crear("td", { texto: num(o.unidades) }), crear("td", { texto: eur(o.precio_referencia, 2) }), crear("td", { texto: eur(o.precio_efectivo, 2) }),
    crear("td", { texto: eur(o.comision, 2) }), crear("td", { texto: eur(o.slippage, 2) }), crear("td", { texto: eur(o.funding, 2) }),
    crear("td", { texto: `${pct(o.exposicion_antes, 0)} a ${pct(o.exposicion_objetivo, 0)}` }),
  ]));
  const cab = [["Apertura", ""], ["Cartera", "texto"], ["Par", "texto"], ["Orden", "texto"], ["Unidades", ""], ["Precio ref.", ""],
    ["Precio efectivo", ""], ["Comisión", ""], ["Slippage", ""], ["Funding", ""], ["Exposición", ""]];
  t.replaceChildren(crear("caption", { texto: `${c.ejecuciones.length} órdenes simuladas, de la más reciente a la más antigua` }),
    crear("thead", {}, [crear("tr", {}, cab.map(([x, cl]) => crear("th", { texto: x, clase: cl })))]),
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
  } catch {
    el("avisos").append(crear("div", { clase: "aviso", texto: "Todavía no hay registro publicado (el experimento no ha empezado) o no se pudo cargar." }));
    el("sello-estado").textContent = "Sin registro todavía";
    el("sello-mini-estado").textContent = "Sin registro todavía";
    preregistro();
    return;
  }
  const eventos = leerEventos(texto);
  if (eventos[0] && eventos[0].datos.demo) el("demo").hidden = false;
  const costes = config ? { comision: config.configuracion.comision_pct, slippage: config.configuracion.slippage_pct } : { comision: 0.008, slippage: 0.001 };
  const c = calcular(eventos, costes);
  if (!c) return;
  avisos(c); portada(c); dibujar(c); tablaCapital(c); decisiones(c); operaciones(c);
  let ultimo = "";
  window.addEventListener("resize", () => { clearTimeout(window.__redibujo); window.__redibujo = setTimeout(() => dibujar(c), 150); });

  const resultado = el("resultado-verificacion");
  const sello = el("sello");
  const verificar = async () => {
    resultado.textContent = "Verificando…";
    sello.className = "sello cargando";
    const v = await verificarCadena(texto);
    ultimo = v.valido ? v.ultimo : "";
    sello.className = `sello ${v.valido ? "ok" : "mal"}`;
    el("sello-estado").textContent = v.valido ? "Registro íntegro" : "Registro alterado";
    el("sello-detalle").textContent = v.valido
      ? `${v.lineas} eventos encadenados con SHA-256, verificados ahora en tu navegador.`
      : `La cadena se rompe en la línea ${v.linea}: ${v.error}. No te fíes de estas cifras.`;
    el("sello-hash").textContent = v.ultimo;
    el("sello-mini").className = `sello-mini ${v.valido ? "ok" : "mal"}`;
    el("sello-mini-estado").textContent = v.valido ? "Registro íntegro · hash del día" : "Registro alterado";
    el("sello-mini-hash").textContent = v.ultimo ? `${v.ultimo.slice(0, 16)}…${v.ultimo.slice(-6)}` : "";
    el("sello-mini-hash").title = v.ultimo;
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
  const comparar = () => {
    const valor = el("hash-x").value.trim().toLowerCase().replace(/[^0-9a-f]/g, "");
    const salida = el("resultado-comparar");
    if (!valor) { salida.textContent = ""; return; }
    salida.replaceChildren(ultimo && ultimo.startsWith(valor) && valor.length >= 8
      ? crear("span", { clase: "sube", texto: "Coincide con el hash de hoy." })
      : crear("span", { clase: "baja", texto: valor.length < 8 ? "Escribe al menos 8 caracteres." : "No coincide con el hash de hoy (puede ser de otro día)." }));
  };
  el("boton-verificar").onclick = verificar;
  el("hash-x").oninput = comparar;
  verificar();   // también al cargar: el sello de la portada muestra el resultado
  preregistro();
}

if (typeof document !== "undefined") {
  iniciar();
} else if (typeof module !== "undefined") {
  module.exports = { verificarCadena, leerEventos, calcular };   // solo para el test de paridad con Python
}
