// Admin: the Modeling and Simulation demo (paper: "Simulating the Transactional Core of Fix it with Scrum").
// Everything shown here is computed by the server's discrete-event simulation; this file only draws it and sends the controls.
const NS = "http://www.w3.org/2000/svg";
export const svg = (tag, attrs = {}, ...kids) => {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) el.setAttribute(k, v);
  for (const kid of kids.flat()) if (kid != null) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
};
const f1 = (v, d = 1) => (v == null || Number.isNaN(v) ? "" : Number(v).toFixed(d));
const clock = (t) => { const s = Math.floor(t), d = Math.floor(s / 86400), r = s % 86400; return `day ${d + 1} ${String(Math.floor(r / 3600)).padStart(2, "0")}:${String(Math.floor((r % 3600) / 60)).padStart(2, "0")}`; };

// A small line chart. series: [{name, cls, points: [[x, y]]}]; marks: [{y, label}] horizontal reference lines.
export function lineChart({ title, series, xLabel, yLabel, marks = [], yMax, width = 460, height = 230 }) {
  const m = { l: 46, r: 12, t: 46, b: 38 }, w = width - m.l - m.r, hh = height - m.t - m.b;
  const xs = series.flatMap((s) => s.points.map((p) => p[0])), ys = series.flatMap((s) => s.points.map((p) => p[1])).concat(marks.map((k) => k.y));
  const x0 = Math.min(...xs, 0), x1 = Math.max(...xs, 1), y1 = yMax || Math.max(...ys, 1) * 1.08;
  const X = (v) => m.l + ((v - x0) / (x1 - x0 || 1)) * w, Y = (v) => m.t + hh - (Math.min(v, y1) / y1) * hh;
  const el = svg("svg", { viewBox: `0 0 ${width} ${height}`, class: "chart", role: "img", "aria-label": `${title}: ${series.map((s) => s.name).join(", ")}` });
  el.append(svg("text", { x: m.l, y: 16, class: "ch-title" }, title));
  for (let i = 0; i <= 4; i++) {
    const v = (y1 * i) / 4;
    el.append(svg("line", { x1: m.l, x2: m.l + w, y1: Y(v), y2: Y(v), class: "ch-grid" }), svg("text", { x: m.l - 6, y: Y(v) + 4, class: "ch-tick", "text-anchor": "end" }, f1(v, y1 >= 10 ? 0 : 1)));
  }
  for (let i = 0; i <= 4; i++) {
    const v = x0 + ((x1 - x0) * i) / 4;
    el.append(svg("text", { x: X(v), y: m.t + hh + 16, class: "ch-tick", "text-anchor": "middle" }, f1(v, x1 > 20 ? 0 : 1)));
  }
  for (const k of marks) el.append(svg("line", { x1: m.l, x2: m.l + w, y1: Y(k.y), y2: Y(k.y), class: "ch-mark" }), svg("text", { x: m.l + w - 2, y: Y(k.y) - 4, class: "ch-marklab", "text-anchor": "end" }, k.label));
  for (const s of series) {
    if (s.points.length) el.append(svg("polyline", { points: s.points.map((p) => `${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join(" "), class: "ch-line " + s.cls, fill: "none" }));
    if (s.dots) for (const p of s.points) el.append(svg("circle", { cx: X(p[0]), cy: Y(p[1]), r: 3, class: "ch-dot " + s.cls }));
  }
  el.append(svg("text", { x: m.l + w / 2, y: height - 6, class: "ch-axis", "text-anchor": "middle" }, xLabel), svg("text", { x: 12, y: m.t + hh / 2, class: "ch-axis", transform: `rotate(-90 12 ${m.t + hh / 2})`, "text-anchor": "middle" }, yLabel));
  let lx = m.l;
  for (const s of series) { el.append(svg("line", { x1: lx, x2: lx + 16, y1: 31, y2: 31, class: "ch-line " + s.cls }), svg("text", { x: lx + 20, y: 35, class: "ch-leg" }, s.name)); lx += 30 + s.name.length * 6.2; }
  return el;
}

const FIELDS = [
  ["user_arrival_rate", "Students starting per hour", 1, 400, 1], ["auth_workers", "Authentication workers", 1, 64, 1], ["llm_slots", "LLM call slots", 1, 64, 1],
  ["sandbox_workers", "Sandbox workers", 1, 32, 1], ["run_hours", "Run length (virtual hours)", 1, 168, 1], ["warmup_min", "Warm-up (minutes)", 0, 600, 5], ["seed", "Random seed", 0, 99999, 1],
];
const DIST_LABELS = { login_auth: "Login verification (s)", login_retry: "Wait before a login retry (s)", think: "Student reads and replies (s)", build_context: "E1 context build (s)",
  llm: "LLM call (s)", llm_e1: "LLM call with E1 (s)", sandbox: "Sandbox grading (s)", revise_min: "Revising a solution (min)", score: "E2 scoring (s)" };
const METRICS = [["M1_turn_response_s", "M1 Turn response", "s", 1], ["M2_session_min", "M2 Session time", "min", 1], ["M3_throughput_per_h", "M3 Throughput", "/h", 1],
  ["M4_llm_util_pct", "M4 LLM utilization", "%", 1], ["M5_sandbox_util_pct", "M5 Sandbox utilization", "%", 1], ["M6_llm_queue_avg", "M6 LLM queue (avg)", "", 1], ["M7_llm_queue_max", "M7 LLM queue (max)", "", 0],
  ["M8_llm_wait_s", "M8 LLM wait", "s", 1], ["M9_sandbox_wait_s", "M9 Sandbox wait", "s", 1], ["M10_abandoned", "M10 Abandoned students", "", 1], ["M11_abandon_pct", "M11 Abandonment", "%", 2]];

export function simulationTab({ h, api, toast }) {
  const root = h("section", { class: "simtab" });
  let presets = null, reference = null, cfg = null, dists = null, jobId = null, timer = null, speed = 600, last = null, applying = false;
  const state = { quick: true, busy: false };

  const resolve = () => {
    const p = { user_arrival_rate: +cfg.user_arrival_rate, auth_workers: +cfg.auth_workers, llm_slots: +cfg.llm_slots, sandbox_workers: +cfg.sandbox_workers, budgeted_context: !!cfg.budgeted_context,
      run_seconds: +cfg.run_hours * 3600, warmup_seconds: +cfg.warmup_min * 60, seed: +cfg.seed };
    if (dists) p.dists = dists;
    return p;
  };
  const setPreset = (p) => {
    const d = presets.defaults;
    cfg = { user_arrival_rate: d.user_arrival_rate, auth_workers: d.auth_workers, llm_slots: d.llm_slots, sandbox_workers: d.sandbox_workers, budgeted_context: d.budgeted_context,
      run_hours: d.run_seconds / 3600, warmup_min: d.warmup_seconds / 60, seed: d.seed, ...p.params };
    cfg._preset = p.id;
    dists = p.params.dists || null;
    if (p.params.run_seconds) cfg.run_hours = p.params.run_seconds / 3600;
    draw();
  };

  async function start(kind, extra = {}) {
    if (state.busy) return;
    state.busy = true;
    try {
      const j = await api("/api/v1/instructor/sim/jobs", "POST", { kind, params: resolve(), ...extra });
      jobId = j.id; last = null; poll(true);
    } catch (e) { toast("bad", e.message); }
    state.busy = false;
  }
  async function control(action, extra = {}) {
    try { last = await api(`/api/v1/instructor/sim/jobs/${jobId}/control`, "POST", { action, ...extra }); render(); } catch (e) { toast("bad", e.message); }
  }
  function poll(first) {
    clearInterval(timer);
    const tick = async () => {
      if (!root.isConnected) return clearInterval(timer);
      try { last = await api(`/api/v1/instructor/sim/jobs/${jobId}`); } catch (e) { clearInterval(timer); return; }
      render();
      if (!["queued", "running"].includes(last.status)) clearInterval(timer);
    };
    timer = setInterval(tick, last && last.kind === "live" ? 700 : 600);
    tick();
  }

  // ---- pieces
  const num = (key, label, lo, hi, step) => h("label", { class: "simf" }, label, h("input", { type: "number", min: lo, max: hi, step, value: cfg[key], onchange: (e) => { cfg[key] = e.target.value; } }));
  const form = () => h("div", { class: "simform" },
    h("div", { class: "simrow" }, h("label", { class: "simf wide" }, "Scenario", h("select", { onchange: (e) => { const p = e.target.value === "deployment" ? presets.deployment : presets.presets.find((x) => x.id === e.target.value); if (p) setPreset(p); } },
      presets.presets.concat(presets.deployment ? [presets.deployment] : []).map((p) => h("option", { value: p.id, selected: cfg._preset === p.id }, p.name)))),
      h("button", { onclick: measure }, "Measure this deployment")),
    h("div", { class: "simgrid" }, FIELDS.map((f) => num(f[0], f[1], f[2], f[3], f[4])),
      h("label", { class: "simf check" }, h("input", { type: "checkbox", checked: !!cfg.budgeted_context, onchange: (e) => { cfg.budgeted_context = e.target.checked; } }), "E1 budgeted context (Option B)")),
    h("details", { class: "simdist" }, h("summary", {}, "Service times (triangular min / mode / max)"),
      h("div", { class: "simgrid" }, Object.keys(DIST_LABELS).map((k) => { const v = (dists || presets.paper_dists)[k];
        return h("div", { class: "simd" }, h("span", {}, DIST_LABELS[k]), [0, 1, 2].map((i) => h("input", { type: "number", step: "any", value: v[i], "aria-label": `${DIST_LABELS[k]} ${["min", "mode", "max"][i]}`,
          onchange: (e) => { dists = dists || JSON.parse(JSON.stringify(presets.paper_dists)); dists[k][i] = +e.target.value; } }))); }))));

  async function measure() {
    toast("info", "Timing this deployment's login, interpreter and AI server...");
    try { presets.deployment = await api("/api/v1/instructor/sim/calibrate", "POST", {}); setPreset({ ...presets.deployment, params: { ...presets.deployment.params } }); cfg._preset = "deployment"; draw();
      toast("good", presets.deployment.note); } catch (e) { toast("bad", e.message); }
  }

  const actions = () => h("div", { class: "simactions" },
    h("div", { class: "simrow" }, h("button", { class: "primary", onclick: () => start("live", { speed }) }, "Run live"),
      h("label", { class: "simf inline" }, "Speed", h("input", { type: "range", min: 1, max: 4, step: 1, value: speed <= 60 ? 1 : speed <= 600 ? 2 : speed <= 1800 ? 3 : 4,
        oninput: (e) => { speed = [60, 600, 1800, 3600][e.target.value - 1]; e.target.nextSibling.textContent = `${speed >= 3600 ? "1 h" : speed >= 60 ? speed / 60 + " min" : speed + " s"} of simulated time per second`; } }),
        h("span", {}, `${speed / 60} min of simulated time per second`))),
    h("div", { class: "simrow" }, h("button", { onclick: () => start("baseline", { reps: state.quick ? 5 : 10 }) }, "Experiment 1 · Baseline"),
      h("button", { onclick: () => start("stress", { reps: state.quick ? 3 : 10 }) }, "Experiment 2 · Stress test"),
      h("button", { onclick: () => start("optimize", { reps: state.quick ? 3 : 5, rate: 60 }) }, "Experiment 3 · Optimize A vs B"),
      h("button", { onclick: () => start("validate", { reps: state.quick ? 3 : 4 }) }, "Validate against the paper")),
    h("label", { class: "simf check" }, h("input", { type: "checkbox", checked: state.quick, onchange: (e) => { state.quick = e.target.checked; } }), "Quick replications (untick for the paper's 10 / 10 / 5)"));

  const bar = (label, p) => h("div", { class: "pool" }, h("div", { class: "poolhead" }, h("b", {}, label), h("span", {}, `${p.busy} of ${p.capacity} busy · ${p.queue} waiting`)),
    h("div", { class: "util", role: "progressbar", "aria-valuenow": f1(p.utilization, 0), "aria-valuemin": "0", "aria-valuemax": "100", "aria-label": `${label} utilization` },
      h("i", { class: p.utilization >= 90 ? "hot" : "", "data-w": Math.round(p.utilization) }), h("em", { class: "alarm", title: "90% alarm level" })), h("small", {}, `${f1(p.utilization)}% utilized`));
  const fillBars = (el) => el.querySelectorAll(".util i").forEach((i) => { i.style.width = i.dataset.w + "%"; });

  let ctl = null, ctlJob = null;
  function buildCtl(j, p) {
    const slider = (k, label, lo, hi, val) => h("label", { class: "simf" }, `${label}: `, h("b", {}, val), h("input", { type: "range", min: lo, max: hi, value: val, "data-k": k, oninput: (e) => { e.target.previousSibling.textContent = e.target.value; } }));
    const node = h("div", { class: "livectl" }, h("h4", {}, "Change it while it runs"),
      h("div", { class: "simgrid" }, slider("user_arrival_rate", "Students per hour", 1, 100, Math.round(j.params.user_arrival_rate)), slider("llm_slots", "LLM call slots", 1, 16, p.llm.capacity), slider("sandbox_workers", "Sandbox workers", 1, 8, p.sandbox.capacity),
        h("label", { class: "simf check" }, h("input", { type: "checkbox", "data-k": "budgeted_context", checked: !!j.params.budgeted_context }), "E1 budgeted context")),
      h("div", { class: "simrow" }, h("button", { class: "primary", onclick: () => { const ch = {}; node.querySelectorAll("[data-k]").forEach((e) => { ch[e.dataset.k] = e.type === "checkbox" ? e.checked : +e.value; }); control("apply", { changes: ch }); } }, "Apply now"),
        h("button", { "data-pause": "1", onclick: () => control(last && last.paused ? "resume" : "pause") }, "Pause"), h("button", { onclick: () => control("cancel") }, "Stop"),
        h("label", { class: "simf inline" }, "Speed", h("select", { "data-speed": "1", onchange: (e) => control("speed", { speed: +e.target.value }) }, [[60, "1 min / s"], [600, "10 min / s"], [1800, "30 min / s"], [3600, "1 h / s"], [7200, "2 h / s"]].map(([v, t]) => h("option", { value: v }, t))))),
      h("ul", { class: "applog" }));
    return node;
  }
  function updateCtl(j) {
    ctl.querySelector("[data-pause]").textContent = j.paused ? "Resume" : "Pause";
    const sp = ctl.querySelector("[data-speed]");
    if (document.activeElement !== sp) sp.value = String(j.speed);
    ctl.querySelector(".applog").replaceChildren(...(j.applied || []).slice().reverse().map((a) => h("li", {}, `${clock(a.t)}: `, a.error ? `refused (${a.error})` : Object.entries(a.changes).map(([k, v]) => `${k} = ${v}`).join(", "))));
  }

  function liveView(j) {
    const s = j.live || {}, p = s.pools || {}, series = j.series || [];
    const pts = (key) => series.map((r) => [r.t / 3600, r[key]]);
    const run = j.status === "running";
    const wrap = h("div", { class: "livebox" },
      h("div", { class: "simrow between" }, h("h3", {}, "Live simulation ", h("span", { class: "chip " + (run ? "good" : "") }, j.status)), h("b", { class: "simclock" }, clock(s.t || 0))),
      h("div", { class: "kpis" }, [["Students in the system", s.in_system], ["Completed sessions", s.completed], ["Abandoned students", s.abandoned, s.abandon_pct > 5 ? "bad" : ""],
        ["Abandonment", f1(s.abandon_pct, 2) + "%", s.abandon_pct > 5 ? "bad" : "good"], ["Throughput", f1(s.throughput) + " /h"], ["Average turn", f1(s.avg_turn_s) + " s"]].map(([k, v, c]) =>
        h("div", { class: "kpi " + (c || "") }, h("small", {}, k), h("b", {}, v == null ? "" : v)))),
      h("div", { class: "pools" }, p.llm ? [bar("LLM call slots", p.llm), bar("Sandbox workers", p.sandbox), bar("Authentication workers", p.auth)] : null),
      h("div", { class: "charts" },
        lineChart({ title: "Utilization (per minute)", series: [{ name: "LLM", cls: "c-llm", points: pts("util_llm").map(([x, y]) => [x, y * 100]) }, { name: "Sandbox", cls: "c-sbx", points: pts("util_sbx").map(([x, y]) => [x, y * 100]) }],
          xLabel: "virtual hours", yLabel: "% busy", yMax: 100, marks: [{ y: 90, label: "90% alarm" }] }),
        lineChart({ title: "People waiting", series: [{ name: "LLM queue", cls: "c-llm", points: pts("queue_llm") }, { name: "Sandbox queue", cls: "c-sbx", points: pts("queue_sbx") }, { name: "In system", cls: "c-sys", points: pts("in_system") }], xLabel: "virtual hours", yLabel: "students" }),
        lineChart({ title: "Abandoned students (cumulative)", series: [{ name: "Abandoned", cls: "c-bad", points: pts("abandoned") }, { name: "Completed", cls: "c-ok", points: pts("completed") }], xLabel: "virtual hours", yLabel: "students" })));
    if (run) {   // the controls are built once per run and reused, so a slider is not rebuilt under your finger on every refresh
      if (!ctl || ctlJob !== j.id) { ctl = buildCtl(j, p); ctlJob = j.id; }
      updateCtl(j);
      wrap.append(ctl);
    } else { ctl = null; }
    return wrap;
  }

  const metricTable = (mean, refCol) => h("table", { class: "simtable" }, h("tr", {}, ["Metric", "This run", refCol ? "Paper" : null].filter(Boolean).map((x) => h("th", {}, x))),
    METRICS.map(([k, label, unit, d]) => h("tr", {}, h("td", {}, label), h("td", {}, f1(mean[k], d) + (unit ? " " + unit : "")), refCol ? h("td", { class: "muted" }, refCol[k] != null ? f1(refCol[k], d) + (unit ? " " + unit : "") : "") : null)));

  function resultView(j) {
    const r = j.result;
    if (!r) return null;
    if (j.kind === "baseline") {
      const refCol = Object.fromEntries(Object.entries(reference.table1).filter(([k]) => k !== "scenarios").map(([k, v]) => [k, v[0]]));
      return h("div", {}, h("h3", {}, "Experiment 1 · Baseline analysis"), h("p", { class: "muted" }, `${r.mean.reps} replications of ${r.params.run_seconds / 3600} virtual hours at ${r.params.user_arrival_rate} students/h. The platform runs smoothly when no resource nears the 90% alarm.`),
        metricTable(r.mean, refCol));
    }
    if (j.kind === "stress") {
      const rows = r.rows, ref = reference.exp2, pts = (key) => rows.map((x) => [x.rate, x[key]]), rpts = (key) => Object.entries(ref).map(([rt, v]) => [+rt, v[key]]);
      return h("div", {}, h("h3", {}, "Experiment 2 · Stress test (launch day)"),
        h("p", {}, r.break_point ? h("span", {}, "The system breaks at ", h("b", {}, `${r.break_point} students/h`), `, the first rate above the 5% abandonment limit (paper: ${reference.break_point}). Primary bottleneck: `, h("b", {}, r.bottleneck), ".") : "No rate in this sweep crossed the 5% limit."),
        h("div", { class: "charts" },
          lineChart({ title: "Graph 1 · Abandonment vs load", series: [{ name: "this run", cls: "c-bad", points: pts("M11_abandon_pct"), dots: true }, { name: "paper", cls: "c-paper", points: rpts("M11_abandon_pct") }], xLabel: "students per hour", yLabel: "% abandoned", marks: [{ y: 5, label: "5% limit" }], yMax: 100 }),
          lineChart({ title: "Graph 2 · Turn response vs load", series: [{ name: "this run", cls: "c-llm", points: pts("M1_turn_response_s"), dots: true }, { name: "paper", cls: "c-paper", points: rpts("M1_turn_response_s") }], xLabel: "students per hour", yLabel: "seconds" }),
          lineChart({ title: "Graph 3 · Utilization vs load", series: [{ name: "LLM", cls: "c-llm", points: pts("M4_llm_util_pct"), dots: true }, { name: "Sandbox", cls: "c-sbx", points: pts("M5_sandbox_util_pct"), dots: true }, { name: "paper LLM", cls: "c-paper", points: rpts("M4_llm_util_pct") }], xLabel: "students per hour", yLabel: "% busy", yMax: 100, marks: [{ y: 90, label: "90% alarm" }] })),
        h("table", { class: "simtable" }, h("tr", {}, ["Per hour", "Abandoned", "Abandon %", "Turn s", "LLM %", "Sandbox %", "Throughput", "Paper abandon %"].map((x) => h("th", {}, x))),
          rows.map((x) => h("tr", { class: x.M11_abandon_pct > 5 ? "over" : "" }, h("td", {}, x.rate), h("td", {}, f1(x.M10_abandoned)), h("td", {}, f1(x.M11_abandon_pct, 2)), h("td", {}, f1(x.M1_turn_response_s)),
            h("td", {}, f1(x.M4_llm_util_pct)), h("td", {}, f1(x.M5_sandbox_util_pct)), h("td", {}, f1(x.M3_throughput_per_h)), h("td", { class: "muted" }, ref[x.rate] ? f1(ref[x.rate].M11_abandon_pct, 2) : "")))));
    }
    if (j.kind === "optimize") {
      const a = r.best.A, b = r.best.B, row = (x, name) => x ? h("tr", {}, h("td", {}, name), h("td", {}, x.llm_slots), h("td", {}, x.sandbox_workers), h("td", {}, h("b", {}, x.units)), h("td", {}, f1(x.M11_abandon_pct, 2)), h("td", {}, f1(x.M2_session_min)),
        h("td", {}, f1(x.M3_throughput_per_h)), h("td", {}, f1(x.M4_llm_util_pct))) : null;
      const bySlots = (opt) => r.table.filter((x) => x.option === opt && x.sandbox_workers === 2).map((x) => [x.llm_slots, x.M11_abandon_pct]);
      return h("div", {}, h("h3", {}, `Experiment 3 · Optimization at ${r.rate} students/h`),
        h("p", {}, a && b ? h("span", {}, "Option A (scale resources) needs ", h("b", {}, `${a.llm_slots} LLM slots + ${a.sandbox_workers} sandbox workers = ${a.units} units`), "; Option B (E1 budgeted context) needs ", h("b", {}, `${b.llm_slots} + ${b.sandbox_workers} = ${b.units} units`),
          ` (${r.saving_units >= 0 ? r.saving_units : 0} unit${r.saving_units === 1 ? "" : "s"} cheaper). Paper: A = 7 + 2, B = 6 + 2.`) : "No combination in the range meets the targets."),
        h("table", { class: "simtable" }, h("tr", {}, ["Configuration", "LLM slots", "Sandbox", "Units", "Abandon %", "Session min", "Throughput", "LLM %"].map((x) => h("th", {}, x))),
          row(r.baseline, "Baseline (5 + 1, no E1)"), row(a, "Option A optimum"), row(r.margin.A, "Option A + safety slot"), row(b, "Option B optimum (E1)"), row(r.margin.B, "Option B + safety slot")),
        h("div", { class: "charts" }, lineChart({ title: "Graph 4 · Abandonment vs LLM slots (2 sandbox workers)", series: [{ name: "Option A", cls: "c-bad", points: bySlots("A"), dots: true }, { name: "Option B (E1)", cls: "c-ok", points: bySlots("B"), dots: true }], xLabel: "LLM slots", yLabel: "% abandoned", marks: [{ y: 5, label: "5% limit" }], yMax: 100 })));
    }
    if (j.kind === "validate") {
      return h("div", {}, h("h3", {}, `Validation against the paper: ${r.passed} of ${r.total} checks pass`), h("p", { class: "muted" }, "Each check compares the simulation with a value that needs no simulation (the paper, Section 5.3)."),
        h("table", { class: "simtable" }, h("tr", {}, ["", "Check", "Expected", "Measured", "Allowed error"].map((x) => h("th", {}, x))),
          r.checks.map((c) => h("tr", { class: c.passed ? "" : "over" }, h("td", {}, c.passed ? "pass" : "FAIL"), h("td", {}, h("b", {}, c.name), h("div", { class: "muted small" }, c.note)), h("td", {}, c.expected + " " + c.unit), h("td", {}, c.measured == null ? "none" : c.measured + " " + c.unit),
            h("td", {}, (c.tolerance_kind === "relative" ? Math.round(c.tolerance * 100) + "%" : c.tolerance) + (c.tolerance_kind === "relative" ? "" : " " + c.unit))))));
    }
    return null;
  }

  function render() {
    const j = last;
    const box = root.querySelector(".simout");
    if (!box || !j) return;
    const keepScroll = window.scrollY;
    const parts = [];
    if (["queued", "running"].includes(j.status) && j.kind !== "live") {
      const pct = j.progress.total ? Math.round((100 * j.progress.done) / j.progress.total) : 0;
      parts.push(h("div", { class: "simprog" }, h("b", {}, `Running ${j.kind}...`), h("div", { class: "util", role: "progressbar", "aria-valuenow": String(pct), "aria-valuemin": "0", "aria-valuemax": "100" }, h("i", { "data-w": pct })),
        h("small", {}, `${j.progress.done} of ${j.progress.total} simulation runs finished`), h("button", { onclick: () => control("cancel") }, "Cancel")));
    }
    if (j.status === "error") parts.push(h("div", { class: "err" }, j.error));
    if (j.kind === "live") parts.push(liveView(j));
    if (j.result && j.kind !== "live") parts.push(resultView(j));
    if (j.status === "done" && j.kind === "live" || j.status === "cancelled" && j.kind === "live") parts.push(h("div", {}, h("h3", {}, "Final metrics of this live run"), j.result ? metricTable(j.result.metrics) : null));
    if (j.result || j.series?.length) parts.push(h("p", {}, h("a", { class: "button-link", href: `/api/v1/instructor/sim/jobs/${j.id}/export.csv`, download: `simulation-${j.id}.csv` }, "Download CSV")));
    box.replaceChildren(...parts.filter(Boolean));
    fillBars(box);
    window.scrollTo(0, keepScroll);
  }

  function draw() {
    root.replaceChildren(h("h2", {}, "Modeling and Simulation"),
      h("p", { class: "muted" }, "A discrete-event simulation of the platform's transactional core: students log in, take about 32 turns with the AI team (limited LLM call slots), then submit code to a limited number of sandbox workers. It is the model of the final paper, running here; change the load or the resources and watch where it breaks."),
      form(), actions(), h("div", { class: "simout", "aria-live": "polite" }));
    if (last) render();
  }

  (async () => {
    try {
      presets = await api("/api/v1/instructor/sim/presets");
      reference = await api("/api/v1/instructor/sim/reference");
      setPreset(presets.presets[0]);
    } catch (e) { root.replaceChildren(h("div", { class: "err" }, e.message)); }
  })();
  return root;
}
