// Front end: draws server state, sends commands. No game rules live here (scores, costs, results all come from the server).
const root = document.getElementById("root");
const nav = document.getElementById("nav");
const tabs = document.getElementById("tabs");
let csrf = "";
let me = null;
let seqCounter = 0;

const h = (tag, attrs = {}, ...kids) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));  // text nodes only
  return el;
};
const mount = (...nodes) => { tabs.replaceChildren(); root.replaceChildren(...nodes.filter(Boolean)); };
const SVG = "http://www.w3.org/2000/svg";
// cartoon teammate; the face changes with the message tone
function avatar(who, tone) {
  const svg = document.createElementNS(SVG, "svg"), use = document.createElementNS(SVG, "use");
  svg.setAttribute("class", "av av-" + who); svg.setAttribute("aria-hidden", "true");
  use.setAttribute("href", tone === "panicked" ? "#face-panic" : tone === "pushy" ? "#face-mad" : "#face");
  svg.append(use); return svg;
}

async function api(path, method = "GET", body) {
  const opt = { method, headers: { "Content-Type": "application/json" }, credentials: "same-origin" };
  if (csrf) opt.headers["X-CSRF-Token"] = csrf;
  if (body !== undefined) opt.body = JSON.stringify(body);
  const r = await fetch(path, opt);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(data.detail || data.code || r.statusText), { code: data.code, status: r.status });
  return data;
}

// ------------------------------------------------------------ auth
function authScreen() {
  nav.replaceChildren();
  const err = h("div", { class: "err", role: "alert" });
  const f = {};
  const field = (id, label, type = "text") => { f[id] = h("input", { id, type, autocomplete: type === "password" ? "current-password" : "off" }); return [h("label", { for: id }, label), f[id]]; };
  const role = h("select", { id: "role" }, h("option", { value: "student" }, "Student"), h("option", { value: "instructor" }, "Instructor"));
  const go = async (kind) => {
    err.textContent = "";
    try {
      if (kind === "register") {
        const body = { email: f.email.value, password: f.password.value, display_name: f.name.value || "Player", role: role.value };
        if (f.code.value) { if (role.value === "instructor") body.instructor_code = f.code.value; else body.cohort_code = f.code.value; }
        const r = await api("/api/v1/auth/register", "POST", body);
        if (r.join_code) alert("Your cohort join code: " + r.join_code);
      }
      const l = await api("/api/v1/auth/login", "POST", { email: f.email.value, password: f.password.value });
      csrf = l.csrf;
      await start();
    } catch (e) { err.textContent = e.message; }
  };
  mount(h("section", { class: "card narrow" }, h("h2", {}, "Log in or register"),
    ...field("email", "Email", "email"), ...field("password", "Password (10+ characters)", "password"),
    ...field("name", "Display name"), h("label", { for: "role" }, "Role"), role,
    ...field("code", "Cohort code (students) or instructor code"), err,
    h("div", { class: "row" }, h("button", { class: "primary", onclick: () => go("login") }, "Log in"), h("button", { onclick: () => go("register") }, "Register"))));
}

async function start() {
  me = await api("/api/v1/me");
  nav.replaceChildren(h("span", { class: "muted" }, me.display_name + " · " + me.role + " "), h("button", { onclick: logout }, "Log out"));
  if (me.role === "instructor") return instructorScreen();
  if (!me.consented) return consentScreen();
  return preTest();
}

async function logout() { try { await api("/api/v1/auth/logout", "POST", {}); } catch (_) {} csrf = ""; me = null; authScreen(); }

function consentScreen() {
  mount(h("section", { class: "card narrow" }, h("h2", {}, "Before you play"),
    h("p", {}, "This pilot logs your game actions and the dialogue you see so your instructor and the research team can study learning. Transcripts are kept only for the pilot period."),
    h("button", { class: "primary", onclick: async () => { await api("/api/v1/consent", "POST", {}); start(); } }, "I agree")));
}

