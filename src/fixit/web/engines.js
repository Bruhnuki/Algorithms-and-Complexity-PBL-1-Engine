// Admin: the AlgoCom engines (E1 context window chaining, E2 learning gain) running for real inside the app.
// Everything shown is computed by the server's `pbl_engine` package; this file only sends the inputs and draws what comes back.
import { lineChart, svg } from "/sim.js";

const f = (v, d = 2) => (v == null || Number.isNaN(v) ? "-" : Number(v).toFixed(d));
const GOOD = ["standup_held", "blocker_cleared", "coach", "dod_honest", "review_before_push"];
const hhmmss = (t) => new Date(t * 1000).toTimeString().slice(0, 8);

export function enginesTab({ h, api, toast }) {
  const root = h("section", { class: "simtab engtab" });
  const S = { since: 0, calls: [], total: 0, summary: null, runs: [],
    e1: { source: "synthetic", run_id: "", n: 120, seed: 1, stage: "BUILD", advance_to: "", budget: 3000, mode: "auto" },
    e2: { source: "synthetic", n: 30, mean_pre: 40, mean_post: 65, spread: 15, seed: 1, B: 1000, run_id: "" } };
  const box = (cls) => h("div", { class: cls });
  const feedBox = box("engfeed"), e1Out = box("engout"), e2Out = box("engout"), benchOut = box("engout");

  // ---- live feed: the real calls the game and this page make, newest first
  const detail = (c) => ["stage", "mode", "segments", "budget", "chosen", "tokens_used", "dp_cells", "gap_bound", "events", "students", "bootstrap", "score", "ok", "status"]
    .filter((k) => c[k] != null).map((k) => `${k.replace("_", " ")} ${typeof c[k] === "number" ? f(c[k], Number.isInteger(c[k]) ? 0 : 3) : c[k]}`).join(" · ");
  function drawFeed() {
    const sm = S.summary || { E1: {}, E2: {} };
    feedBox.replaceChildren(
      h("div", { class: "kpis" }, ["E1", "E2"].map((e) => h("div", { class: "kpi" }, h("small", {}, e === "E1" ? "E1 context window chaining" : "E2 learning gain"), h("b", {}, `${sm[e].calls || 0} calls`),
        h("small", {}, sm[e].avg_ms != null ? `avg ${f(sm[e].avg_ms, 3)} ms · max ${f(sm[e].max_ms, 3)} ms` : "no calls yet"))), h("div", { class: "kpi" }, h("small", {}, "Total since the server started"), h("b", {}, String(S.total)))),
      S.calls.length ? h("table", { class: "simtable engfeedtable" }, h("thead", {}, h("tr", {}, ["Time", "Engine", "Call", "From", "Details", "ms"].map((t) => h("th", {}, t)))),
        h("tbody", {}, S.calls.slice(0, 14).map((c) => h("tr", { class: "src-" + c.source }, h("td", {}, hhmmss(c.t)), h("td", {}, h("b", {}, c.engine)), h("td", {}, c.op), h("td", {}, c.source),
          h("td", {}, detail(c)), h("td", {}, f(c.ms, 3))))))
        : h("p", { class: "muted" }, "No calls yet. Chat in Slackish or play a Sprint in another window: every teammate line and every stage change is a real engine call and appears here."));
  }
  async function pollFeed() {
    if (!root.isConnected) return clearInterval(S.timer);
    try {
      const r = await api(`/api/v1/instructor/engines/feed?since=${S.since}`);
      S.summary = r.summary; S.total = r.total;
      if (r.calls.length) { S.calls = r.calls.reverse().concat(S.calls).slice(0, 60); S.since = r.total; }
      drawFeed();
    } catch (_) { /* a failed poll is retried on the next tick */ }
  }

  // ---- form helpers
  const field = (obj, key, label, type = "number", extra = {}) => h("label", { class: "simf" }, label, h("input", { type, value: obj[key], ...extra, onchange: (e) => { obj[key] = type === "number" ? +e.target.value : e.target.value; } }));
  const pick = (obj, key, label, options, after) => h("label", { class: "simf" }, label, h("select", { onchange: (e) => { obj[key] = e.target.value; if (after) after(); } },
    options.map(([v, t]) => h("option", { value: v, selected: String(obj[key]) === String(v) }, t))));
  const runPicker = (obj, label) => h("label", { class: "simf" }, label, h("select", { "data-runs": "1", onchange: (e) => { obj.run_id = e.target.value; } },
    h("option", { value: "" }, "(none)"), S.runs.map((r) => h("option", { value: r.run_id, selected: String(obj.run_id) === String(r.run_id) }, `run ${r.run_id} · ${r.student} · ${r.status}`))));

  // ---- E1 workbench
  const e1Form = box("simform");
  function drawE1Form() {
    const e = S.e1;
    e1Form.replaceChildren(
      h("div", { class: "simgrid" }, pick(e, "source", "Transcript", [["synthetic", "Synthetic (the paper's instance)"], ["run", "A real run's transcript and memory"]], () => drawE1Form()),
        e.source === "run" ? runPicker(e, "Run") : field(e, "n", "Segments (1 to 2000)", "number", { min: 1, max: 2000 }),
        pick(e, "stage", "Current stage", ["PLANNING", "STANDUP", "BUILD", "REVIEW"].map((s) => [s, s])),
        pick(e, "advance_to", "Advance first to", [["", "(stay)"], ["STANDUP", "STANDUP"], ["BUILD", "BUILD"], ["REVIEW", "REVIEW"]]),
        field(e, "budget", "Token budget", "number", { min: 50, max: 32000, step: 50 }), pick(e, "mode", "Policy", [["auto", "Auto (exact while small)"], ["exact", "Exact DP"], ["greedy", "Greedy"]]),
        field(e, "seed", "Random seed", "number", { min: 0 })),
      h("div", { class: "simrow" }, h("button", { class: "primary", onclick: runE1 }, "Run E1"), h("button", { onclick: () => { S.e1.source = S.e1.source === "run" ? "synthetic" : "run"; drawE1Form(); } }, "Switch transcript source")));
  }
  async function runE1() {
    const e = S.e1, body = { source: e.source, n: e.n, seed: e.seed, stage: e.stage, budget: e.budget, mode: e.mode };
    if (e.advance_to) body.advance_to = e.advance_to;
    if (e.source === "run") { if (!e.run_id) return toast("bad", "Pick a run first."); body.run_id = +e.run_id; }
    try { drawE1(await api("/api/v1/instructor/engines/e1", "POST", body)); pollFeed(); } catch (err) { toast("bad", err.message); }
  }
  function strip(rows) {
    const per = 80, size = 9, rowsN = Math.ceil(rows.length / per), el = svg("svg", { viewBox: `0 0 ${per * size + 4} ${rowsN * size + 4}`, class: "segstrip", role: "img", "aria-label": "Which segments the chosen policy put in the context window" });
    rows.forEach((r, i) => el.append(svg("rect", { x: 2 + (i % per) * size, y: 2 + Math.floor(i / per) * size, width: size - 1.5, height: size - 1.5, rx: 1.5,
      class: r.pinned ? "seg-pin" : r.selected ? "seg-sel" : r.eligible ? "seg-elig" : "seg-no" }, svg("title", {}, `${r.id}: ${r.tokens} tokens, relevance ${r.relevance}${r.selected ? ", selected" : r.eligible ? ", eligible, not selected" : ", not eligible in this stage"}${r.text ? "\n" + r.text : ""}`))));
    return el;
  }
  function drawE1(r) {
    const c = r.compare, row = (name, x) => x.skipped ? h("tr", {}, h("td", {}, name), h("td", { colspan: 7, class: "muted" }, x.skipped))
      : h("tr", { class: name.startsWith("Chosen") ? "chosen" : "" }, h("td", {}, name), h("td", {}, f(x.value, 3)), h("td", {}, x.of_optimal != null ? f(x.of_optimal * 100, 1) + "%" : "-"), h("td", {}, x.tokens_used), h("td", {}, x.n_selected),
        h("td", {}, x.dp_cells == null ? "-" : x.dp_cells.toLocaleString()), h("td", {}, x.gap_bound != null ? f(x.gap_bound, 3) : "-"), h("td", {}, f(x.ms, 2)));
    e1Out.replaceChildren(
      h("p", {}, `Stage ${r.stage}, budget ${r.budget} tokens, ${r.total_segments} segments, ${r.est_cells.toLocaleString()} estimated DP cells. The engine ran in `, h("b", {}, c.chosen.mode), " mode."),
      h("table", { class: "simtable" }, h("thead", {}, h("tr", {}, ["Policy", "Total relevance", "% of optimal", "Tokens used", "Segments", "DP cells", "Gap bound", "ms"].map((t) => h("th", {}, t)))),
        h("tbody", {}, row("Chosen (" + c.chosen.mode + ")", c.chosen), row("Exact DP", c.exact), row("Greedy (density)", c.greedy), row("Most recent first", c.recent))),
      h("p", { class: "muted small" }, "Greedy's gap bound is a proof: the optimum is at most this much higher. Most recent first is what a plain \"keep the newest\" rule would send."),
      strip(r.segments), h("p", { class: "muted small legend" }, h("i", { class: "sw seg-pin" }), "pinned ", h("i", { class: "sw seg-sel" }), "selected ", h("i", { class: "sw seg-elig" }), "eligible, left out ", h("i", { class: "sw seg-no" }), "not eligible in this stage",
        r.total_segments > r.segments.length ? ` (showing the last ${r.segments.length})` : ""));
  }

  // ---- E2 workbench
  const e2Form = box("simform");
  function drawE2Form() {
    const e = S.e2;
    e2Form.replaceChildren(
      h("div", { class: "simgrid" }, pick(e, "source", "Cohort", [["synthetic", "Synthetic cohort"], ["cohort", "My real cohort (first to latest run)"]], () => drawE2Form()),
        e.source === "synthetic" ? [field(e, "n", "Students", "number", { min: 1, max: 2000 }), field(e, "mean_pre", "Mean before (0-100)", "number", { min: 0, max: 100 }), field(e, "mean_post", "Mean after (0-100)", "number", { min: 0, max: 100 }),
          field(e, "spread", "Spread", "number", { min: 0, max: 50 })] : null,
        field(e, "B", "Bootstrap draws", "number", { min: 100, max: 10000, step: 100 }), field(e, "seed", "Random seed", "number", { min: 0 }), runPicker(e, "Process score from a real run (optional)")),
      h("div", { class: "simrow" }, h("button", { class: "primary", onclick: runE2 }, "Run E2")));
  }
  async function runE2() {
    const e = S.e2, body = { source: e.source, n: e.n, mean_pre: e.mean_pre, mean_post: e.mean_post, spread: e.spread, seed: e.seed, B: e.B };
    if (e.run_id) body.run_id = +e.run_id;
    try { drawE2(await api("/api/v1/instructor/engines/e2", "POST", body)); pollFeed(); } catch (err) { toast("bad", err.message); }
  }
  function histogram(gains) {
    const bins = Array(10).fill(0), w = 460, hh = 170, m = { l: 34, r: 10, t: 34, b: 30 };
    gains.forEach((g) => { bins[Math.min(9, Math.max(0, Math.floor((g + 1) * 5)))]++; });
    const top = Math.max(...bins, 1), bw = (w - m.l - m.r) / 10, el = svg("svg", { viewBox: `0 0 ${w} ${hh}`, class: "chart", role: "img", "aria-label": "Distribution of individual normalized gains" });
    el.append(svg("text", { x: m.l, y: 16, class: "ch-title" }, "Individual normalized gains (-1 to 1)"));
    bins.forEach((n, i) => { const bh = (n / top) * (hh - m.t - m.b); el.append(svg("rect", { x: m.l + i * bw + 2, y: hh - m.b - bh, width: bw - 4, height: bh, class: i >= 5 ? "c-ok" : "c-bad" }),
      svg("text", { x: m.l + i * bw + bw / 2, y: hh - m.b - bh - 3, class: "ch-tick", "text-anchor": "middle" }, n || ""), svg("text", { x: m.l + i * bw + bw / 2, y: hh - 14, class: "ch-tick", "text-anchor": "middle" }, f(-1 + i * 0.2 + 0.1, 1))); });
    return el;
  }
  function drawE2(r) {
    const s = r.summary, ci = s.ci95;
    const kids = [h("div", { class: "kpis" },
      h("div", { class: "kpi" }, h("small", {}, "Students"), h("b", {}, String(s.n_students))), h("div", { class: "kpi" }, h("small", {}, "Mean individual gain"), h("b", {}, f(s.mean_individual_gain, 3))),
      h("div", { class: "kpi" }, h("small", {}, "Class gain"), h("b", {}, f(s.class_gain, 3))), h("div", { class: "kpi" }, h("small", {}, "95% bootstrap interval"), h("b", {}, ci ? `${f(ci[0], 3)} to ${f(ci[1], 3)}` : "-")),
      h("div", { class: "kpi " + (s.effect_detected ? "good" : "bad") }, h("small", {}, "Effect detected"), h("b", {}, s.effect_detected == null ? "-" : s.effect_detected ? "Yes" : "No")))];
    if (r.note) kids.push(h("p", { class: "muted" }, r.note));
    if (s.warnings.length) kids.push(h("p", { class: "muted small" }, "Engine warnings: " + s.warnings.join(", ")));
    if (r.gains.length) kids.push(h("div", { class: "charts" }, histogram(r.gains)));
    if (r.process) {
      const p = r.process;
      let k = 0;
      const sat = p.events.map((key, i) => { if (GOOD.includes(key)) k++; return [i + 1, k ? p.saturating_curve[k - 1] : 0]; });
      kids.push(h("h4", {}, `Process score over ${p.events.length} behaviours (${p.good_events} count as good)`),
        h("div", { class: "charts" }, lineChart({ title: "Game's linear score vs the engine's saturating accumulator", xLabel: "behaviour number", yLabel: "score (0-100)", yMax: 100,
          series: [{ name: "game (linear, capped)", cls: "c-paper", points: p.linear.map((v, i) => [i + 1, Math.max(0, v)]) }, { name: "engine (saturating)", cls: "c-llm", points: sat }] })),
        h("p", { class: "muted small" }, `Saturating score ${f(p.saturating, 1)}. By stage: ` + Object.entries(p.by_stage).map(([st, v]) => `${st} ${f(v, 1)}`).join(" · ") + ". Each good behaviour closes 30% of the remaining distance to the full mark, so repeating one has diminishing returns."));
    }
    e2Out.replaceChildren(...kids);
  }

  // ---- benchmark
  async function runBench() {
    benchOut.replaceChildren(h("p", { class: "muted" }, "Measuring on this machine..."));
    try {
      const b = await api("/api/v1/instructor/engines/benchmark", "POST", {});
      const tbl = (head, rows) => h("table", { class: "simtable" }, h("thead", {}, h("tr", {}, head.map((t) => h("th", {}, t)))), h("tbody", {}, rows.map((r) => h("tr", {}, r.map((c) => h("td", {}, c))))));
      benchOut.replaceChildren(
        h("h4", {}, "E1 exact DP: time grows with the number of DP cells"), tbl(["Segments", "Budget", "DP cells", "ms", "ns per cell"], b.dp.map((d) => [d.n, d.budget, d.cells.toLocaleString(), f(d.ms, 1), f(d.ns_per_cell, 1)])),
        h("p", { class: "muted small" }, `ns per cell varies by a factor of ${b.ns_per_cell_ratio} across a 20x range of cells: the cost really is proportional to cells (the engine's assertion is at most 3).`),
        h("h4", {}, "E1 policy at scale"), h("p", {}, `${b.policy.n} segments, ${b.policy.budget.toLocaleString()} tokens: ${b.policy.est_cells.toLocaleString()} cells, so auto picks `, h("b", {}, b.policy.auto_mode), ` (${f(b.policy.greedy_ms, 2)} ms, gap bound ${f(b.policy.gap_bound, 3)}).`),
        h("h4", {}, "E2 bootstrap interval (10 students)"), tbl(["Draws", "ms"], b.bootstrap.map((x) => [x.B, f(x.ms, 2)])),
        h("h4", {}, "E2 saturating accumulator"), h("p", {}, `${b.accumulator.events.toLocaleString()} events in ${f(b.accumulator.ms, 1)} ms (${f(b.accumulator.us_per_event, 2)} microseconds per event).`));
      pollFeed();
    } catch (err) { benchOut.replaceChildren(); toast("bad", err.message); }
  }

  // ---- page
  (async () => {
    try { S.runs = (await api("/api/v1/instructor/engines/runs")).runs; } catch (_) { S.runs = []; }
    drawE1Form(); drawE2Form(); drawFeed();
    root.replaceChildren(
      h("h2", {}, "Algorithm engines"), h("p", { class: "muted" }, "The AlgoCom engines (E1 and E2) run inside this app: E1 chooses what the teammates remember, E2 measures learning. Everything below is computed by the real engine code."),
      h("h3", {}, "Live engine calls"), feedBox,
      h("h3", {}, "E1 workbench: context window chaining"), e1Form, e1Out,
      h("h3", {}, "E2 workbench: learning gain and process score"), e2Form, e2Out,
      h("h3", {}, "Benchmark"), h("div", { class: "simrow" }, h("button", { onclick: runBench }, "Measure the engines on this machine")), benchOut);
    pollFeed(); S.timer = setInterval(pollFeed, 1500);
  })();
  return root;
}
