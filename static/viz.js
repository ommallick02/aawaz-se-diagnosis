// SVG visuals: skill-prerequisite mastery map, per-skill mastery line chart,
// and the two re-teaching models (number line, fraction bars).

const NS = "http://www.w3.org/2000/svg";

function el(tag, attrs = {}, parent) {
  const node = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) node.setAttribute(k, v);
  if (parent) parent.appendChild(node);
  return node;
}

function text(parent, x, y, str, attrs = {}) {
  const t = el("text", { x, y, ...attrs }, parent);
  t.textContent = str;
  return t;
}

const pct = (p) => (p == null ? "—" : `${Math.round(p * 100)}%`);
const LEVEL_LABEL = { not_started: "not started", needs_help: "needs help", developing: "developing", mastered: "mastered" };

function tooltip(container) {
  let tip = container.querySelector(":scope > .viz-tip");
  if (!tip) {
    tip = document.createElement("div");
    tip.className = "viz-tip";
    tip.setAttribute("role", "tooltip");
    container.appendChild(tip);
  }
  return {
    show(html, x, y) {
      tip.innerHTML = html;
      tip.style.display = "block";
      const box = container.getBoundingClientRect();
      const w = tip.offsetWidth;
      const left = Math.min(Math.max(4, x - w / 2), box.width - w - 4);
      tip.style.left = `${left}px`;
      tip.style.top = `${Math.max(4, y - tip.offsetHeight - 10)}px`;
    },
    hide() { tip.style.display = "none"; },
  };
}

function svgPoint(svg, evt) {
  const pt = svg.createSVGPoint();
  pt.x = evt.clientX;
  pt.y = evt.clientY;
  return pt.matrixTransform(svg.getScreenCTM().inverse());
}

function containerPoint(container, evt) {
  const box = container.getBoundingClientRect();
  return { x: evt.clientX - box.left, y: evt.clientY - box.top };
}