async function questions(kind, next) {
  const { questions: qs } = await api("/api/v1/assessments/questions");
  const answers = {};
  const err = h("div", { class: "err", role: "alert" });
  mount(h("section", { class: "card narrow" }, h("h2", {}, kind === "pre" ? "Quick warm-up quiz" : "Quick final quiz"), h("p", { class: "lead" }, kind === "pre" ? "Five easy questions so we know where you start. No grades, and guessing is fine." : "The same kind of questions again, so we can see what you learned."),
    qs.map((q) => h("fieldset", {}, h("legend", {}, q.text), q.choices.map((c, i) => h("label", {}, h("input", { type: "radio", name: q.id, onchange: () => { answers[q.id] = i; } }), h("span", {}, c))))),
    err, h("div", { class: "row" }, h("button", { class: "primary", onclick: async () => {
      try { await api("/api/v1/assessments/" + kind, "POST", { answers }); next(); }
      catch (e) { if (e.code === "ALREADY_SUBMITTED") next(); else err.textContent = e.message; }
    } }, "Submit answers"), h("button", { onclick: next }, "Skip for now"))));
}
const preTest = () => questions("pre", newRun);

// ------------------------------------------------------------ game
const NAMES = { po: "Marlo (PO)", dev1: "Ines (Dev)", dev2: "Tobi (Dev)" };
const TUTORIALS = [{ id: "conditions", title: "Reading if / else" }, { id: "definition_of_done", title: "Definition of Done" }];
let run = null;      // {id, lastSeq, lastLine, state, lines[], wall[]}
let timers = [];

async function newRun() {
  const r = await api("/api/v1/runs", "POST", {});
  run = { id: r.id, lastSeq: 0, lastLine: 0, state: r.state, lines: [], wall: [], lastTick: performance.now(), busy: false };
  timers.forEach(clearInterval);
  timers = [setInterval(poll, 1000), setInterval(tick, 1000)];
  await poll();
}

async function poll() {
  if (!run || run.busy) return;
  try {
    const r = await api(`/api/v1/runs/${run.id}/state?since=${run.lastSeq}&since_line=${run.lastLine}`);
    run.lastSeq = r.seq; run.state = r.state;
    for (const l of r.lines) { run.lines.push(l); run.lastLine = l.id; }
    collect(r.events);
    render();
  } catch (e) { if (e.status === 401) authScreen(); }
}

async function tick() {
  if (!run || !run.state || run.state.status !== "active" || run.state.stage !== "BUILD") { run && (run.lastTick = performance.now()); return; }
  const now = performance.now(), ms = Math.round(now - run.lastTick);
  run.lastTick = now;
  try { await api(`/api/v1/runs/${run.id}/tick`, "POST", { real_ms: ms }); } catch (_) {}
}

function collect(events) {
  for (const e of events) {
    const t = e.type;
    if (["pushed", "push_blocked", "review_resolved", "rating_resolved", "attack_check_resolved", "warning_issued", "contradiction_detected", "card_escalated", "call_missed"].includes(t))
      run.wall.push(e);
  }
}

async function cmd(type, payload = {}) {
  run.busy = true;
  seqCounter = Math.max(seqCounter + 1, Date.now());
  try {
    const r = await api(`/api/v1/runs/${run.id}/commands`, "POST", { client_seq: seqCounter, type, payload });
    run.state = r.state; run.lastSeq = r.seq; collect(r.events);
    run.error = "";
  } catch (e) { run.error = e.message; }
  run.busy = false;
  await poll();
  if (run.state.status === "ended") return debrief();
}

function meters(s) {
  const m = s.meters;
  const box = (k, v, low, hint, icon, tone, pct) => {
    const bar = pct == null ? null : h("div", { class: "bar" }, h("i", {}));
    if (bar) bar.firstChild.style.width = Math.max(0, Math.min(100, pct)) + "%";
    return h("div", { class: `meter t-${tone}` + (low ? " low" : ""), title: hint }, h("span", { class: "lbl" }, icon + " " + k), h("b", {}, v), bar, h("span", { class: "hint" }, hint));
  };
  return h("div", { id: "meters" }, box("Points", m.points, false, "Your score. Spend it on upgrades.", "💰", "yellow"), box("Rating", Number(m.rating).toFixed(2), m.rating < 3, "How happy people are with you. Don't let it fall too low.", "⭐", "sky"),
    box("Cover", m.cover, m.cover >= 70, "How close you are to being found out. Keep it low.", "🕵", "lav", m.cover), box("Focus", Math.round(m.focus), m.focus < 30, "Your energy. Rest if it runs low.", "⚡", "mint", m.focus),
    box("Stage", s.stage + " · day " + s.day, false, "Where you are in the sprint.", "📅", "white"), box("Clock", s.clock_min + " min", false, "Time passed in the game.", "⏱", "white"), box("Warnings", s.warnings, false, "Too many and you get demoted.", "⚠", "coral"));
}

