import { runWelcome } from "/welcome.js";
// Front end: draws server state, sends commands. No game rules live here (scores, costs, results all come from the server).
const root = document.getElementById("root");
const nav = document.getElementById("nav");
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
const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
let lastPt = null;   // where the player last pressed, so confetti pops from the button they hit
document.addEventListener("pointerdown", (e) => { lastPt = { x: e.clientX, y: e.clientY }; }, true);
const fx = h("div", { id: "fx", "aria-hidden": "true" });
const toasts = h("div", { id: "toasts", role: "status", "aria-live": "polite" });
document.body.append(fx, toasts);

function playEnter() { if (REDUCED) return; root.classList.add("enter"); setTimeout(() => root.classList.remove("enter"), 1200); }
// a screen change animates in; refreshes of the game screen do not (no replaying on every poll)
const mount = (...nodes) => {
  const wasGame = !!document.getElementById("browser");
  root.replaceChildren(...nodes.filter(Boolean));
  if (!(wasGame && document.getElementById("browser"))) playEnter();
};

function toast(kind, msg) {
  const t = h("div", { class: "toast " + kind }, h("span", { class: "ti" }, ic({ good: "check", bad: "cross", warn: "warn", info: "star" }[kind])), h("span", {}, msg));
  toasts.append(t);
  while (toasts.children.length > 3) toasts.firstChild.remove();
  setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 300); }, 3400);
}

function burst(n = 22) {
  if (REDUCED) return;
  const o = lastPt || { x: innerWidth / 2, y: innerHeight / 3 };
  for (let i = 0; i < n; i++) {
    const p = h("i", { class: "conf c" + (i % 5) });
    const a = Math.random() * Math.PI * 2, d = 60 + Math.random() * 120;
    p.style.left = o.x + "px"; p.style.top = o.y + "px";
    p.style.setProperty("--dx", Math.cos(a) * d + "px"); p.style.setProperty("--dy", Math.sin(a) * d - 60 + "px"); p.style.setProperty("--r", Math.random() * 720 - 360 + "deg");
    p.addEventListener("animationend", () => p.remove());
    fx.append(p);
  }
}

function shakeScreen() {
  if (REDUCED) return;
  root.classList.remove("shake"); void root.offsetWidth; root.classList.add("shake");
  setTimeout(() => root.classList.remove("shake"), 500);
}