// ------------------------------------------------------------------ skill map
export function renderSkillMap(container, skills, studentSkills, selectedId, onSelect) {
  container.querySelectorAll("svg").forEach((n) => n.remove());
  const stats = Object.fromEntries((studentSkills || []).map((s) => [s.id, s]));
  const byId = Object.fromEntries(skills.map((s) => [s.id, s]));
  const depth = {};
  const depthOf = (id) => {
    if (depth[id] != null) return depth[id];
    const pre = byId[id].prereqs;
    depth[id] = pre.length ? 1 + Math.max(...pre.map(depthOf)) : 0;
    return depth[id];
  };
  skills.forEach((s) => depthOf(s.id));
  const layers = [];
  skills.forEach((s) => (layers[depth[s.id]] ||= []).push(s));

  const W = 360, nodeW = 118, nodeH = 52, rowH = 78, top = 10;
  const pos = {};
  layers.forEach((layer, d) => {
    // Order each layer by the average x of its prerequisites to keep edges from crossing.
    if (d > 0) {
      layer.sort((a, b) => {
        const bx = (s) => s.prereqs.reduce((sum, p) => sum + pos[p].x, 0) / s.prereqs.length;
        return bx(a) - bx(b);
      });
    }
    const gap = (W - layer.length * nodeW) / (layer.length + 1);
    layer.forEach((s, i) => {
      pos[s.id] = { x: gap + i * (nodeW + gap) + nodeW / 2, y: top + d * rowH };
    });
  });
  const H = top + layers.length * rowH - (rowH - nodeH) + 8;

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "skill-map", role: "img",
    "aria-label": "Skill map: prerequisite graph coloured by mastery" }, null);
  container.prepend(svg);
  const defs = el("defs", {}, svg);
  const marker = el("marker", { id: "arrow", viewBox: "0 0 8 8", refX: 7, refY: 4, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse" }, defs);
  el("path", { d: "M0,0 L8,4 L0,8 z", class: "edge-head" }, marker);

  const edges = el("g", {}, svg);
  skills.forEach((s) => s.prereqs.forEach((p) => {
    const a = pos[p], b = pos[s.id];
    const y1 = a.y + nodeH, y2 = b.y - 2, my = (y1 + y2) / 2;
    let d = `M${a.x},${y1} C${a.x},${my} ${b.x},${my} ${b.x},${y2}`;
    if (depth[s.id] - depth[p] > 1) {
      // Edges that skip layers run down a side lane so they never cut through a node.
      const lane = b.x >= W / 2 ? W - 12 : 12, r = 8, dir = lane > a.x ? 1 : -1, back = b.x > lane ? 1 : -1;
      const ya = y1 + (rowH - nodeH) / 2, yb = b.y - (rowH - nodeH) / 2;
      d = `M${a.x},${y1} V${ya - r} Q${a.x},${ya} ${a.x + dir * r},${ya} H${lane - dir * r} Q${lane},${ya} ${lane},${ya + r}` +
          ` V${yb - r} Q${lane},${yb} ${lane + back * r},${yb} H${b.x - back * r} Q${b.x},${yb} ${b.x},${yb + r} V${y2}`;
    }
    el("path", { d, class: "edge", "marker-end": "url(#arrow)" }, edges);
  }));

  const tip = tooltip(container);
  skills.forEach((s) => {
    const st = stats[s.id] || { p: null, level: "not_started", active_misconceptions: 0, attempts: 0 };
    const { x, y } = pos[s.id];
    const g = el("g", { class: `node level-${st.level}${s.id === selectedId ? " selected" : ""}`, tabindex: 0, role: "button",
      transform: `translate(${x - nodeW / 2},${y})`, "aria-label": `${s.name}: ${pct(st.p)} ${LEVEL_LABEL[st.level]}` }, svg);
    el("rect", { width: nodeW, height: nodeH, rx: 10, class: "node-bg" }, g);
    text(g, 10, 18, s.short, { class: "node-title" });
    text(g, 10, 33, st.attempts ? `${pct(st.p)} · ${LEVEL_LABEL[st.level]}` : "not started", { class: "node-sub" });
    const trackW = nodeW - 20;
    el("rect", { x: 10, y: 40, width: trackW, height: 5, rx: 2.5, class: "node-track" }, g);
    if (st.p != null && st.attempts) el("rect", { x: 10, y: 40, width: Math.max(5, trackW * st.p), height: 5, rx: 2.5, class: "node-fill" }, g);
    el("line", { x1: 10 + trackW * 0.8, x2: 10 + trackW * 0.8, y1: 38, y2: 47, class: "node-goal" }, g);
    if (st.active_misconceptions) {
      el("circle", { cx: nodeW - 2, cy: 2, r: 9, class: "node-badge" }, g);
      text(g, nodeW - 2, 5.5, String(st.active_misconceptions), { class: "node-badge-text", "text-anchor": "middle" });
    }
    const describe = () => `<b>${s.name}</b><br>${st.attempts ? `${pct(st.p)} mastery · ${LEVEL_LABEL[st.level]}` : "Not started yet"}` +
      (st.active_misconceptions ? `<br><span class="tip-alert">⚠ ${st.active_misconceptions} open misconception${st.active_misconceptions > 1 ? "s" : ""}</span>` : "") +
      (s.prereqs.length ? `<br><span class="tip-muted">Builds on: ${s.prereqs.map((p) => byId[p].short).join(", ")}</span>` : "");
    g.addEventListener("mouseenter", (e) => { const p = containerPoint(container, e); tip.show(describe(), p.x, p.y); });
    g.addEventListener("mousemove", (e) => { const p = containerPoint(container, e); tip.show(describe(), p.x, p.y); });
    g.addEventListener("mouseleave", () => tip.hide());
    g.addEventListener("click", () => onSelect(s.id));
    g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(s.id); } });
  });
}