function pilePanel(s) {
  const moves = (c) => s.stage !== "BUILD" || c.state === "delegated" ? [] : [
    c.state !== "open" ? h("button", { title: "Start on this request yourself", onclick: () => cmd("open_card", { card_id: c.id }), disabled: !!s.open_card }, c.state === "returned" ? "Review" : "Work") : h("button", { title: "Put this down for now", onclick: () => cmd("hold") }, "Hold"),
    h("button", { title: "Hand this to a teammate", onclick: () => cmd("delegate", { card_id: c.id }) }, "Delegate"),
    c.type === "help_call" ? h("button", { title: "Help the teammate work it out", onclick: () => cmd("coach", { card_id: c.id }) }, "Coach") : null,
    h("button", { title: "Push this to later", onclick: () => cmd("defer", { card_id: c.id }) }, "Defer")];
  const live = s.pile.filter((c) => c.state !== "done");
  return h("section", { class: "card", id: "pile", "aria-label": "Pile" }, h("h2", {}, "📥 Pile (" + live.length + ")"), h("p", { class: "sub" }, "Everything your team is asking you for."),
    live.map((c) => h("div", { class: `pile-item esc${c.escalation}` + (c.state === "open" ? " open" : "") },
      h("b", {}, c.title || c.type.replace("_", " ")), h("div", { class: "tag" }, `${c.type} from ${NAMES[c.sender] || c.sender} · ${c.state}` + (c.deadline_min != null ? ` · due ${c.deadline_min} min` : " · escalated")),
      h("div", { class: "tag" }, ["escalation: " + ["message", "call", "meeting"][c.escalation], c.payoff.points ? ` · +${c.payoff.points} pts` : "", c.penalty.cover ? ` · +${c.penalty.cover} cover if ignored` : ""].join("")),
      h("div", { class: "row" }, moves(c)))));
}

function codeDesk(s) {
  const w = s.work;
  if (s.stage === "STANDUP" && s.standup) {
    const q = s.standup;
    return h("section", { class: "card", "aria-label": "Standup" }, h("h2", {}, "Standup: " + NAMES[q.teammate]),
      h("p", {}, "How did your last push go?"), h("div", { class: "row" }, q.choices.map((c) => h("button", { onclick: () => cmd("reply_standup", { answer: c }) }, c[0].toUpperCase() + c.slice(1)))),
      h("p", { class: "muted" }, "An accurate answer is only offered once you have unlocked the concept in LearnLoop."));
  }
  if (s.stage === "STANDUP") return h("section", { class: "card" }, h("h2", {}, "Standup done"), h("button", { class: "primary", onclick: () => cmd("advance_stage", { to: "BUILD" }) }, "Start building"));
  if (s.stage === "PLANNING") return h("section", { class: "card" }, h("h2", {}, "Planning"), h("p", {}, "Look at the Pile, then start the sprint."), h("button", { class: "primary", onclick: () => cmd("advance_stage", { to: "STANDUP" }) }, "Go to standup"));
  if (s.stage === "BUILD" && !w) {
    const next = s.day >= 2 ? ["REVIEW", "End sprint (Review)"] : ["STANDUP", "End day 1 (next standup)"];
    return h("section", { class: "card" }, h("h2", {}, "💻 Fix-it desk"), h("p", { class: "muted" }, s.open_card ? "This card has no code. Send your reply." : "Open a card from the Pile."),
      s.open_card ? h("button", { onclick: () => cmd("push") }, "Send reply") : null,
      h("div", { class: "row" }, h("button", { onclick: () => cmd("advance_stage", { to: next[0] }), disabled: !!s.open_card }, next[1])));
  }
  if (!w) return h("section", { class: "card" }, h("h2", {}, "CodeDesk"));
  const lastRun = run.runs;
  const perks = s.perks.includes("ai_assistant");
  return h("section", { class: "card", "aria-label": "CodeDesk" }, h("h2", {}, "💻 " + w.title), h("p", {}, w.doc),
    h("pre", { class: "code" }, w.lines.map((t, i) => h("div", { class: "line" + (w.flagged === i + 1 ? " flagged" : ""), role: w.kind === "fix" ? "button" : null, tabindex: w.kind === "fix" ? "0" : null,
      onclick: () => w.kind === "fix" && cmd("flag_line", { line_no: i + 1 }), onkeydown: (e) => { if (e.key === "Enter" && w.kind === "fix") cmd("flag_line", { line_no: i + 1 }); } }, h("span", { class: "n" }, i + 1), t))),
    h("p", { class: "muted" }, w.kind === "fix" ? "Step 1: click the line you think is wrong. Step 2: pick the replacement below. Step 3: run the script to check." : "Fill the blank line from the tray."),
    w.options.map((o) => h("button", { class: "opt" + (w.selected === o.id ? " sel" : "") + (w.assistant === o.id ? " hint" : ""), onclick: () => cmd("select_patch", { option_id: o.id }) }, o.text.trim())),
    w.assistant ? h("p", { class: "muted" }, "AI Assistant suggests the highlighted option (it can be wrong).") : null,
    h("div", { class: "row" }, h("button", { title: "Test your fix and see if it works", onclick: runScript }, "▶ Run Script"), perks ? h("button", { onclick: () => cmd("use_assistant") }, "AI Assistant") : null),
    lastRun ? h("div", {}, lastRun.map((r) => h("div", { class: "run " + (r.pass ? "pass" : "fail") }, r.text))) : null,
    h("h3", {}, "Checklist: is it really done?"),
    ["tests", "matches_doc", "no_security"].map((b) => h("label", { class: "check" }, h("input", { type: "checkbox", checked: w.dod[b], onchange: () => cmd("toggle_dod", { box: b }) }), h("span", {}, { tests: "Tests pass", matches_doc: "Matches the doc", no_security: "No security concern" }[b]))),
    h("div", { class: "row" }, h("button", { class: "primary", title: "Send your fix live to the customers", onclick: () => cmd("push"), disabled: !w.selected }, "🚀 Push (send it live)"), h("button", { onclick: () => cmd("hold") }, "Hold")));
}