function tween(el, from, to, fmt) {
  el.textContent = fmt(from);
  const t0 = performance.now();
  const step = (t) => { const p = Math.min(1, (t - t0) / 450); el.textContent = fmt(from + (to - from) * (1 - Math.pow(1 - p, 3))); if (p < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
}
const SVG = "http://www.w3.org/2000/svg";
// Game art lives in /icons.svg: custom icons (i-*) and the cast (c-*). Never emoji.
function ic(name, cls = "") {
  const svg = document.createElementNS(SVG, "svg"), use = document.createElementNS(SVG, "use");
  svg.setAttribute("class", "ic" + (cls ? " " + cls : "")); svg.setAttribute("aria-hidden", "true");
  use.setAttribute("href", "/icons.svg#" + (name.startsWith("c-") ? name : "i-" + name));
  svg.append(use); return svg;
}
// Each teammate has their own look; the face changes with the tone of the message (calm, pushy, panicked).
const CAST = { po: "marlo", dev1: "ines", dev2: "tobi" };
function avatar(who, tone) {
  const name = CAST[who] || "heron", svg = ic("c-" + name + (name === "heron" ? "" : tone === "panicked" ? "-panic" : tone === "pushy" ? "-mad" : ""));
  svg.setAttribute("class", "av av-" + name);
  return svg;
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
  const role = h("select", { id: "role", onchange: () => { codeBox.hidden = role.value !== "instructor"; } }, h("option", { value: "student" }, "Student"), h("option", { value: "instructor" }, "Instructor"));
  const codeBox = h("div", { hidden: true }, ...field("code", "Instructor code"));   // only instructors need a code
  const go = async (kind) => {
    err.textContent = "";
    try {
      if (kind === "register") {
        const body = { email: f.email.value, password: f.password.value, display_name: f.name.value || "Player", role: role.value };
        if (role.value === "instructor" && f.code.value) body.instructor_code = f.code.value;
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
    codeBox, err,
    h("div", { class: "row" }, h("button", { class: "primary", onclick: () => go("login") }, "Log in"), h("button", { onclick: () => go("register") }, "Register"))));
}

async function start() {
  me = await api("/api/v1/me");
  nav.replaceChildren(h("span", { class: "muted" }, me.display_name + " · " + me.role + " "), h("button", { onclick: logout }, "Log out"));
  if (me.role === "instructor") return instructorScreen();
  if (!welcomed()) return runWelcome({ h, ic, mount, onDone: () => { markWelcomed(); afterWelcome(); } });   // right after sign-up, once per player
  return afterWelcome();
}
const afterWelcome = () => (me.consented ? preTest() : consentScreen());
const welcomeKey = () => "welcomed:" + me.id;
const welcomed = () => { try { return localStorage.getItem(welcomeKey()) === "1"; } catch (_) { return false; } };   // storage can be blocked: then the intro just shows again
const markWelcomed = () => { try { localStorage.setItem(welcomeKey(), "1"); } catch (_) { /* storage can be blocked */ } };

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
  const done = h("span", {}, "0 of " + qs.length + " answered"), fill = h("i", {});
  fill.style.width = "0%";
  const progress = () => { const n = Object.keys(answers).length; done.textContent = n + " of " + qs.length + " answered"; fill.style.width = (100 * n / qs.length) + "%"; };
  mount(h("section", { class: "card narrow" }, h("h2", {}, kind === "pre" ? "Quick warm-up quiz" : "Quick final quiz"), h("p", { class: "lead" }, kind === "pre" ? "Five easy questions so we know where you start. No grades, and guessing is fine." : "The same kind of questions again, so we can see what you learned."),
    h("div", { class: "bar quiz" }, fill), h("div", { class: "muted" }, done),
    qs.map((q) => h("fieldset", {}, h("legend", {}, q.text), q.choices.map((c, i) => h("label", {}, h("input", { type: "radio", name: q.id, onchange: () => { answers[q.id] = i; progress(); } }), h("span", {}, c))))),
    err, h("div", { class: "row" }, h("button", { class: "primary", onclick: async () => {
      try { await api("/api/v1/assessments/" + kind, "POST", { answers }); next(); }
      catch (e) { if (e.code === "ALREADY_SUBMITTED") next(); else err.textContent = e.message; }
    } }, "Submit answers"), h("button", { onclick: next }, "Skip for now"))));
}
const preTest = () => questions("pre", setupRun);

// Experimental: a run can use a class challenge code (everyone gets the same sprints) and, after a first win, Heat.
const HEAT_TEXT = { no_assistant: "No AI Assistant", one_warning: "One warning ends the run", short_days: "Shorter working days",
  po_pressure: "Marlo wants extra status updates", harsh_reviews: "Reviewers go viral more often" };
async function setupRun() {
  let un = { unlocks: [], heat: [] };
  try { un = await api("/api/v1/me/unlocks"); } catch (_) { return newRun(); }
  const code = h("input", { id: "challenge", inputmode: "numeric", placeholder: "Leave empty for a random run", autocomplete: "off" });
  const picked = new Set();
  const err = h("div", { class: "err", role: "alert" });
  mount(h("section", { class: "card narrow" }, h("h2", {}, ic("flag"), " New run"),
    h("p", { class: "lead" }, "Three sprints. Every run deals different tickets, and the last sprint is a boss."),
    h("label", { for: "challenge" }, "Class challenge code (optional)"), code,
    h("p", { class: "muted" }, "Everyone who types the same code gets the same sprints, so you can compare choices in class."),
    un.heat.length ? h("fieldset", {}, h("legend", {}, "Heat: make it harder for a bigger run score"),
      un.heat.map((k) => h("label", { class: "check" }, h("input", { type: "checkbox", onchange: (e) => { e.target.checked ? picked.add(k) : picked.delete(k); } }), h("span", {}, HEAT_TEXT[k] || k))))
      : h("p", { class: "muted" }, ic("lock"), " Win a run to unlock Heat modifiers."),
    un.unlocks.length ? h("p", { class: "muted" }, "Unlocked from earlier runs: " + un.unlocks.filter((u) => u !== "heat").map(practiceName).join(", ")) : null,
    err, h("div", { class: "row" }, h("button", { class: "primary", onclick: () => {
      const v = code.value.trim();
      if (v && !/^[0-9]{1,6}$/.test(v)) { err.textContent = "A challenge code is a number up to 6 digits."; return; }
      newRun({ ...(v ? { challenge: Number(v) } : {}), heat: [...picked] }).catch((e) => { err.textContent = e.message; });
    } }, "Start the run"))));
}

// ------------------------------------------------------------ game
const NAMES = { po: "Marlo (PO)", dev1: "Ines (Dev)", dev2: "Tobi (Dev)" };
const TUTORIALS = [{ id: "conditions", title: "Reading if / else" }, { id: "definition_of_done", title: "Definition of Done" }];
let run = null;      // {id, lastSeq, lastLine, state, lines[], wall[]}
let timers = [];

async function newRun(opts = {}) {
  const r = await api("/api/v1/runs", "POST", opts);
  run = { id: r.id, lastSeq: 0, lastLine: 0, state: r.state, lines: [], wall: [], lastTick: performance.now(), busy: false, notes: [] };
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

// experimental mechanics: what each new event says when it happens
const XTOAST = {
  practice_gained: (e) => ["good", (e.duo ? "Combo unlocked: " : "New practice: ") + practiceName(e.practice)],
  practice_evolved: (e) => ["good", practiceName(e.practice) + " levelled up"],
  practice_unlocked: (e) => ["info", practiceName(e.practice) + " can now appear in the shop"],
  spot_check: () => ["warn", "Spot check! Marlo is checking your work"],
  last_stand: () => ["bad", "Last stand: one more slip and you're found out. A clean, honest push pulls you back."],
  clutch: (e) => ["good", "Clutch! Cover " + e.cover],
  director: (e) => e.action === "relief" ? ["info", "Marlo gives everyone " + e.minutes + " more minutes"] : ["warn", "Things are quiet. New work arrives"],
  bounty_paid: (e) => ["good", "Bounty paid: +" + e.points + " pts"],
  interest_paid: (e) => ["good", "Interest on saved points: +" + e.points],
  comeback_offered: () => ["info", "Comeback: extra Focus and a bounty ticket this sprint"],
  ultimate_used: (e) => ["good", ULTIMATES[e.kind] ? ULTIMATES[e.kind].name + "!" : "Ultimate used"],
  style_ranked: (e) => ["info", "Sprint style rank: " + e.rank],
  achievement: () => ["good", "Achievement: a whole sprint with no bluffing"],
  card_reset: () => ["good", "Retrospective: card calmed down"],
  focus_switch: (e) => ["warn", "Switching tasks: Focus " + e.focus],
  sprint_goal: (e) => e.met ? ["good", `Sprint goal met: ${e.shipped} of ${e.target} shipped (+${e.points} pts)`]
    : ["bad", `Sprint goal missed: ${e.shipped} of ${e.target} shipped. Demotion warning and +${e.cover} Cover`],
  sprint_dealt: (e) => ["info", e.boss ? "Boss sprint: " + (BOSSES[e.boss] || {}).name : "Sprint " + e.sprint + " dealt"],
};

function collect(events) {
  for (const e of events) {
    const t = e.type;
    if (XTOAST[t]) { const [k, m] = XTOAST[t](e); toast(k, m); if (t === "clutch" || t === "practice_gained") burst(); if (t === "last_stand") shakeScreen(); }
    if (["pushed", "push_blocked", "review_resolved", "rating_resolved", "attack_check_resolved", "warning_issued", "contradiction_detected", "card_escalated", "call_missed"].includes(t)) {
      run.wall.push(e); react(e);
    }
  }
}

const wallText = (e) => ({
  pushed: `Pushed ${e.ticket}: ${e.label} (${e.points >= 0 ? "+" : ""}${e.points} pts)`, push_blocked: `Push blocked: runtime error (${e.points} pts)`,
  review_resolved: "Reviews are in.", rating_resolved: `Rating moved ${e.delta >= 0 ? "+" : ""}${e.delta}`,
  attack_check_resolved: `Security attack on ${e.ticket}: ${e.rating} rating, ${e.points} points`, warning_issued: `Demotion warning ${e.warnings}`,
  contradiction_detected: "A teammate caught your earlier answer contradicting the result: +" + e.cover + " Cover", card_escalated: `Card ${e.card_id} escalated to ${["message", "call", "meeting"][e.level]}`, call_missed: "Missed call " + e.misses,
}[e.type]);

function react(e) {
  const t = e.type;
  if (t === "pushed") { if (e.points > 0) { toast("good", wallText(e)); burst(); } else toast("bad", wallText(e)); }
  else if (t === "push_blocked" || t === "warning_issued") { toast("bad", wallText(e)); shakeScreen(); }
  else if (t === "attack_check_resolved" || t === "call_missed") toast("bad", wallText(e));
  else if (t === "contradiction_detected" || t === "card_escalated") toast("warn", wallText(e));
  else if (t === "rating_resolved") toast(e.delta >= 0 ? "good" : "bad", wallText(e));
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
  const el = buildMeters(s), m = s.meters;
  const now = { Points: m.points, Rating: Number(m.rating), Cover: m.cover, Focus: Math.round(m.focus) };
  const prev = run.lastM;
  run.lastM = now;
  if (!prev || REDUCED) return el;
  const fmt = { Points: (n) => String(Math.round(n)), Rating: (n) => n.toFixed(2), Cover: (n) => String(Math.round(n)), Focus: (n) => String(Math.round(n)) };
  for (const k of Object.keys(now)) {
    const a = prev[k], b = now[k];
    if (a === b) continue;
    const good = k === "Cover" ? b < a : b > a;
    const tile = el.querySelector(`[data-k="${k}"]`);
    if (!tile) continue;
    const chip = h("span", { class: "delta " + (good ? "good" : "bad") }, (b > a ? "+" : "−") + fmt[k](Math.abs(b - a)));
    tile.classList.add(good ? "gain" : "loss");
    tile.append(chip);
    chip.addEventListener("animationend", () => chip.remove());
    tween(tile.querySelector("b"), a, b, fmt[k]);
  }
  return el;
}

function buildMeters(s) {
  const m = s.meters;
  const box = (k, v, low, hint, icon, tone, pct) => {
    const bar = pct == null ? null : h("div", { class: "bar" }, h("i", {}));
    if (bar) bar.firstChild.style.width = Math.max(0, Math.min(100, pct)) + "%";
    return h("div", { class: `meter t-${tone}` + (low ? " low" : ""), title: k + ": " + hint, "data-k": k },
      h("span", { class: "lbl", "aria-hidden": "true" }, ic(icon)), h("span", { class: "vh" }, k), h("b", {}, v), bar);
  };
  const stage = s.stage[0] + s.stage.slice(1).toLowerCase();
  return h("div", { id: "meters", role: "group", "aria-label": "Your status" },
    box("Rating", Number(m.rating).toFixed(2), m.rating < 3, "How happy people are with you. Don't let it fall too low.", "star", "sky"), box("Points", m.points, false, "Your score. Spend it on upgrades.", "coin", "yellow"),
    box("Cover", m.cover, m.cover >= 70, "How close you are to being found out. Keep it low.", "search", "lav", m.cover), box("Focus", Math.round(m.focus), m.focus < 30, "Your energy. Rest if it runs low.", "bolt", "mint", m.focus),
    box("Warnings", s.warnings, false, "Too many and you get demoted.", "warn", "coral"),
    box("Stage", stage + " · day " + s.day, false, "Where you are in the sprint.", "calendar", "white"), box("Clock", s.clock_min + " min", false, "Time passed in the game.", "clock", "white"));
}

const STAGE_FLOW = [["PLANNING", "Plan"], ["STANDUP", "Standup"], ["BUILD", "Build"], ["REVIEW", "Review"]];
// The fake apps. Each game feature lives in one of them. Rename here to rebrand.
const APPS = [
  { id: "slack", name: "Slackish", icon: "chat", tag: "Team chat", url: "slackish.fake/scrumcorp/team-chat" },
  { id: "github", name: "GitHab", icon: "branch", tag: "Issues and code", url: "githab.fake/scrumcorp/app/issues" },
  { id: "play", name: "Play Storey", icon: "store", tag: "Apps and reviews", url: "playstorey.fake/store/apps/scrumcorp" },
  { id: "youtube", name: "ToobYou", icon: "tv", tag: "Learn something", url: "toobyou.fake/learn" },
  { id: "shop", name: "Amazin'", icon: "cart", tag: "Upgrades", url: "amazin.fake/upgrades" },
];
const appName = (id) => APPS.find((a) => a.id === id).name;

function coachHint(s) {
  if (s.stage === "PLANNING") return s.x && s.x.shop ? (s.x.shop.free ? "Pick a starting practice, then start the sprint." : "Spend points on practices, then start the next sprint.") : `Peek at your open issues in ${appName("github")}, then start the sprint.`;
  if (s.stage === "STANDUP") return `Standup time! Answer your teammate in ${appName("slack")}.`;
  if (s.stage === "BUILD") return s.open_card ? `Fix it in ${appName("github")}: click the wrong line, pick a replacement, run the script, then push.` : `Open an issue in ${appName("github")} and press Work.`;
  return "Sprint review. Let's see how you did!";
}
function steps(s) {
  const at = STAGE_FLOW.findIndex(([k]) => k === s.stage);
  return h("div", { class: "steps", "aria-label": "Sprint steps" }, STAGE_FLOW.map(([, label], i) => h("span", { class: "step " + (i < at ? "done" : i === at ? "now" : "") }, i < at ? [ic("check"), " ", label] : label)));
}

const typeIcon = (t) => { t = String(t); return t.includes("fix") ? "bug" : t.includes("help") ? "sos" : t.includes("build") ? "hammer" : t.includes("problem") ? "alert" : t.includes("status") ? "megaphone" : "pin"; };

function pilePanel(s) {
  const moves = (c) => s.stage !== "BUILD" || c.state === "delegated" ? [] : [
    c.state !== "open" ? h("button", { title: "Start on this request yourself", onclick: () => cmd("open_card", { card_id: c.id }), disabled: !!s.open_card }, c.state === "returned" ? "Review" : "Work") : h("button", { title: "Put this down for now", onclick: () => cmd("hold") }, "Hold"),
    h("button", { title: "Hand this to a teammate", onclick: () => cmd("delegate", { card_id: c.id }) }, "Delegate"),
    c.type === "help_call" ? h("button", { title: "Help the teammate work it out", onclick: () => cmd("coach", { card_id: c.id }) }, "Coach") : null,
    h("button", { title: "Push this to later", onclick: () => cmd("defer", { card_id: c.id }) }, "Defer")];
  const live = s.pile.filter((c) => c.state !== "done");
  return h("section", { class: "card", id: "pile", "aria-label": "Pile" }, h("h2", {}, ic("clipboard"), " Issues (" + live.length + ")"), h("p", { class: "sub" }, "Your Pile: everything your team is asking you for."),
    live.map((c) => h("div", { class: `pile-item esc${c.escalation}` + (c.state === "open" ? " open" : "") + (c.bounty ? " bounty" : "") + (c.spot ? " spot" : "") },
      h("b", {}, ic(typeIcon(c.type)), " " + (c.spot ? "Spot check: " : "") + (c.title || c.type.replace("_", " "))),
      c.bounty ? h("span", { class: "chip good" }, "Bounty: extra points for a clean push") : null,
      h("div", { class: "tag" }, `${c.type} from ${NAMES[c.sender] || c.sender} · ${c.state}` + (c.deadline_min != null ? ` · due ${c.deadline_min} min` : " · escalated")),
      h("div", { class: "tag" }, ["escalation: " + ["message", "call", "meeting"][c.escalation], c.payoff.points ? ` · +${c.payoff.points} pts` : "", c.penalty.cover ? ` · +${c.penalty.cover} cover if ignored` : ""].join("")),
      s.x ? priceTag(s, c) : null,
      h("div", { class: "row" }, moves(c),
        s.x && s.x.retro_left > 0 && c.escalation > 0 && s.stage === "BUILD" ? h("button", { title: "Retrospective: calm this card back down", onclick: () => cmd("retro", { card_id: c.id }) }, "Retro") : null))));
}

// M1/M2: what a move costs right now, and which other cards would slip while you do it
function priceTag(s, c) {
  const x = s.x, cost = x.move_costs;
  const slip = (mins) => s.pile.filter((o) => o.id !== c.id && o.state !== "done" && o.state !== "delegated" && o.deadline_min != null && o.deadline_min <= s.clock_min + mins).length;
  const work = c.ticket ? cost.read : cost.open_other;
  const out = [];
  if (s.stage === "BUILD" && c.state !== "open" && c.state !== "delegated") {
    const n = slip(work);
    out.push(h("div", { class: "cost" + (n ? " risk" : "") }, `Work: ${work} min` + (n ? ` · ${n} other card${n > 1 ? "s" : ""} will escalate meanwhile` : "") + ` · Delegate: ${cost.delegate} min · Defer: ${cost.defer} min` + (x.focus_switch_cost && c.state !== "open" ? ` · switching costs ${x.focus_switch_cost} Focus` : "")));
  }
  if (c.ticket && (c.state === "returned" || c.state === "delegated")) {
    const pct = Math.round(100 * x.bug_odds);
    out.push(h("div", { class: "odds" }, ic("bug"), c.bug_known === undefined ? ` About ${pct}% of delegated tickets come back with a hidden bug. Only reading the code tells you for sure.`
      : c.bug_known ? " TDD Pair: this one has a bug." : " TDD Pair: this one is clean."));
  }
  if (c.ticket && c.state === "delegated") out.push(h("div", { class: "tag" }, "If you end the sprint before it comes back, it ships unreviewed."));
  return out;
}

function codeDesk(s) {
  const w = s.work;
  if (s.stage === "STANDUP" && s.standup) {
    const q = s.standup;
    const pr = s.x && s.x.prices, cov = (n) => (n > 0 ? "+" : "") + n + " Cover";
    const say = { accurate: pr && `${cov(pr.standup.accurate)} now, but ${cov(pr.contradiction_cover)} later if that ticket turns out buggy`,
      vague: pr && `${cov(pr.standup.vague * pr.vague_multiplier)}. A bluff`, wrong: pr && `${cov(pr.standup.wrong)}. A bluff` };
    const timer = s.x && s.x.standup_timer_s ? standupTimer(q, s.x.standup_timer_s) : null;
    return h("section", { class: "card", "aria-label": "Standup" }, h("h2", {}, "Standup: " + NAMES[q.teammate]),
      h("p", {}, "How did your last push go?"), timer,
      h("div", { class: "row" }, q.choices.map((c) => h("button", { class: pr ? "deal" : "", onclick: () => cmd("reply_standup", { answer: c }) }, c[0].toUpperCase() + c.slice(1), pr ? h("small", {}, say[c]) : null))),
      h("p", { class: "muted" }, "An accurate answer is only offered once you have unlocked the concept in ToobYou."));
  }
  if (s.stage === "STANDUP") return h("section", { class: "card" }, h("h2", {}, "Standup done"), h("button", { class: "primary", onclick: () => cmd("advance_stage", { to: "BUILD" }) }, "Start building"));
  if (s.stage === "PLANNING") {
    const x = s.x, boss = x && (BOSSES[x.boss] || {});
    return h("div", {}, shopEl(s),
      h("section", { class: "card" }, h("h2", {}, "Planning" + (x ? ` · sprint ${s.sprint} of ${x.sprints_total}` : "")),
        x && x.boss_live ? h("p", { class: "bossnote" }, ic("flag"), ` Boss sprint: ${boss.name}. ${boss.rule}`) : null,
        x ? h("p", { class: "goalnote" }, ic("flag"), ` Sprint goal: ship ${x.goal.target} ticket${x.goal.target > 1 ? "s" : ""} that you fixed or reviewed yourself. Miss it and you get a demotion warning.`) : null,
        h("p", {}, "Look at the Pile, then start the sprint."), h("button", { class: "primary", onclick: () => cmd("advance_stage", { to: "STANDUP" }) }, "Go to standup")));
  }
  if (s.stage === "BUILD" && !w) {
    const next = s.day >= 2 ? ["REVIEW", "End sprint (Review)"] : ["STANDUP", "End day 1 (next standup)"];
    const short = s.x && s.day >= 2 && !s.x.goal.met;
    return h("section", { class: "card" }, h("h2", {}, ic("branch"), " Fix-it desk"), h("p", { class: "muted" }, s.open_card ? "This card has no code. Send your reply." : "Open a card from the Pile."),
      s.open_card ? h("button", { onclick: () => cmd("push") }, "Send reply") : null,
      short ? h("p", { class: "cost risk" }, `Sprint goal not met yet (${s.x.goal.shipped}/${s.x.goal.target}). Ending now means a demotion warning.`) : null,
      h("div", { class: "row" }, h("button", { onclick: () => cmd("advance_stage", { to: next[0] }), disabled: !!s.open_card }, next[1])));
  }
  if (!w) return h("section", { class: "card" }, h("h2", {}, "CodeDesk"));
  const lastRun = run.runs;
  const perks = s.perks.includes("ai_assistant");
  return h("section", { class: "card", "aria-label": "CodeDesk" }, h("h2", {}, ic("branch"), " " + w.title), h("p", {}, w.doc),
    h("pre", { class: "code" }, w.lines.map((t, i) => h("div", { class: "line" + (w.flagged === i + 1 ? " flagged" : ""), role: w.kind === "fix" ? "button" : null, tabindex: w.kind === "fix" ? "0" : null,
      onclick: () => w.kind === "fix" && cmd("flag_line", { line_no: i + 1 }), onkeydown: (e) => { if (e.key === "Enter" && w.kind === "fix") cmd("flag_line", { line_no: i + 1 }); } }, h("span", { class: "n" }, i + 1), t))),
    h("p", { class: "muted" }, w.kind === "fix" ? "Step 1: click the line you think is wrong. Step 2: pick the replacement below. Step 3: run the script to check." : "Fill the blank line from the tray."),
    w.options.map((o) => h("button", { class: "opt" + (w.selected === o.id ? " sel" : "") + (w.assistant === o.id ? " hint" : ""), onclick: () => cmd("select_patch", { option_id: o.id }) }, o.text.trim())),
    w.assistant ? h("p", { class: "muted" }, "AI Assistant suggests the highlighted option (it can be wrong).") : null,
    h("div", { class: "row" }, h("button", { title: "Test your fix and see if it works", onclick: runScript }, ic("play"), " Run Script" + (s.x ? ` (${s.x.move_costs.test} min)` : "")), perks ? h("button", { onclick: () => cmd("use_assistant") }, "AI Assistant") : null),
    lastRun ? h("div", {}, lastRun.map((r) => h("div", { class: "run " + (r.pass ? "pass" : "fail") }, ic(r.pass ? "check" : "cross"), " ", r.text))) : null,
    h("h3", {}, "Checklist: is it really done?"),
    ["tests", "matches_doc", "no_security"].map((b) => h("label", { class: "check" }, h("input", { type: "checkbox", checked: w.dod[b], onchange: () => cmd("toggle_dod", { box: b }) }), h("span", {}, { tests: "Tests pass", matches_doc: "Matches the doc", no_security: "No security concern" }[b]))),
    s.x ? pushDeal(s, w) : null,
    h("div", { class: "row" }, h("button", { class: "primary", title: "Send your fix live to the customers", onclick: () => cmd("push"),
      disabled: !w.selected || (s.x && s.x.boss_live && s.x.boss === "friday_deploy" && !Object.values(w.dod).every(Boolean)) }, ic("rocket"), " Push (send it live)"), h("button", { onclick: () => cmd("hold") }, "Hold")));
}

function pushDeal(s, w) {
  const x = s.x, unticked = Object.values(w.dod).filter((v) => !v).length;
  const lines = [];
  if (unticked) lines.push(h("div", { class: "cost risk" }, x.boss_live && x.boss === "friday_deploy" ? "Friday Deploy: tick every box before you can push."
    : `Pushing with ${unticked} box${unticked > 1 ? "es" : ""} unticked: +${x.prices.unticked_box} Cover and a lower process score.`));
  else if (!w.last_run) lines.push(h("div", { class: "cost risk" }, "Boxes ticked without running the script counts as a dishonest checklist."));
  if (x.next_clean_factor < 1) lines.push(h("div", { class: "cost" }, `Repeat reward: another clean push this sprint is worth ${Math.round(x.next_clean_factor * 100)}% of the first.`));
  if (x.last_stand) lines.push(h("div", { class: "cost good" }, "Last stand: an honest, clean push now pulls your Cover back down."));
  return lines;
}

// Demo Day: a timed standup. When the timer runs out the answer counts as vague (the server scores it).
function standupTimer(q, secs) {
  if (!run.sTimer || run.sTimer.n !== q.n) run.sTimer = { n: q.n, end: performance.now() + secs * 1000, sent: false };
  const el = h("div", { class: "sutimer", id: "sutimer", role: "timer" }, secs + " s");
  return el;
}
setInterval(() => {
  const t = run && run.sTimer, el = document.getElementById("sutimer");
  if (!t || !el || !run.state || !run.state.standup) return;
  const left = Math.max(0, Math.ceil((t.end - performance.now()) / 1000));
  el.textContent = left + " s to answer";
  el.classList.toggle("hurry", left <= 5);
  if (left === 0 && !t.sent) { t.sent = true; toast("warn", "Too slow: that counts as a vague answer"); cmd("reply_standup", { answer: "vague" }); }
}, 250);

async function runScript() {
  await cmd("run_script");
  const r = await api(`/api/v1/runs/${run.id}/state?since=${run.lastSeq - 1}`);
  const ev = r.events.filter((e) => e.type === "script_run").pop();
  run.runs = ev ? ev.runs : null;
  if (run.runs) {
    const ok = run.runs.every((r) => r.pass);
    toast(ok ? "good" : "bad", ok ? "All tests passed!" : "Some tests failed. Check the lines and try again.");
    if (ok) burst(14); else shakeScreen();
  }
  render();
}

function callCard(s) {
  return s.call ? h("div", { class: "callbar", role: "alert" }, h("span", { class: "ring", "aria-hidden": "true" }, ic("phone")),
    h("div", { class: "grow" }, h("b", {}, "Call from " + (NAMES[s.call.sender] || s.call.sender)), h("div", { class: "muted" }, "Answer it (15 min) or ignore it.")),
    h("button", { onclick: () => cmd("answer_call") }, "Answer")) : null;
}

function slackApp(s) {
  const msgs = run.lines.slice(-12);
  return h("div", { class: "slack" },
    h("aside", { class: "side" }, h("h3", {}, "# team-chat"), ["po", "dev1", "dev2"].map((id) => h("div", { class: "member" }, avatar(id), h("span", {}, NAMES[id])))),
    h("div", { class: "main" }, s.stage === "STANDUP" ? codeDesk(s) : null,
      h("section", { class: "card", "aria-label": "Team chat" }, h("h2", {}, "# team-chat"), h("p", { class: "sub" }, "What your team is saying."),
        msgs.length ? h("div", { class: "chat" }, msgs.map((l) => h("div", { class: "msg " + l.tone + (l.id > run.freshAfter ? " new" : "") }, avatar(l.speaker, l.tone), h("div", { class: "bub" }, h("b", {}, NAMES[l.speaker] || l.speaker), h("div", {}, l.text)))))
          : h("p", { class: "muted" }, "No messages yet. Enjoy the quiet while it lasts."))));
}

function githubApp(s) {
  return h("div", { class: "gh" }, h("aside", {}, lanesEl(s), pilePanel(s), intentsEl(s)),
    h("div", { class: "main" }, s.stage === "STANDUP"
      ? h("section", { class: "card" }, h("h2", {}, "Standup is happening in " + appName("slack")), h("p", {}, "Your teammate is waiting for your answer."), h("button", { class: "primary", onclick: () => openApp("slack") }, "Open " + appName("slack")))
      : codeDesk(s)));
}

const stars = (n) => { n = Math.max(0, Math.min(5, Math.round(n))); return h("span", { class: "starrow" }, [1, 2, 3, 4, 5].map((i) => ic(i <= n ? "star" : "star-o"))); };
// cosmetic: how many stars a public reviewer gives for each kind of event
function reviewStars(e) {
  const l = String(e.label || "").toLowerCase();
  if (e.type === "pushed") return l.includes("clean") ? 5 : l.includes("accept") ? 4 : l.includes("bug") ? 2 : l.includes("secur") ? 1 : e.points > 0 ? 4 : 2;
  if (e.type === "push_blocked" || e.type === "attack_check_resolved") return 1;
  if (e.type === "rating_resolved") return e.delta >= 0 ? 4 : 2;
  return 3;
}
// Only things a user of the app would notice become reviews. Escalations, calls and warnings are internal to the team.
const REVIEWABLE = new Set(["pushed", "push_blocked", "attack_check_resolved"]);
const reviewList = () => run.wall.map((e, idx) => ({ e, idx })).filter((x) => REVIEWABLE.has(x.e.type));
const BLURBS = {
  final_price: { good: "Coupons finally take the right amount off. Love it!", bad: "The coupon discount is still wrong. I got overcharged." },
  average_rating: { good: "The ratings page loads now. Thank you!", bad: "The ratings page crashes every time I open it." },
  find_user: { good: "User search is quick and works great.", bad: "Search shows other people's details. That's not safe." },
  total_with_tax: { good: "Tax is added correctly at checkout now.", bad: "My checkout total looks wrong." },
};
function reviewText(e) {
  if (e.type === "push_blocked") return "The app crashes as soon as I open it.";
  if (e.type === "attack_check_resolved") return "I heard this app leaked user data. Uninstalling.";
  const b = BLURBS[e.ticket], good = reviewStars(e) >= 4;
  return b ? (good ? b.good : b.bad) : (good ? "Works well after the latest update." : "Something is off since the latest update.");
}
const QUIP = ["", "Broken!", "Needs work", "It's okay", "Pretty good", "Love it!"];
const REVIEWERS = ["Dana K.", "Mo T.", "Lia P.", "Sam R.", "Kofi A.", "Ivy W."];

function playApp(s) {
  const r = Number(s.meters.rating), list = reviewList().slice(-10).reverse();
  return h("div", { class: "play" },
    h("section", { class: "card store-head" }, h("div", { class: "app-icon", "aria-hidden": "true" }, ic("hammer")),
      h("div", {}, h("h2", {}, "Scrum Corp App"), h("div", { class: "muted" }, "Scrum Corp · Productivity"),
        h("div", { class: "big-rating" }, h("b", {}, r.toFixed(2)), h("span", { class: "stars", "aria-label": r.toFixed(1) + " out of 5 stars" }, stars(r))))),
    h("section", { class: "card", "aria-label": "Reviews" }, h("h2", {}, "Reviews"), h("p", { class: "sub" }, "What the public says about your updates."),
      list.length ? list.map(({ e, idx }) => {
        const k = reviewStars(e), who = REVIEWERS[idx % REVIEWERS.length];
        return h("div", { class: "review" + (idx >= run.wallFresh ? " new" : "") }, h("span", { class: "rv rv" + (idx % 5), "aria-hidden": "true" }, who[0]),
          h("div", {}, h("b", {}, who), h("div", { class: "stars sm", "aria-label": k + " stars" }, stars(k), " ", h("span", { class: "muted" }, QUIP[k])), h("div", {}, reviewText(e))));
      }) : h("p", { class: "muted" }, "No reviews yet. Push an update and users will tell you what they think.")));
}

function youtubeApp(s) {
  return h("section", { class: "card", "aria-label": "Learn" }, h("h2", {}, "Learn something new"), h("p", { class: "sub" }, "A short video is a nice break from the chaos. Each one takes 30 game minutes."),
    h("div", { class: "videos" }, TUTORIALS.map((t, i) => {
      const got = s.unlocked.includes(t.id);
      return h("div", { class: "video" }, h("div", { class: "thumb th" + i, "aria-hidden": "true" }, ic(got ? "check" : "play")), h("b", {}, got ? t.title : "??? " + t.title),
        h("button", { onclick: () => cmd("watch_tutorial", { tutorial_id: t.id }), disabled: got }, got ? "Watched" : "Watch (30 min)"));
    })));
}

function shopApp(s) {
  const own = s.perks.includes("ai_assistant"), noAi = s.x && s.x.heat.includes("no_assistant");
  return h("div", {}, s.x ? (shopEl(s) || h("section", { class: "card" }, h("h2", {}, ic("cart"), " Practice shop"), h("p", { class: "muted" }, "The practice shop opens during planning, between sprints."))) : null,
    h("section", { class: "card", "aria-label": "Upgrades" }, h("h2", {}, "Upgrades"), h("p", { class: "sub" }, noAi ? "Heat: the AI Assistant is switched off this run." : "Spend your points on a helper."),
    h("div", { class: "product" }, h("div", { class: "prod-img", "aria-hidden": "true" }, ic("robot")),
      h("div", { class: "grow" }, h("b", {}, "AI Assistant"), h("div", { class: "muted" }, "Suggests a fix for you. It can be wrong."), h("div", { class: "price" }, own ? [ic("check"), " Owned"] : "150 pts")),
      h("button", { class: "primary", disabled: own || noAi, onclick: () => cmd("buy_perk", { perk_id: "ai_assistant" }) }, own ? "Owned" : "Buy"))));
}

// ------------------------------------------------------------ experimental mechanics (state.x)
const PRACTICES = {
  definition_of_done_p: ["Definition of Done", "Your first Run Script on each ticket costs no time."],
  pair_programming: ["Pair Programming", "Delegated tickets come back with a bug less often."],
  timeboxing: ["Timeboxing", "New requests arrive with more time before they escalate."],
  wip_limit: ["WIP Limit", "Opening a card is faster while the Pile is small."],
  swarming: ["Swarming", "Coaching someone heads off extra calls."],
  retrospective: ["Retrospective", "Once a sprint, calm one escalated card back down."],
  psychological_safety: ["Psychological Safety", "You can give an accurate standup answer without the tutorial."],
  sustainable_pace: ["Sustainable Pace", "More Focus back each morning; tiredness sets in later."],
  backlog_refinement: ["Backlog Refinement", "Deferring a card no longer escalates it."],
  spike: ["Spike", "Tutorials take half the time."],
  tdd_pair: ["TDD Pair (combo)", "Run Script is always free, and you can tell if returned work is bugged."],
  steady_flow: ["Steady Flow (combo)", "No card escalates past a message."],
};
const practiceName = (id) => (PRACTICES[id] || [id])[0];
const BOSSES = {
  auditor: { name: "The Auditor", rule: "A shipped security hole is attacked immediately." },
  scope_creep: { name: "Scope Creep", rule: "Marlo adds a new request every 90 minutes." },
  friday_deploy: { name: "Friday Deploy", rule: "No pushing with unticked boxes, and day 2 is short." },
  demo_day: { name: "Demo Day", rule: "Standups are timed and vague answers cost double." },
};
const ULTIMATES = {
  protect: { name: "Protect the Sprint", text: "No escalations or spot checks for a while." },
  swarm: { name: "Swarm", text: "Everything delegated comes back now, bug-free." },
  retro_now: { name: "Retro Now", text: "Every card calms down one level and gets more time." },
};
const DUOS = new Set(["tdd_pair", "steady_flow"]);

function hudEl(s) {
  const x = s.x;
  if (!x) return h("div", { class: "hud", "data-region": "hud", hidden: true });
  const boss = BOSSES[x.boss] || { name: x.boss, rule: "" };
  const mom = h("div", { class: "bar mom" }, h("i", {}));
  mom.firstChild.style.width = Math.min(100, 100 * x.momentum / x.momentum_full) + "%";
  const ready = x.momentum >= x.momentum_full && s.stage === "BUILD";
  return h("div", { class: "hud", "data-region": "hud" },
    h("div", { class: "hud-row" },
      h("span", { class: "chip" }, ic("calendar"), ` Sprint ${s.sprint} of ${x.sprints_total}`),
      goalChip(x.goal),
      h("span", { class: "chip " + (x.clock_running ? "live" : "paused"), title: "The clock runs while you stand at the Pile and stops while you read a card or answer a standup." }, ic("clock"), x.clock_running ? " Clock running" : " Clock paused"),
      h("span", { class: "chip", title: "Points come from pushes. Process score comes from how you work. The debrief shows the gap." }, ic("coin"), ` ${s.meters.points} pts`, h("span", { class: "sep" }, " | "), ic("check"), ` Process ${x.process_score}`),
      h("span", { class: "chip", title: "Variety of good habits this sprint. Repeating one action stops counting." }, ic("star"), ` Style ${x.style.rank}`),
      x.last_stand ? h("span", { class: "chip danger" }, ic("warn"), " Last stand") : null,
      x.protected_min ? h("span", { class: "chip good" }, ic("check"), ` Protected ${x.protected_min} min`) : null,
      x.boss_live ? h("span", { class: "chip boss", title: boss.rule }, ic("flag"), ` Boss: ${boss.name}. ${boss.rule}`)
        : h("span", { class: "chip faint", title: boss.rule }, ic("flag"), ` Sprint ${x.boss_sprint} boss: ${boss.name}`)),
    h("div", { class: "hud-row" },
      h("span", { class: "lbl" }, "Momentum"), mom,
      ready ? Object.keys(ULTIMATES).map((k) => h("button", { class: "ult", title: ULTIMATES[k].text, onclick: () => cmd("use_ultimate", { kind: k }) }, ULTIMATES[k].name))
        : h("span", { class: "muted small" }, "Fills from coaching, honest checklists, reviews and accurate standups."),
      x.practices.length ? h("span", { class: "pracs" }, x.practices.map((p) => h("span", { class: "pchip" + (DUOS.has(p.id) ? " duo" : ""), title: (PRACTICES[p.id] || ["", ""])[1] }, practiceName(p.id) + (p.level > 1 ? " (Lv 2)" : "")))) : null));
}

// Sprint goal: ship this many tickets yourself (or reviewed) before Review, or get a demotion warning
const goalChip = (g) => h("span", { class: "chip " + (g.met ? "good" : "goal"), title: "Ship this many tickets (clean or acceptable, pushed by you or reviewed) before the sprint review. Missing it is a demotion warning." },
  ic(g.met ? "check" : "flag"), ` Goal: ship ${g.target} · ${g.shipped}/${g.target}`);

function intentsEl(s) {
  const x = s.x;
  if (!x) return null;
  return h("section", { class: "card intents", "aria-label": "Coming up" }, h("h3", {}, ic("clock"), " Coming up"),
    x.intents.length ? h("ul", {}, x.intents.slice(0, 5).map((i) => h("li", {}, h("b", {}, i.in_min <= 0 ? "now" : `in ${i.in_min} min`), " " + i.text)))
      : h("p", { class: "muted small" }, "Nothing announced for the next two hours."));
}

function lanesEl(s) {
  if (!s.x) return null;
  const n = (st) => s.pile.filter((c) => st.includes(c.state)).length;
  const lanes = [["In the Pile", ["pile"]], ["With you", ["open"]], ["With the team", ["delegated"]], ["Back for review", ["returned"]], ["Done", ["done"]]];
  return h("div", { class: "lanes", "aria-label": "Work in flight" }, lanes.map(([k, st]) => h("div", { class: "lane" + (n(st) ? "" : " empty") }, h("b", {}, n(st)), h("small", {}, k))));
}

function shopEl(s) {
  const x = s.x;
  if (!x || !x.shop) return null;
  const sh = x.shop, full = x.practices.filter((p) => !DUOS.has(p.id)).length >= x.slots;
  return h("section", { class: "card shop", "aria-label": "Practice shop" },
    h("h2", {}, ic("cart"), sh.free ? " Pick one practice to start with" : " Practice shop"),
    h("p", { class: "sub" }, sh.free ? "Free. Practices change the rules in your favour, and some pairs combine into something stronger." : `You have ${s.meters.points} points. Unspent points earn a little interest each sprint.`),
    h("div", { class: "offers" }, sh.offers.map((o) => h("div", { class: "offer" + (o.locked ? " locked" : "") },
      h("b", {}, practiceName(o.id)), h("p", {}, (PRACTICES[o.id] || ["", ""])[1]),
      h("div", { class: "row" }, h("button", { class: "primary", disabled: full || (!sh.free && s.meters.points < o.price), onclick: () => cmd("buy_practice", { practice_id: o.id }) }, sh.free ? "Take it" : `Buy · ${o.price} pts`),
        h("button", { onclick: () => cmd("lock_offer", { practice_id: o.id }), title: "A locked offer stays when you reroll" }, o.locked ? "Unlock" : "Lock"))))),
    h("div", { class: "row" }, h("button", { onclick: () => cmd("reroll_shop"), disabled: s.meters.points < sh.reroll_price }, `Reroll (${sh.reroll_price ? sh.reroll_price + " pts" : "free"})`),
      full ? h("span", { class: "muted" }, "All practice slots are full.") : null));
}

// One big project per difficulty. Only the Easy project is playable so far.
const PROJECTS = [
  { level: "Easy", title: "The Coupon Shop", blurb: "Fix the bugs before launch", live: true },
  { level: "Medium", title: "Coming soon", blurb: "A bigger app, a bigger mess", live: false },
  { level: "Hard", title: "Coming soon", blurb: "Real users, real pressure", live: false },
];
const PATH_NODES = [
  { icon: "clipboard", label: "Plan", app: "github" },
  { icon: "chat", label: "Standup · day 1", app: "slack" },
  { icon: "hammer", label: "Build · day 1", app: "github" },
  { icon: "chat", label: "Standup · day 2", app: "slack" },
  { icon: "hammer", label: "Build · day 2", app: "github" },
  { icon: "flag", label: "Review", app: "github" },
  { icon: "chest", label: "Debrief reward", app: null },
];
// where the player is on the path (the day counter goes up when Build ends into the second Standup)
function pathIndex(s) {
  if (s.stage === "PLANNING") return 0;
  if (s.stage === "STANDUP") return s.day >= 2 ? 3 : 1;
  if (s.stage === "BUILD") return s.day >= 2 ? 4 : 2;
  return 5;
}

// The roadmap: a slim left rail you can fold away. Open by default only when there is room.
const railPref = () => { try { const v = localStorage.getItem("railOpen"); if (v === "1" || v === "0") return v === "1"; } catch (_) { /* storage can be blocked */ } return innerWidth >= 1100; };
const railSave = (open) => { try { localStorage.setItem("railOpen", open ? "1" : "0"); } catch (_) { /* storage can be blocked */ } };

function roadmap(s) {
  if (run.railOpen == null) run.railOpen = railPref();
  const at = pathIndex(s), doneCards = s.pile.filter((c) => c.state === "done").length, proj = PROJECTS[0];
  const go = (n) => { if (isNote(n.app)) { pingNote(n.app); run.sig = null; render(); } else openApp(n.app); };
  const nav = h("nav", { class: "rail" + (run.railOpen ? "" : " collapsed"), "aria-label": "Project roadmap", "data-region": "rail" });
  const toggle = h("button", { class: "railtoggle", "aria-expanded": String(run.railOpen), "aria-controls": "railbody", title: run.railOpen ? "Hide roadmap" : "Show roadmap", onclick: () => {
    run.railOpen = !run.railOpen; railSave(run.railOpen);
    nav.classList.toggle("collapsed", !run.railOpen); toggle.setAttribute("aria-expanded", String(run.railOpen)); toggle.title = run.railOpen ? "Hide roadmap" : "Show roadmap";
  } }, ic("map"), h("span", { class: "rt" }, "Roadmap"), ic("chev-l", "chev-open"));
  nav.append(toggle, h("div", { class: "railbody", id: "railbody" },
    h("div", { class: "projhead" }, h("small", {}, `Project 1 · ${proj.level}` + (s.x ? ` · sprint ${s.sprint} of ${s.x.sprints_total}` : "")), h("b", {}, proj.title)),
    h("ol", { class: "rnodes" }, PATH_NODES.map((n, i) => {
      const state = i < at ? "done" : i === at ? "now" : "locked", chest = i === PATH_NODES.length - 1;
      const sub = state === "now" && n.label.startsWith("Build") ? `${doneCards} of ${s.pile.length} done` : "";
      const word = state === "done" ? "done" : state === "now" ? "your turn" : "locked";
      return h("li", { class: `rnode ${state}` + (run.lastPath != null && i === at - 1 && at > run.lastPath ? " just" : "") + (run.lastPath != null && i === at && at > run.lastPath ? " arrive" : "") },
        h("button", { class: "rdot", title: `${n.label}, ${word}`, "aria-label": `${n.label}, ${word}`, "aria-current": state === "now" ? "step" : null, disabled: state !== "now" || !n.app, onclick: () => go(n) },
          ic(state === "done" ? "check" : state === "locked" && !chest ? "lock" : n.icon)),
        h("span", { class: "rlab" }, n.label, sub ? h("small", {}, sub) : null));
    })),
    h("ul", { class: "rmore" }, PROJECTS.slice(1).map((p, i) => h("li", {}, ic("lock"), h("span", {}, `Project ${i + 2} · ${p.level}`))))));
  return nav;
}

const PAGES = { slack: slackApp, github: githubApp, play: playApp, youtube: youtubeApp, shop: shopApp };

// ---- tabs and sticky notes: pull a tab down out of the browser and it becomes a floating note
const attached = () => APPS.filter((a) => !run.notes.some((n) => n.id === a.id));   // apps still in the browser
const isNote = (id) => run.notes.some((n) => n.id === id);
const visible = (id) => run.app === id || isNote(id);                               // on screen, so not "unread"
let noteZ = 0, swallow = false;

function badgeFor(id, s) {
  if (id === "github") return s.pile.filter((c) => c.state !== "done").length;
  if (id === "slack") return visible("slack") ? 0 : run.lines.filter((l) => l.id > (run.slackSeen ?? 0)).length;
  if (id === "play") return visible("play") ? 0 : run.wall.slice(run.playSeen ?? 0).filter((e) => REVIEWABLE.has(e.type)).length;
  return 0;
}
const badgeLabel = (id, n) => n + (id === "github" ? " open issues" : " new");

function openApp(id) { if (!run || isNote(id)) return; run.app = id; run.sig = null; render(); }
const clampPos = (n) => { n.x = Math.max(-n.w + 90, Math.min(innerWidth - 90, n.x)); n.y = Math.max(0, Math.min(innerHeight - 44, n.y)); };
const over = (ev, r) => ev.clientX >= r.left && ev.clientX <= r.right && ev.clientY >= r.top && ev.clientY <= r.bottom;

function detach(id, x, y) {
  if (!run || isNote(id) || attached().length <= 1) return;   // the browser always keeps one tab
  const n = { id, x: x - 70, y: y - 18, w: Math.min(420, innerWidth - 24), z: ++noteZ, tilt: run.notes.length % 2 ? 1.2 : -1.2, min: false };
  clampPos(n); run.notes.push(n);
  if (run.app === id) run.app = attached()[0].id;
  run.sig = null; render();
}
function dock(id) { run.notes = run.notes.filter((n) => n.id !== id); run.app = id; run.sig = null; render(); }
function pingNote(id) { const n = run.notes.find((x) => x.id === id); if (n) { n.z = ++noteZ; n.ping = true; setTimeout(() => { n.ping = false; }, 1400); } }

function startTabDrag(e, id) {
  if (e.pointerType === "touch" || e.button !== 0 || attached().length <= 1) return;   // touch and keyboard use the Pop out button
  e.preventDefault();   // no text selection while dragging; the click still fires
  const sx = e.clientX, sy = e.clientY, app = APPS.find((a) => a.id === id);
  let ghost = null;
  const tearing = (ev) => { const r = document.querySelector("#browser .tabstrip").getBoundingClientRect(); return ev.clientY > r.bottom + 36 || ev.clientY < r.top - 36; };
  const move = (ev) => {
    if (!ghost) {
      if (Math.hypot(ev.clientX - sx, ev.clientY - sy) < 8) return;
      run.dragging = true; document.body.classList.add("dragging");
      ghost = h("div", { class: "ghost" }, ic(app.icon), h("b", {}, app.name), h("small", {}, ""));
      document.body.append(ghost);
    }
    const t = tearing(ev);
    ghost.style.left = ev.clientX + "px"; ghost.style.top = ev.clientY + "px";
    ghost.classList.toggle("tear", t);
    ghost.lastChild.textContent = t ? "Let go for a sticky note" : "Pull it down";
  };
  const up = (ev) => {
    for (const [t, f] of [["pointermove", move], ["pointerup", up], ["pointercancel", up]]) window.removeEventListener(t, f);
    if (!ghost) return;
    ghost.remove(); document.body.classList.remove("dragging"); run.dragging = false;
    swallow = true; setTimeout(() => { swallow = false; }, 0);   // the release must not count as a tab click
    if (ev.type === "pointerup" && tearing(ev)) detach(id, ev.clientX, ev.clientY); else { run.sig = null; render(); }
  };
  for (const [t, f] of [["pointermove", move], ["pointerup", up], ["pointercancel", up]]) window.addEventListener(t, f);
}

function startNoteDrag(e, n, el) {
  if (e.button !== 0 || e.target.closest("button")) return;
  e.preventDefault();
  run.dragging = true; n.z = ++noteZ; el.style.zIndex = 20 + n.z; el.classList.add("lifting"); document.body.classList.add("dragging");
  const ox = e.clientX - n.x, oy = e.clientY - n.y, strip = document.querySelector("#browser .tabstrip");
  const move = (ev) => {
    n.x = ev.clientX - ox; n.y = ev.clientY - oy; clampPos(n);
    el.style.left = n.x + "px"; el.style.top = n.y + "px";
    strip.classList.toggle("dock", over(ev, strip.getBoundingClientRect()));
  };
  const up = (ev) => {
    for (const [t, f] of [["pointermove", move], ["pointerup", up], ["pointercancel", up]]) window.removeEventListener(t, f);
    document.body.classList.remove("dragging"); run.dragging = false;
    const hit = ev.type === "pointerup" && over(ev, strip.getBoundingClientRect());
    strip.classList.remove("dock");
    if (hit) dock(n.id); else { run.sig = null; render(); }   // dropping a note on the tab bar puts it back
  };
  for (const [t, f] of [["pointermove", move], ["pointerup", up], ["pointercancel", up]]) window.addEventListener(t, f);
}

function noteEl(s, n) {
  clampPos(n);
  const app = APPS.find((a) => a.id === n.id), b = badgeFor(n.id, s);
  const el = h("section", { class: `note app-${n.id}` + (n.min ? " min" : "") + (n.ping ? " ping" : ""), role: "group", "aria-label": app.name + " sticky note" },
    h("div", { class: "note-head", onpointerdown: (e) => startNoteDrag(e, n, el) },
      ic("pin"), h("span", { class: "ai", "aria-hidden": "true" }, ic(app.icon)), h("b", {}, app.name),
      b > 0 ? h("span", { class: "badge", "aria-label": badgeLabel(n.id, b) }, b) : null, h("span", { class: "grow" }),
      h("button", { class: "nbtn", title: n.min ? "Open note" : "Shrink note", "aria-label": n.min ? "Open note" : "Shrink note", onclick: () => { n.min = !n.min; run.sig = null; render(); } }, ic(n.min ? "open" : "minus")),
      h("button", { class: "nbtn", title: "Put back in the browser", "aria-label": "Put back in the browser", onclick: () => dock(n.id) }, ic("undo"))),
    h("div", { class: "note-body" }, PAGES[n.id](s)));
  el.style.left = n.x + "px"; el.style.top = n.y + "px"; el.style.width = n.w + "px"; el.style.zIndex = 20 + n.z; el.style.setProperty("--tilt", n.tilt + "deg");
  el.addEventListener("pointerdown", () => { n.z = ++noteZ; el.style.zIndex = 20 + n.z; });
  if (!n.min && typeof ResizeObserver !== "undefined") new ResizeObserver(() => { const w = Math.round(el.getBoundingClientRect().width); if (Math.abs(w - n.w) > 2) n.w = w; }).observe(el);   // remember the width you pulled it to
  return el;
}

// ---- The browser frame is built once. After that render() patches only the regions whose data changed,
// so tabs, hover, scroll position and running animations are not thrown away every few seconds.
function badgeEl(id, s) { const n = badgeFor(id, s); return n > 0 ? h("span", { class: "badge", "aria-label": badgeLabel(id, n) }, n) : null; }

function tabsEl(s) {
  const left = attached();
  return h("div", { class: "tabstrip", role: "tablist", "aria-label": "Open apps", "data-region": "tabs" }, left.map((a) => h("button", { class: `btab app-${a.id}` + (a.id === run.app ? " active" : ""), role: "tab", "aria-selected": String(a.id === run.app), "data-app": a.id,
    onpointerdown: (e) => startTabDrag(e, a.id), onclick: () => { if (!swallow) openApp(a.id); } },
    h("span", { class: "fav", "aria-hidden": "true" }, ic(a.icon)), h("span", {}, a.name), badgeEl(a.id, s))),
    left.length > 1 ? h("span", { class: "tabhint" }, "Tip: pull a tab down to make a sticky note") : null);
}
// unread counts change often: update them in place instead of rebuilding the tabs
function syncBadges(s) {
  document.querySelectorAll("#browser .btab").forEach((b) => {
    const id = b.dataset.app, n = badgeFor(id, s);
    let el = b.querySelector(".badge");
    if (n > 0) { if (!el) { el = h("span", { class: "badge" }); b.append(el); } el.textContent = String(n); el.setAttribute("aria-label", badgeLabel(id, n)); }
    else if (el) el.remove();
  });
}
const addrEl = (s) => h("div", { class: "addr", "data-region": "addr" }, h("span", { class: "navg", "aria-hidden": "true" }, ic("chev-l"), ic("chev-r"), ic("refresh")),
  h("div", { class: "url" }, ic("lock"), " " + APPS.find((a) => a.id === run.app).url), meters(s));
const coachEl = (s) => h("div", { class: "coach", "data-region": "coach" }, h("span", { class: "heron", "aria-hidden": "true" }, ic("c-heron")), h("div", { class: "say" }, coachHint(s)), steps(s));
const callEl = (s) => h("div", { class: "callslot", "data-region": "call" }, callCard(s), run.error ? h("div", { class: "err pad", role: "alert" }, run.error) : null);
function appheadEl() {
  const app = APPS.find((a) => a.id === run.app);
  return h("div", { class: `apphead app-${app.id}`, "data-region": "apphead" }, h("span", { class: "ai", "aria-hidden": "true" }, ic(app.icon)), h("b", {}, app.name), h("span", {}, app.tag),
    h("button", { class: "nbtn pop", title: "Pop out as a sticky note", "aria-label": "Pop out as a sticky note", disabled: attached().length <= 1, onclick: () => detach(app.id, innerWidth - 470 - 34 * run.notes.length, 150 + 34 * run.notes.length) }, ic("note"), " Pop out"));
}
const pageEl = (s) => h("div", { class: "page", role: "tabpanel", "aria-label": APPS.find((a) => a.id === run.app).name, "data-region": "page" }, PAGES[run.app](s));
const notesLayer = (s) => h("div", { class: "notes" }, run.notes.map((n) => noteEl(s, n)));

function browserFrame(s) {
  return h("div", { class: "win", id: "browser" }, tabsEl(s), addrEl(s), coachEl(s), hudEl(s), callEl(s), appheadEl(), h("div", { class: "winbody" }, roadmap(s), pageEl(s)));
}

// what each page actually draws; a page is rebuilt only when this changes
const PAGE_DEPS = {
  slack: (s) => [run.lines.slice(-12).map((l) => l.id), s.stage, s.standup, s.x ? [s.x.standup_timer_s, s.x.prices] : null],
  github: (s) => [s.pile, s.stage, s.work, s.open_card, s.day, s.perks, run.runs, s.standup,
    s.x ? [s.x.shop, s.x.intents, s.x.move_costs, s.x.retro_left, s.x.next_clean_factor, s.x.practices, s.meters.points, s.x.goal, Math.floor(s.clock_min / 10)] : null],
  play: (s) => [Number(s.meters.rating), reviewList().length],
  youtube: (s) => [s.unlocked],
  shop: (s) => [s.perks, s.x ? [s.x.shop, s.meters.points, s.x.heat] : null],
};
const REGIONS = {
  tabs: { sig: () => attached().map((a) => a.id).join() + "|" + run.app, build: tabsEl },
  addr: { sig: (s) => JSON.stringify([s.meters, s.warnings, s.stage, s.day, run.app]), build: addrEl },
  coach: { sig: (s) => s.stage + "|" + coachHint(s), build: coachEl },
  hud: { sig: (s) => JSON.stringify(s.x ? [s.sprint, s.stage, s.meters.points, s.x.clock_running, s.x.process_score, s.x.style.rank, s.x.last_stand,
    s.x.protected_min, s.x.momentum, s.x.practices, s.x.boss_live, s.x.goal] : null), build: hudEl },
  call: { sig: (s) => JSON.stringify(s.call || null) + "|" + (run.error || ""), build: callEl },
  apphead: { sig: () => run.app + "|" + attached().length, build: appheadEl },
  rail: { sig: (s) => [pathIndex(s), s.sprint, s.pile.filter((c) => c.state === "done").length, s.pile.length].join(), build: roadmap },
  page: { sig: (s) => run.app + "|" + JSON.stringify(PAGE_DEPS[run.app](s)), build: pageEl },
};
const notesSig = (s) => JSON.stringify(run.notes.map((n) => [n.id, n.x, n.y, n.w, n.z, n.min, n.ping, badgeFor(n.id, s), PAGE_DEPS[n.id](s)]));
const scrollables = () => [...document.querySelectorAll(".chat, .note-body")];

function updateScreen(s) {
  const frame = document.getElementById("browser");
  if (!frame) {                                   // first time on this screen: build everything once
    mount(browserFrame(s), notesLayer(s));
    run.regs = Object.fromEntries(Object.entries(REGIONS).map(([k, r]) => [k, r.sig(s)])); run.notesSig = notesSig(s);
    return;
  }
  const keep = scrollables().map((e) => e.scrollTop);   // a rebuilt list must not jump back to the top
  for (const [name, r] of Object.entries(REGIONS)) {
    const sig = r.sig(s);
    if (sig === run.regs[name]) continue;
    run.regs[name] = sig;
    document.querySelector(`#browser [data-region="${name}"]`).replaceWith(r.build(s));
  }
  syncBadges(s);
  const ns = notesSig(s);
  if (ns !== run.notesSig) { run.notesSig = ns; document.querySelector(".notes").replaceWith(notesLayer(s)); }
  scrollables().forEach((e, i) => { if (keep[i]) e.scrollTop = keep[i]; });
}

function render() {
  if (!run || !run.state || run.dragging) return;   // never rebuild the screen under a drag
  const s = run.state;
  const sig = JSON.stringify({ ...s, clock_min: 0, day_used_min: 0 }) + run.lines.length + run.wall.length + JSON.stringify(run.runs || null) + (run.error || "");
  if (sig === run.sig && document.getElementById("meters")) { const clk = document.querySelector('#meters [data-k="Clock"] b'); if (clk) clk.textContent = s.clock_min + " min"; return; }  // nothing changed but the clock
  run.sig = sig;
  // a new stage opens the app where that stage happens (or nudges its note if you pulled it out)
  if (!run.app) run.app = s.stage === "STANDUP" ? "slack" : "github";
  else if (run.lastStage && run.lastStage !== s.stage && ["PLANNING", "STANDUP", "BUILD"].includes(s.stage)) {
    const to = s.stage === "STANDUP" ? "slack" : "github";
    if (isNote(to)) { pingNote(to); toast("info", appName(to) + " is open in a note"); }
    else if (to !== run.app) { run.app = to; toast("info", "Opening " + appName(to)); }
  }
  if (isNote(run.app)) run.app = attached()[0].id;
  const at = pathIndex(s);
  if (run.lastPath != null && at > run.lastPath) toast("good", "Step complete: " + PATH_NODES[at - 1].label);   // quiet: the roadmap shows the rest
  const lastId = run.lines.length ? run.lines[run.lines.length - 1].id : 0;
  run.freshAfter = run.slackSeen ?? 0; run.wallFresh = run.playSeen ?? 0;   // only lines you have not seen yet animate in
  updateScreen(s);
  if (visible("slack")) run.slackSeen = lastId;
  if (visible("play")) run.playSeen = run.wall.length;
  if (((run.lastStage && run.lastStage !== s.stage) || (run.lastApp && run.lastApp !== run.app)) && !REDUCED) { const d = document.querySelector("#browser .page"); if (d) { d.classList.add("swap"); setTimeout(() => d.classList.remove("swap"), 700); } }
  run.lastStage = s.stage; run.lastApp = run.app; run.lastPath = at;
}

async function debrief() {
  timers.forEach(clearInterval);
  const d = await api(`/api/v1/runs/${run.id}/debrief`);
  const names = { win: d.x ? "You survived all " + d.x.sprints_played + " sprints" : "You survived the sprint", lose_rating: "Fired: Rating fell below 2.0", lose_cover: "Exposed: Cover hit 100", lose_warnings: "Demoted twice" };
  mount(h("section", { class: "card narrow" }, h("div", { class: "hero", "aria-hidden": "true" }, ic(d.ending === "win" ? "c-heron-cheer" : "c-heron-oops")), h("h2", {}, names[d.ending] || d.ending),
    h("table", {}, [["Rating", Number(d.rating).toFixed(2)], ["Cover", d.cover], ["Points", d.points], ["Process score", d.process_score], ["Gap (rating % minus process)", d.gap]].map(([k, v]) => h("tr", {}, h("th", {}, k), h("td", {}, v)))),
    h("p", { class: "muted" }, "Points never count toward your process score: honest process does."),
    d.x ? xDebrief(d.x) : null,
    h("div", { class: "row" }, h("button", { class: "primary", onclick: () => questions("post", () => mount(h("section", { class: "card narrow" }, h("h2", {}, "Thanks for playing")))) }, "Take the post-test"), h("button", { onclick: setupRun }, "Play again"))));
  if (d.ending === "win") { lastPt = null; burst(40); setTimeout(() => burst(30), 350); }
}

function xDebrief(x) {
  return h("div", { class: "xdeb" },
    h("div", { class: "row" }, h("span", { class: "chip" }, ic("coin"), ` Run score ${x.run_score}` + (x.heat.length ? ` (Heat ${x.heat.length})` : "")),
      h("span", { class: "chip" }, ic("star"), " Style " + (x.style.map((r) => r.rank).join(" · ") || "-")),
      h("span", { class: "chip" + (x.near_miss ? " danger" : "") }, ic("search"), ` Highest Cover ${x.max_cover}` + (x.near_miss ? " · close call" : "")),
      x.clutches ? h("span", { class: "chip good" }, ic("check"), ` ${x.clutches} clutch save${x.clutches > 1 ? "s" : ""}`) : null,
      x.goals.length ? h("span", { class: "chip" }, ic("flag"), " Goals " + x.goals.map((g) => g.met ? "met" : "missed").join(" · ")) : null),
    h("h3", {}, "What the team says"), x.story.map((l) => h("p", { class: "story" }, l)),
    x.practices.length ? h("p", { class: "muted" }, "Practices: " + x.practices.map(practiceName).join(", ")) : null,
    h("p", { class: "muted" }, `Challenge code ${x.seed}: share it so classmates can play the same sprints.`));
}

// ------------------------------------------------------------ instructor
async function instructorScreen() {
  const list = h("div", {});
  mount(h("section", { class: "card" }, h("h2", {}, "Your cohort"), list));
  try {
    const r = await api(`/api/v1/instructor/cohorts/${me.cohort_id}/runs`);
    list.replaceChildren(h("table", {}, h("tr", {}, ["Student", "Code", "Status", "Ending", "Process", "Gain", ""].map((x) => h("th", {}, x))),
      r.runs.map((x) => h("tr", {}, h("td", {}, x.student), h("td", {}, x.seed ?? ""), h("td", {}, x.status), h("td", {}, x.ending || ""), h("td", {}, x.process_score), h("td", {}, x.gain == null ? "" : x.gain.toFixed(2)),
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