// ------------------------------------------------------------------ mastery over time
export function renderMasteryChart(container, history, skillName) {
  container.querySelectorAll("svg, .empty").forEach((n) => n.remove());
  if (!history.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = `No attempts on ${skillName} yet. Answer a question to start the graph.`;
    container.prepend(empty);
    return;
  }
  const W = 360, H = 190, m = { l: 38, r: 40, t: 14, b: 26 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const n = history.length;
  const xs = (i) => m.l + (n === 1 ? iw / 2 : (i / (n - 1)) * iw);
  const ys = (p) => m.t + (1 - p) * ih;

  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "mastery-chart", role: "img",
    "aria-label": `Mastery of ${skillName} over ${n} attempts, now ${pct(history[n - 1].p)}` });
  container.prepend(svg);
  [0, 0.25, 0.5, 0.75, 1].forEach((v) => {
    el("line", { x1: m.l, x2: W - m.r, y1: ys(v), y2: ys(v), class: v === 0 ? "axis" : "grid" }, svg);
    text(svg, m.l - 6, ys(v) + 4, `${v * 100}%`, { class: "tick", "text-anchor": "end" });
  });
  el("line", { x1: m.l, x2: W - m.r, y1: ys(0.8), y2: ys(0.8), class: "goal" }, svg);
  text(svg, W - m.r + 4, ys(0.8) + 4, "mastered", { class: "tick goal-label" });
  text(svg, m.l, H - 6, "older", { class: "tick" });
  text(svg, W - m.r, H - 6, "latest attempt", { class: "tick", "text-anchor": "end" });

  const d = history.map((h, i) => `${i ? "L" : "M"}${xs(i)},${ys(h.p)}`).join(" ");
  el("path", { d, class: "line" }, svg);
  history.forEach((h, i) => {
    if (h.event === "start") return;
    el("circle", { cx: xs(i), cy: ys(h.p), r: h.event === "diagnosis" ? 4.5 : 3.5, class: `dot dot-${h.event}` }, svg);
  });
  const last = history[n - 1];
  text(svg, xs(n - 1) + 8, ys(last.p) + 4, pct(last.p), { class: "end-label" });

  const cross = el("line", { y1: m.t, y2: m.t + ih, class: "crosshair", visibility: "hidden" }, svg);
  const focus = el("circle", { r: 6, class: "focus", visibility: "hidden" }, svg);
  const hit = el("rect", { x: m.l - 10, y: 0, width: iw + 20, height: H, fill: "transparent" }, svg);
  const tip = tooltip(container);
  const EVENT = { start: "Starting estimate", diagnosis: "Spoken diagnosis", drill: "Practice drill" };
  hit.addEventListener("mousemove", (e) => {
    const p = svgPoint(svg, e);
    const i = n === 1 ? 0 : Math.max(0, Math.min(n - 1, Math.round(((p.x - m.l) / iw) * (n - 1))));
    const h = history[i];
    cross.setAttribute("x1", xs(i)); cross.setAttribute("x2", xs(i)); cross.setAttribute("visibility", "visible");
    focus.setAttribute("cx", xs(i)); focus.setAttribute("cy", ys(h.p)); focus.setAttribute("visibility", "visible");
    const when = new Date(h.ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    const box = svg.getBoundingClientRect(), cbox = container.getBoundingClientRect();
    const scale = box.width / W;
    tip.show(`<b>${pct(h.p)}</b> · ${EVENT[h.event] || h.event}<br><span class="tip-muted">${when}${h.detail ? " · " + escapeHtml(h.detail) : ""}</span>`,
      box.left - cbox.left + xs(i) * scale, box.top - cbox.top + ys(h.p) * scale);
  });
  hit.addEventListener("mouseleave", () => {
    cross.setAttribute("visibility", "hidden"); focus.setAttribute("visibility", "hidden"); tip.hide();
  });
}