async function runScript() {
  await cmd("run_script");
  const r = await api(`/api/v1/runs/${run.id}/state?since=${run.lastSeq - 1}`);
  const ev = r.events.filter((e) => e.type === "script_run").pop();
  run.runs = ev ? ev.runs : null;
  render();
}

function chatPanel(s) {
  const call = s.call ? h("div", { class: "card call" }, h("b", {}, "☎ Call from " + (NAMES[s.call.sender] || s.call.sender)), h("p", { class: "muted" }, "Answer it (15 min) or ignore it."), h("button", { onclick: () => cmd("answer_call") }, "Answer")) : null;
  return h("section", { class: "card", id: "chat", "aria-label": "TeamChat" }, h("h2", {}, "💬 Team chat"), h("p", { class: "sub" }, "What your team is saying."), call,
    h("div", { class: "chat" }, run.lines.slice(-12).map((l) => h("div", { class: "msg " + l.tone }, avatar(l.speaker, l.tone), h("div", { class: "bub" }, h("b", {}, NAMES[l.speaker] || l.speaker), h("div", {}, l.text))))));
}

function starWall() {
  const text = (e) => ({
    pushed: `Pushed ${e.ticket}: ${e.label} (${e.points >= 0 ? "+" : ""}${e.points} pts)`, push_blocked: `Push blocked: runtime error (${e.points} pts)`,
    review_resolved: "Reviews are in.", rating_resolved: `Rating moved ${e.delta >= 0 ? "+" : ""}${e.delta}`,
    attack_check_resolved: `Security attack on ${e.ticket}: ${e.rating} rating, ${e.points} points`, warning_issued: `Demotion warning ${e.warnings}`,
    contradiction_detected: "A teammate caught your earlier answer contradicting the result: +" + e.cover + " Cover", card_escalated: `Card ${e.card_id} escalated to ${["message", "call", "meeting"][e.level]}`, call_missed: "Missed call " + e.misses,
  }[e.type]);
  return h("section", { class: "card", id: "wall", "aria-label": "StarWall" }, h("h2", {}, "⭐ What just happened"), h("div", { class: "chat" }, run.wall.slice(-10).reverse().map((e) => h("div", { class: "msg plain" }, h("div", { class: "bub" }, "⭐ " + text(e))))));
}

function learnLoop(s) {
  return h("section", { class: "card", id: "learn", "aria-label": "LearnLoop" }, h("h2", {}, "📺 Learn & upgrade"), h("p", { class: "sub" }, "Watch short videos to learn, or buy a helper."),
    TUTORIALS.map((t) => h("div", { class: "row" }, h("span", {}, s.unlocked.includes(t.id) ? "✔ " + t.title : "??? " + t.title), h("button", { onclick: () => cmd("watch_tutorial", { tutorial_id: t.id }), disabled: s.unlocked.includes(t.id) }, "Watch (30 min)"))),
    h("h3", {}, "Toolbox"), h("button", { onclick: () => cmd("buy_perk", { perk_id: "ai_assistant" }), disabled: s.perks.includes("ai_assistant") }, s.perks.includes("ai_assistant") ? "AI Assistant owned" : "Buy AI Assistant (150 pts)"));
}

function render() {
  if (!run || !run.state) return;
  const s = run.state;
  const sig = JSON.stringify({ ...s, clock_min: 0, day_used_min: 0 }) + run.lines.length + run.wall.length + JSON.stringify(run.runs || null) + (run.error || "");
  if (sig === run.sig && document.getElementById("meters")) { document.getElementById("meters").replaceWith(meters(s)); return; }  // keep buttons stable between polls
  run.sig = sig;
  const live = s.pile.filter((c) => c.state !== "done").length;
  const go = (id) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  const tab = (id, label, badge) => h("button", { class: "tab", onclick: () => go(id) }, label, badge ? h("span", { class: "badge" }, badge) : null);
  mount(meters(s), run.error ? h("div", { class: "err", role: "alert" }, run.error) : null,
    h("div", { id: "game" }, pilePanel(s), h("div", { id: "desk" }, codeDesk(s)), h("div", {}, chatPanel(s), h("div", { style: null }, starWall()), learnLoop(s))));
  tabs.replaceChildren(tab("pile", "📥 Pile", live), tab("desk", "💻 Fix-it desk"), tab("chat", "💬 Team chat"), tab("wall", "⭐ What happened"), tab("learn", "📺 Learn & upgrade"));
}

async function debrief() {
  timers.forEach(clearInterval);
  const d = await api(`/api/v1/runs/${run.id}/debrief`);
  const names = { win: "You survived the sprint", lose_rating: "Fired: Rating fell below 2.0", lose_cover: "Exposed: Cover hit 100", lose_warnings: "Demoted twice" };
  mount(h("section", { class: "card narrow" }, h("h2", {}, names[d.ending] || d.ending),
    h("table", {}, [["Rating", Number(d.rating).toFixed(2)], ["Cover", d.cover], ["Points", d.points], ["Process score", d.process_score], ["Gap (rating % minus process)", d.gap]].map(([k, v]) => h("tr", {}, h("th", {}, k), h("td", {}, v)))),
    h("p", { class: "muted" }, "Points never count toward your process score: honest process does."),
    h("div", { class: "row" }, h("button", { class: "primary", onclick: () => questions("post", () => mount(h("section", { class: "card narrow" }, h("h2", {}, "Thanks for playing")))) }, "Take the post-test"), h("button", { onclick: newRun }, "Play again"))));
}

// ------------------------------------------------------------ instructor
async function instructorScreen() {
  const list = h("div", {});
  mount(h("section", { class: "card" }, h("h2", {}, "Your cohort"), list));
  try {
    const r = await api(`/api/v1/instructor/cohorts/${me.cohort_id}/runs`);
    list.replaceChildren(h("table", {}, h("tr", {}, ["Student", "Status", "Ending", "Process", "Gain", ""].map((x) => h("th", {}, x))),
      r.runs.map((x) => h("tr", {}, h("td", {}, x.student), h("td", {}, x.status), h("td", {}, x.ending || ""), h("td", {}, x.process_score), h("td", {}, x.gain == null ? "" : x.gain.toFixed(2)),
        h("td", {}, h("button", { onclick: () => transcript(x.run_id) }, "Transcript"))))));
  } catch (e) { list.replaceChildren(h("div", { class: "err" }, e.message)); }
}

async function transcript(id) {
  const t = await api(`/api/v1/instructor/runs/${id}/transcript`);
  mount(h("section", { class: "card" }, h("button", { onclick: instructorScreen }, "Back"), h("h2", {}, "Transcript: " + t.student),
    h("h3", {}, "Dialogue"), t.lines.map((l) => h("div", { class: "msg" }, h("b", {}, l.speaker + " [" + l.source + ", " + l.latency_ms + " ms]: "), l.text)),
    h("h3", {}, "Events"), h("pre", { class: "code" }, t.events.map((e) => JSON.stringify(e)).join("\n"))));
}

authScreen();