// ------------------------------------------------------------------ number line
export function renderNumberLine(container, nl) {
  const W = 640, H = 196, m = 34, axisY = 122;
  const span = nl.max - nl.min || 1;
  const xs = (v) => m + ((v - nl.min) / span) * (W - 2 * m);
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "number-line", role: "img",
    "aria-label": `Number line from ${nl.min} to ${nl.max}` });
  container.appendChild(svg);
  const defs = el("defs", {}, svg);
  const marker = el("marker", { id: "jump-head", viewBox: "0 0 8 8", refX: 6, refY: 4, markerWidth: 7, markerHeight: 7, orient: "auto" }, defs);
  el("path", { d: "M0,0 L8,4 L0,8 z", class: "jump-head" }, marker);

  el("line", { x1: m - 14, x2: W - m + 14, y1: axisY, y2: axisY, class: "nl-axis" }, svg);
  const steps = Math.round(span / nl.step);
  const every = Math.ceil((steps + 1) / 11);
  const decimals = Math.min(3, Math.max(0, -Math.floor(Math.log10(nl.step) + 1e-9)));
  for (let k = 0; k <= steps; k++) {
    const v = nl.min + k * nl.step;
    const major = k % every === 0;
    el("line", { x1: xs(v), x2: xs(v), y1: axisY - (major ? 7 : 4), y2: axisY + (major ? 7 : 4), class: "nl-tick" }, svg);
    if (major) text(svg, xs(v), axisY + 22, formatNum(v, decimals), { class: "nl-tick-label", "text-anchor": "middle" });
  }

  // Wider jumps arc higher so arcs sharing a start point nest instead of colliding.
  const jumps = [...(nl.jumps || [])].sort((a, b) => Math.abs(a.to - a.from) - Math.abs(b.to - b.from));
  let lastH = 0;
  jumps.forEach((j) => {
    const x1 = xs(j.from), x2 = xs(j.to);
    const h = Math.min(84, Math.max(20, Math.abs(x2 - x1) * 0.3, lastH + 18));
    lastH = h;
    el("path", { d: `M${x1},${axisY - 6} Q${(x1 + x2) / 2},${axisY - 6 - h * 2} ${x2},${axisY - 6}`, class: "jump", "marker-end": "url(#jump-head)" }, svg);
    if (j.label) text(svg, (x1 + x2) / 2, axisY - 10 - h, j.label, { class: "jump-label", "text-anchor": "middle" });
  });

  const marks = [...(nl.marks || [])].sort((a, b) => a.value - b.value);
  let lastX = -Infinity, row = 0;
  marks.forEach((mk) => {
    const x = xs(mk.value);
    row = x - lastX < 46 ? (row + 1) % 2 : 0;
    lastX = x;
    el("circle", { cx: x, cy: axisY, r: mk.highlight ? 7 : 5, class: mk.highlight ? "nl-mark hl" : "nl-mark" }, svg);
    if (mk.label) text(svg, x, axisY + 44 + row * 18, mk.label, { class: mk.highlight ? "nl-mark-label hl" : "nl-mark-label", "text-anchor": "middle" });
  });
}

// ------------------------------------------------------------------ fraction bars
export function renderBars(container, items) {
  const W = 640, rowH = 62, labelH = 18, barH = 30, gap = 2;
  const H = items.length * rowH + 4;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "frac-bars", role: "img",
    "aria-label": items.map((b) => `${b.label}: ${b.shaded} of ${b.parts} equal parts shaded`).join("; ") });
  container.appendChild(svg);
  items.forEach((b, r) => {
    const y = r * rowH + 2;
    text(svg, 0, y + 13, b.label, { class: "bar-label" });
    text(svg, W, y + 13, `${b.shaded} of ${b.parts} equal parts`, { class: "bar-count", "text-anchor": "end" });
    const segW = (W - gap * (b.parts - 1)) / b.parts;
    for (let i = 0; i < b.parts; i++) {
      el("rect", { x: i * (segW + gap), y: y + labelH + 2, width: segW, height: barH, rx: 4,
        class: i < b.shaded ? "seg shaded" : "seg" }, svg);
    }
  });
}

function formatNum(v, decimals) {
  const s = Math.abs(v) < 1e-9 ? "0" : v.toFixed(decimals);
  return s.replace("-", "−");
}

export function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
