import { runWelcome } from "/welcome.js";
import { TERMS, CONCEPTS, SCORING, CORE_TERMS } from "/guide.js";
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
  document.body.classList.toggle("in-game", !!document.getElementById("browser"));
  if (!(wasGame && document.getElementById("browser"))) playEnter();
};

// Messages are small, sit in the bottom corner and never block clicks. Only results are shown (good, bad, warning):
// "info" messages are dropped, because the guide and the screen already say where you are.
function toast(kind, msg) {
  if (kind === "info") return;
  if ([...toasts.children].some((c) => c.dataset.msg === msg)) return;
  const t = h("div", { class: "toast " + kind, "data-msg": msg }, h("span", { class: "ti" }, ic({ good: "check", bad: "cross", warn: "warn" }[kind])), h("span", {}, msg));
  toasts.append(t);
  while (toasts.children.length > 2) toasts.firstChild.remove();
  setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 300); }, 3000);
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
  mount(h("section", { class: "card narrow" }, h("h2", {}, kind === "pre" ? "Quick warm-up quiz" : "Quick final quiz"), h("p", { class: "lead" }, kind === "pre" ? "Ten short questions so we know where you start. No grades, and guessing is fine." : "The same kind of questions again, so we can see what you learned."),
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
    h("p", { class: "lead" }, "Three Sprints with Marlo, Ines and Tobi. Each one has the five Scrum events: Planning, Daily Scrum, work, Review and Retrospective. Nothing is timed."),
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
const NAMES = { po: "Marlo (Product Owner)", dev1: "Ines (Developer)", dev2: "Tobi (Developer)" };
const FEATURE_NAMES = { delegate: "asking the team for help", practices: "practices", intents: "seeing what's coming", lanes: "seeing what's coming",
  style: "style ranks", hand: "action cards", release: "releases", multiplier: "teamwork bonuses", momentum: "special moves" };

// ---- Tap a word to see what it means in everyday language (the word list lives in guide.js)
const tipEl = h("div", { id: "tip", role: "tooltip", hidden: true });
document.body.append(tipEl);
document.addEventListener("click", () => { tipEl.hidden = true; });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") tipEl.hidden = true; });
function showTip(anchor, t) {
  tipEl.replaceChildren(h("b", {}, t[0]), h("span", {}, t[1]));
  tipEl.hidden = false;
  const r = anchor.getBoundingClientRect(), tw = Math.min(300, innerWidth - 16);
  tipEl.style.width = tw + "px";
  tipEl.style.left = Math.max(8, Math.min(innerWidth - tw - 8, r.left)) + "px";
  const below = r.bottom + 8, th = tipEl.offsetHeight;
  tipEl.style.top = (below + th > innerHeight - 8 ? Math.max(8, r.top - th - 8) : below) + "px";
}
function term(key, label) {
  const t = TERMS[key];
  if (!t) return label || key;
  const open = (e) => { e.stopPropagation(); showTip(e.currentTarget, t); };
  return h("span", { class: "term", tabindex: "0", role: "button", "aria-label": `${label || t[0]}. What does this mean?`, onclick: open,
    onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(e); } } }, label || t[0]);
}

// ---- "New idea" cards: teach one concept the first time it matters, then never again
let seen = new Set();
const seenKey = () => "seen:" + (me ? me.id : "x");
function loadSeen() { try { seen = new Set(JSON.parse(localStorage.getItem(seenKey()) || "[]")); } catch (_) { seen = new Set(); } }
function markSeen(id) { seen.add(id); try { localStorage.setItem(seenKey(), JSON.stringify([...seen])); } catch (_) { /* storage can be blocked */ } }
function conceptFor(s) {
  const x = s.x || {}, f = new Set(x.features || []), build = s.stage === "BUILD";
  // Only the ideas a beginner really needs, in the order they come up. Everything else is learned by doing.
  const checks = [
    ["welcome", s.stage === "PLANNING" && s.sprint === 1],
    ["standup", s.stage === "STANDUP" && !!s.standup],
    ["bug", build && !s.open_card && s.pile.some((c) => c.type === "fix" && c.state === "pile")],
    ["team", !!x.team && build && !s.work],
    ["test", !!(s.work && s.work.last_run)],
    ["dod", !!(s.work && s.work.last_run && s.work.last_run.all_pass)],
    ["review_changes", s.pile.some((c) => c.review)],
    ["stuck", !!x.team && Object.values(x.team).some((m) => m.stuck)],
    ["outage", s.pile.some((c) => c.outage && c.state !== "done")],
    ["wave", !!(x.wave && !x.wave.failed)],
    ["practices", !!(x.shop && f.has("practices"))],
    ["hand", f.has("hand") && !!x.hand && build],
    ["release", f.has("release") && build],
    ["boss", !!x.boss_live],
  ];
  const hit = checks.find(([id, ok]) => ok && !seen.has(id) && CONCEPTS[id]);
  return hit ? hit[0] : null;
}
const conceptLayer = h("div", { id: "concept", hidden: true });
document.body.append(conceptLayer);
function showConcept(id) {
  const c = CONCEPTS[id];
  run.modal = id;
  const ok = h("button", { class: "primary", onclick: () => { markSeen(id); run.modal = null; conceptLayer.hidden = true; conceptLayer.replaceChildren(); run.sig = null; render(); } }, "Got it");
  conceptLayer.replaceChildren(h("div", { class: "concept-card", role: "dialog", "aria-modal": "true", "aria-labelledby": "concept-title" },
    h("span", { class: "heron", "aria-hidden": "true" }, ic("c-heron-cheer")),
    h("div", { class: "concept-body" }, h("small", { class: "newidea" }, "New idea"), h("h2", { id: "concept-title" }, c.title), h("p", {}, c.text),
      c.terms.length ? h("div", { class: "row terms" }, h("span", { class: "muted small" }, "Words to know:"), c.terms.map((k) => term(k))) : null,
      h("div", { class: "row" }, ok))));
  conceptLayer.hidden = false;
  ok.focus();
}
const TUTORIALS = [{ id: "conditions", title: "Reading if / else" }, { id: "definition_of_done", title: "Definition of Done" }];
let run = null;      // {id, lastSeq, lastLine, state, lines[], wall[]}
let timers = [];

async function newRun(opts = {}) {
  const r = await api("/api/v1/runs", "POST", opts);
  run = { id: r.id, lastSeq: 0, lastLine: 0, state: r.state, lines: [], wall: [], lastTick: performance.now(), busy: false, notes: [] };
  loadSeen();
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
  if (!run || !run.state || run.state.status !== "active" || run.state.stage !== "BUILD" || run.modal || (run.state.x && run.state.x.calm)) { run && (run.lastTick = performance.now()); return; }   // learning mode: nothing runs on a clock
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
  clutch: (e) => ["good", "Clutch save! Suspicion " + e.cover],
  director: (e) => e.action === "relief" ? ["info", "Marlo gives everyone " + e.minutes + " more minutes"] : ["warn", "Things are quiet. New work arrives"],
  bounty_paid: (e) => ["good", "Bounty paid: +" + e.points + " pts"],
  interest_paid: (e) => ["good", "Interest on saved points: +" + e.points],
  comeback_offered: () => ["info", "Comeback: extra Focus and a bounty ticket this sprint"],
  ultimate_used: (e) => ["good", ULTIMATES[e.kind] ? ULTIMATES[e.kind].name + "!" : "Ultimate used"],
  style_ranked: (e) => ["info", "Sprint style rank: " + e.rank],
  achievement: () => ["good", "Achievement: a whole sprint with no bluffing"],
  card_reset: () => ["good", "Retrospective: card calmed down"],
  sprint_goal: (e) => e.met ? ["good", `Sprint goal met: ${e.shipped} of ${e.target} sent (+${e.points} pts)`]
    : ["bad", `Sprint goal missed: ${e.shipped} of ${e.target} sent. A strike and Suspicion +${e.cover}`],
  release_shipped: (e) => e.failed ? ["bad", `Release shipped with a bug inside: bonus lost (${e.points} pts)`] : ["good", `Release shipped: ${e.base} × ${e.mult} = ${e.points} pts`],
  trust_changed: (e) => ["warn", `${NAMES[e.dev] || e.dev} trust down to ${e.trust}`],
  card_sent_back: () => ["info", "Sent back to the team"],
  change_fixed: () => ["good", "Change fixed"],
  deck_changed: (e) => ["info", e.added ? `Added a ${CARD_KINDS[e.added][0]} card to your deck` : `Removed a ${CARD_KINDS[e.removed][0]} card`],
  hand_drawn: (e) => ["info", `New hand: ${e.cards.map((k) => CARD_KINDS[k][0]).join(", ")}`],
  dev_started: (e) => ["info", `${who(e.dev)} started working on it`],
  dev_done: (e) => ["good", `${who(e.dev)} finished! Check the work before it goes to users`],
  dev_stuck: (e) => ["bad", `${who(e.dev)} is stuck and has stopped working`],
  dev_unblocked: (e) => ["good", `${who(e.dev)} is back to work`],
  dev_still_stuck: (e) => ["bad", `${who(e.dev)} was stuck too long: the request got louder`],
  combo: (e) => ["good", `Combo ${e.count}! +${e.points} bonus points`],
  combo_broken: (e) => ["bad", `Combo broken: ${e.why}`],
  outage: (e) => ["bad", `Production outage! Users can't use the app. Fix it within ${e.minutes} min`],
  outage_fixed: (e) => ["good", `Outage fixed! +${e.points} pts, rating +${e.rating}`],
  outage_missed: (e) => ["bad", `The outage dragged on: rating ${e.rating}, Suspicion +${e.cover}`],
  urgent: (e) => ["warn", `Marlo: "This one is urgent!" Done within ${e.minutes} min pays +${e.points}`],
  speed_result: (e) => e.tier === "slow" ? ["warn", "Slow fix: no speed bonus"] : ["good", e.tier === "perfect" ? `PERFECT FIX! +${e.points}` : `Fast fix +${e.points}`],
  quick_save: (e) => ["good", `Quick save! +${e.points}`],
  wave: (e) => ["bad", `BUG WAVE! Clear all ${e.ids.length} in ${e.minutes} min: +${e.points}`],
  wave_progress: (e) => ["good", `${e.left} to go`],
  wave_clear: (e) => ["good", `WAVE CLEARED! +${e.points}`],
  wave_failed: () => ["bad", "The wave got away from you"],
  sprint_dealt: (e) => ["info", e.boss ? "Boss sprint: " + (BOSSES[e.boss] || {}).name : "Sprint " + e.sprint + " dealt"],
};

function collect(events) {
  for (const e of events) {
    const t = e.type;
    if (XTOAST[t]) { const [k, m] = XTOAST[t](e); toast(k, m); if (["clutch", "practice_gained", "combo", "outage_fixed", "quick_save", "wave_clear"].includes(t) || (t === "speed_result" && e.tier === "perfect")) burst(); if (["last_stand", "outage", "dev_stuck", "combo_broken", "wave"].includes(t)) shakeScreen(); }
    if (t === "dev_started") markSeen("demo_give");
    if (["pushed", "push_blocked", "review_resolved", "rating_resolved", "attack_check_resolved", "warning_issued", "contradiction_detected", "card_escalated", "call_missed"].includes(t)) {
      run.wall.push(e); react(e);
    }
  }
}

const wallText = (e) => ({
  pushed: `Sent to users: ${e.label} (${e.points >= 0 ? "+" : ""}${e.points} pts${e.held ? ", waiting in the release" : ""}${e.mult ? `, ×${e.mult}` : ""})`, push_blocked: `Blocked: that fix crashes the app (${e.points} pts)`,
  review_resolved: "Reviews are in.", rating_resolved: `Rating moved ${e.delta >= 0 ? "+" : ""}${e.delta}`,
  attack_check_resolved: `Security attack on ${e.ticket}: ${e.rating} rating, ${e.points} points`, warning_issued: `Strike ${e.warnings} from management`,
  contradiction_detected: "A teammate noticed your standup answer was wrong: Suspicion +" + e.cover, card_escalated: `A request got louder: now a ${["message", "call", "meeting"][e.level]}`, call_missed: "You missed a call: Energy down",
}[e.type]);

function react(e) {
  const t = e.type;
  if (t === "pushed") { if (e.points > 0) { toast("good", wallText(e)); burst(); } else toast("bad", wallText(e)); }
  else if (t === "push_blocked" || t === "warning_issued") { toast("bad", wallText(e)); shakeScreen(); }
  else if (t === "attack_check_resolved" || t === "call_missed") toast("bad", wallText(e));
  else if (t === "contradiction_detected") toast("warn", wallText(e));   // "getting louder" is already shown on the card itself
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

// The status meters are built ONCE. After that only their numbers, bars and colours change, in place,
// so icons never flash and nothing is re-created when you click something.
const METER_DEFS = [["Rating", "rating", "star", "sky", false], ["Points", "points", "coin", "yellow", false], ["Cover", "suspicion", "search", "lav", true],
  ["Focus", "energy", "bolt", "mint", true], ["Warnings", "strikes", "warn", "coral", false], ["Clock", "clock", "clock", "white", false]];
function buildMeters() {
  return h("div", { id: "meters", role: "group", "aria-label": "Your status" }, METER_DEFS.map(([k, termKey, icon, tone, bar]) =>
    h("div", { class: `meter t-${tone}`, "data-k": k }, h("span", { class: "lbl", "aria-hidden": "true" }, ic(icon)), h("span", { class: "mname" }, term(termKey)), h("b", {}),
      bar ? h("div", { class: "bar" }, h("i", {})) : null)));
}
const METER_FMT = { Points: (n) => String(Math.round(n)), Rating: (n) => n.toFixed(1), Cover: (n) => String(Math.round(n)), Focus: (n) => String(Math.round(n)) };
function syncMeters(s) {
  const root = document.getElementById("meters");
  if (!root) return;
  const m = s.meters, now = { Points: m.points, Rating: Number(m.rating), Cover: m.cover, Focus: Math.round(m.focus) };
  const prev = run.lastM;
  run.lastM = now;
  const tile = (k) => root.querySelector(`[data-k="${k}"]`);
  for (const k of Object.keys(now)) {
    const t = tile(k), b = t.querySelector("b"), txt = METER_FMT[k](now[k]);
    if (b.dataset.v === undefined || b.dataset.v === "") { b.textContent = txt; b.dataset.v = txt; }
    else if (b.dataset.v !== txt) {
      const a = prev ? prev[k] : now[k], good = k === "Cover" ? now[k] < a : now[k] > a;
      b.dataset.v = txt;
      if (REDUCED || !prev) b.textContent = txt;
      else {
        const chip = h("span", { class: "delta " + (good ? "good" : "bad") }, (now[k] > a ? "+" : "−") + METER_FMT[k](Math.abs(now[k] - a)));
        t.classList.add(good ? "gain" : "loss"); t.append(chip);
        chip.addEventListener("animationend", () => { chip.remove(); t.classList.remove("gain", "loss"); });
        tween(b, a, now[k], METER_FMT[k]);
      }
    }
  }
  tile("Rating").classList.toggle("low", m.rating < 3);
  tile("Cover").classList.toggle("low", m.cover >= 70); tile("Cover").querySelector(".bar i").style.width = Math.max(0, Math.min(100, m.cover)) + "%";
  tile("Focus").classList.toggle("low", m.focus < 30); tile("Focus").querySelector(".bar i").style.width = Math.max(0, Math.min(100, m.focus)) + "%";
  const calmMode = !!(s.x && s.x.calm);
  tile("Cover").hidden = calmMode;   // the fake-résumé idea is not part of learning mode
  const w = tile("Warnings"); w.hidden = calmMode || !s.warnings; w.classList.add("low"); w.querySelector("b").textContent = String(s.warnings);
  tile("Clock").hidden = calmMode;   // nothing is timed in learning mode, so no clock
  const clk = tile("Clock").querySelector("b"), ct = s.clock_min + " min";
  if (!calmMode && clk.textContent !== ct) clk.textContent = ct;
}

const STAGE_FLOW = [["PLANNING", "Sprint Planning"], ["STANDUP", "Daily Scrum"], ["BUILD", "Work"], ["REVIEW", "Sprint Review"], ["RETRO", "Retrospective"]];
// The fake apps. Each game feature lives in one of them. Rename here to rebrand.
const APPS = [
  { id: "slack", name: "Slackish", icon: "chat", tag: "Team chat", url: "slackish.fake/scrumcorp/team-chat" },
  { id: "github", name: "GitHab", icon: "branch", tag: "Your to-do list and the code", url: "githab.fake/scrumcorp/app/issues" },
  { id: "play", name: "Play Storey", icon: "store", tag: "What users say", url: "playstorey.fake/store/apps/scrumcorp" },
  { id: "youtube", name: "ToobYou", icon: "tv", tag: "Videos and the word book", url: "toobyou.fake/learn" },
  { id: "shop", name: "Amazin'", icon: "cart", tag: "Upgrades", url: "amazin.fake/upgrades" },
];
const appName = (id) => APPS.find((a) => a.id === id).name;

// ---- The guide: exactly one next step, why it matters, and which button to press (it glows).
const who = (id) => (NAMES[id] || id).split(" (")[0];
function guide(s) {
  const x = s.x || {}, w = s.work, f = new Set(x.features || []);
  const g = (step, why, target, app) => ({ step, why, target, app });
  if (s.status !== "active") return g("The run is over.", "", null);
  if (s.guide && s.guide.pending) return g("Read the scene and answer the question", "Each Scrum moment starts with a short scene. A wrong answer only explains why: nothing is timed.", "scene-next");
  if (s.stage === "REVIEW" && s.guide) return g("Look at what users said, then go to the Retrospective", "The Sprint Review is where the team inspects what it made. Play Storey shows how users reacted.", "to-retro", "play");
  if (s.stage === "RETRO" && s.guide) return g(s.sprint >= s.x.sprints_total ? "Finish the project" : `Start Sprint ${s.sprint + 1}`, "The Retrospective is done. The improvement you chose helps the next Sprint.", "next-sprint", "github");
  if (s.call && hasCard(s, "call")) return g(`Answer ${who(s.call.sender)}'s call`, "A teammate is stuck. Clearing what blocks the team is the Scrum Master's main job.", "answer-call");
  if (s.stage === "PLANNING") {
    if (x.shop && x.shop.free) return g("Pick one practice (it's free)", "Practices are good team habits. Each one changes a rule in your favour.", "shop-take", "github");
    return g(s.x && s.x.calm ? "Begin the Sprint" : `Start sprint ${s.sprint}`, s.sprint === 1 ? "A sprint is a short round of work, 2 days here. Each day starts with a quick team meeting called the Daily Scrum."
      : "Same rhythm as before: Daily Scrum, work, Daily Scrum, work, then the Sprint Review and Retrospective.", "start-sprint", "github");
  }
  if (s.stage === "STANDUP") {
    if (s.standup) return g(`Answer ${who(s.standup.teammate)}'s question`, "The standup is a 2-minute daily check-in. Honest answers keep Suspicion low. Bluffs raise it.", "standup", "slack");
    return g("Start the work day", "The meeting is done. Time to work on the to-do list.", "start-build", "slack");
  }
  if (s.stage !== "BUILD") return g("Sprint Review", "", null);
  if (w) {
    if (w.kind === "fix" && run.error && run.error.includes("not the broken one")) return g("That line looks fine: click a different one", "Compare each line with the description. The bug is the line that does something different.", "code", "github");
    if (w.kind === "fix" && !w.flagged) return g("Find the line that's wrong and click it", "Read what it should do at the top, then each line. The line that does not match the description is the bug.", "code", "github");
    if (!w.selected) return g(w.kind === "fix" ? "Choose the line that fixes it" : "Choose the line that fills the gap", "Pick the option that makes the code do what the description says.", "patch", "github");
    if (!w.last_run) return hasCard(s, "test") ? g("Test your fix", "A test runs the examples from the description and checks the answers before users ever see them.", "test", "github")
      : g("Regroup to get a Test card", "Every move needs a matching card. Regroup draws a fresh hand.", "regroup", "github");
    if (!w.last_run.all_pass) return g("The test failed: choose a different fix", "Red means at least one example gives the wrong answer.", "patch", "github");
    if (!Object.values(w.dod).every(Boolean)) return g("Tick the Done checklist, but only what's true", "Teams agree on what 'finished' means. Tests cannot spot security holes, so read the code before ticking that box.", "dod", "github");
    return g("Send your fix to users", "Users get your change and leave reviews, which move your app rating.", "push", "github");
  }
  if (s.open_card) return g("Send your reply", "This request only needs an answer, no code.", "push", "github");
  const live = s.pile.filter((c) => c.state !== "done");
  const open = run.reviewing && live.find((c) => c.id === run.reviewing && c.review);
  if (open) {
    const r = open.review, found = r.changes.filter((ch) => ch.shown === "faulty" && ch.sure).length;
    const toFix = r.changes.find((ch) => ch.shown === "faulty" && !ch.fixed);
    if (toFix) return g("Fix the faulty change you found", "Fixing it now means users never see that mistake.", "fixchange", "github");
    if (found < r.faulty_count) return g(`Find the faulty change: ${r.faulty_count - found} still hidden`, "Test a change (needs a Test card later on) or ask the author (costs a little trust). You know how many are faulty, not which.", "inspect", "github");
    return g("Send it to users", r.faulty_count ? "You found and fixed every faulty change. This counts toward your sprint goal." : "Nothing is faulty. Shipping it counts toward your sprint goal.", "review-ship", "github");
  }
  const rev = live.find((c) => c.review);
  if (rev) return g(`Check the work ${who(rev.review.assignee || "dev1")} sent back`, "Work from the team can contain mistakes. Check it before users see it.", "review:" + rev.id, "github");
  const stuck = x.team && ["dev1", "dev2"].find((d) => x.team[d].stuck);
  if (stuck) return g(`${who(stuck)} is stuck: unblock them`, "A stuck teammate makes no progress. Clearing blockers is the Scrum Master's main job.", "unblock:" + stuck, "github");
  const help = live.find((c) => c.type === "help_call" && c.state === "pile");
  if (help && hasCard(s, "coach")) return g(`Help ${who(help.sender)}`, "Coaching costs a little time now, and next time they solve it alone. It raises your teamwork score.", "coach:" + help.id, "github");
  const goalMet = !x.goal || x.goal.met;
  const code = live.find((c) => (c.type === "fix" || c.type === "build") && c.state === "pile");
  const free = x.team && ["dev1", "dev2"].find((d) => !x.team[d].task);
  const urgentOne = live.find((c) => (c.outage || c.urgent) && c.state === "pile");
  const target = urgentOne || code;
  if (free && target && hasCard(s, "delegate") && f.has("delegate"))
    return g(`Give "${target.title || typeLabel(target.type)}" to ${who(free)}`, `${who(free)} is free. Keep your team busy and check their work when it comes back. Or drag it onto "You" to fix it yourself.`, `give:${target.id}:${free}`, "github");
  if (!goalMet && code) {
    if (!hasCard(s, "work")) return g("Regroup to get a Work card", "Every move needs a matching card. Regroup draws a fresh hand.", "regroup", "github");
    return g(`Fix "${code.title}" yourself` + (x.team ? " while the team is busy" : ""), `Sprint goal: send ${x.goal.target} fix${x.goal.target > 1 ? "es" : ""} to users. ${x.goal.shipped} done so far.`, "work:" + code.id, "github");
  }
  if (x.release && x.release.items.length) return g("Send your release to users", "Finished fixes wait in the release until you send it. That's when the points arrive.", "ship-release", "github");
  const other = live.find((c) => c.state === "pile" && (c.type === "status_demand" || c.type === "problem_report"));
  if (other && hasCard(s, "work")) return g(`Answer "${typeLabel(other.type)}" from ${who(other.sender)}`, "Requests you ignore get louder and raise Suspicion.", "work:" + other.id, "github");
  if (code && hasCard(s, "work")) return g(`Goal done! Fix "${code.title}" too, or end the ${s.day >= 2 ? "sprint" : "day"}`, "Extra fixes earn points. Unfinished requests keep getting louder.", "work:" + code.id, "github");
  const busy = x.team && ["dev1", "dev2"].find((d) => x.team[d].task);
  if (busy && (!goalMet || s.day < 2)) {
    const m = x.team[busy];
    return g(`${who(busy)} is working on it: about ${m.eta_min} min left`, `When ${who(busy)} finishes, the work comes back for you to check. Ending the ${s.day >= 2 ? "sprint" : "day"} now would leave it unfinished.`, null, "github");
  }
  return s.day >= 2 ? g("Finish the sprint", "Users see the result and you get your sprint review.", "end-sprint", "github")
    : g("End the day", "Tomorrow starts with another standup.", "end-day", "github");
}

function steps(s) {
  const at = STAGE_FLOW.findIndex(([k]) => k === s.stage);
  return h("div", { class: "steps", "aria-label": "Sprint steps" }, STAGE_FLOW.map(([, label], i) => h("span", { class: "step " + (i < at ? "done" : i === at ? "now" : "") }, i < at ? [ic("check"), " ", label] : label)));
}

const typeIcon = (t) => { t = String(t); return t.includes("fix") ? "bug" : t.includes("help") ? "sos" : t.includes("build") ? "hammer" : t.includes("problem") ? "alert" : t.includes("status") ? "megaphone" : "pin"; };
const TYPE_LABEL = { fix: "Bug", build: "New feature", help_call: "Help request", status_demand: "Status update", problem_report: "Problem report" };
const TYPE_TERM = { fix: "bug", build: "feature" };
const typeLabel = (t) => TYPE_LABEL[t] || String(t).replace("_", " ");
// countdowns are live text: they tick every update without rebuilding the page they sit in
const dueText = (at, clock) => at == null ? "Overdue" : at <= clock ? "Due now" : `Due in ${dur(at - clock)}`;
const liveDue = (at, clock) => h("span", { class: "live-due", "data-at": at == null ? "" : String(at) }, dueText(at, clock));
const inText = (at, clock) => Math.round(at - clock) <= 0 ? "now" : `in ${Math.round(at - clock)} min`;
function syncLive(s) {
  document.querySelectorAll(".live-due").forEach((e) => { const t = dueText(e.dataset.at === "" ? null : Number(e.dataset.at), s.clock_min); if (e.textContent !== t) e.textContent = t; });
  document.querySelectorAll(".live-in").forEach((e) => { const t = inText(Number(e.dataset.at), s.clock_min); if (e.textContent !== t) e.textContent = t; });
}
const dur = (mins) => { mins = Math.max(0, Math.round(mins)); const hh = Math.floor(mins / 60), mm = mins % 60; return hh ? `${hh} h ${mm} min` : `${mm} min`; };

function pilePanel(s) {
  const f = new Set((s.x && s.x.features) || []), canDelegate = !s.x || f.has("delegate");
  const isCode = (c) => c.type === "fix" || c.type === "build";
  const team = s.x && s.x.team;
  const give = (c, d) => h("button", { class: "give", "data-guide": `give:${c.id}:${d}`, title: team[d].task ? `${who(d)} is busy right now` : `Give it to ${who(d)}` + needs(s, "delegate"),
    disabled: !hasCard(s, "delegate") || !!team[d].task, onclick: () => cmd("delegate", { card_id: c.id, to: d }) }, avatar(d, "calm"), who(d));
  // each card has ONE main action, an optional "give to" group and a quiet "later"
  const actions = (c) => {
    if (s.stage !== "BUILD" || c.state === "delegated") return null;
    if (c.review) return h("div", { class: "pactions" }, h("button", { class: "pmain primary", "data-guide": "review:" + c.id, title: "Check their work change by change", onclick: () => { run.reviewing = c.id; run.sig = null; render(); } }, "Check their work"));
    const help = c.type === "help_call";
    const main = c.state === "open" ? h("button", { class: "pmain", title: "Put it back on the list for now", onclick: () => cmd("hold") }, "Put it down")
      : help ? h("button", { class: "pmain", "data-guide": "coach:" + c.id, title: "Teach them how to solve it" + needs(s, "coach"), disabled: !hasCard(s, "coach"), onclick: () => cmd("coach", { card_id: c.id }) }, "Help them")
      : h("button", { class: "pmain", "data-guide": "work:" + c.id, title: (isCode(c) ? "Read the code and fix it yourself" : "Open it and reply") + needs(s, "work"), disabled: !!s.open_card || !hasCard(s, "work"), onclick: () => cmd("open_card", { card_id: c.id }) },
        c.state === "returned" ? "Check their work" : isCode(c) ? "Fix it myself" : "Open");
    const gives = canDelegate && c.state === "pile" && !help
      ? (team ? h("div", { class: "pgive" }, h("span", { class: "givelbl" }, "Give to"), give(c, "dev1"), give(c, "dev2"))
        : h("button", { class: "give", title: "Hand it to a developer. You check their work when it comes back." + needs(s, "delegate"), disabled: !hasCard(s, "delegate"), onclick: () => cmd("delegate", { card_id: c.id }) }, "Ask the team"))
      : null;
    return h("div", { class: "pactions" }, main, gives,
      c.state === "open" ? null : h("button", { class: "quiet", title: "Move it down the list. It gets a little louder." + needs(s, "defer"), disabled: !hasCard(s, "defer"), onclick: () => cmd("defer", { card_id: c.id }) }, "Later"),
      s.x && s.x.retro_left > 0 && c.escalation > 0 ? h("button", { class: "quiet", title: "Retrospective: calm this card back down", onclick: () => cmd("retro", { card_id: c.id }) }, "Calm it down") : null);
  };
  const live = s.pile.filter((c) => c.state !== "done" && c.state !== "backlog");
  const louder = ["", "Getting louder: they called you", "Getting louder: they want a meeting"];
  const calm = !!(s.x && s.x.calm);
  return h("section", { class: "card", id: "pile", "aria-label": calm ? "Sprint Backlog" : "To-do list" }, h("h2", {}, ic("clipboard"), " ", calm ? "Sprint Backlog" : term("todo"), ` (${live.length})`),
    live.length ? null : h("p", { class: "muted" }, calm ? "Nothing left in the Sprint Backlog. When you are ready, end the day." : "Nothing here right now. New requests arrive during the day."),
    live.map((c) => h("div", { class: `pile-item esc${c.escalation}` + (c.state === "open" ? " open" : "") + (c.bounty ? " bounty" : "") + (c.spot ? " spot" : "") + (c.outage ? " outage" : "") + (c.urgent ? " urgent" : "") + (c.wave ? " wave" : ""),
      draggable: team && s.stage === "BUILD" && c.state === "pile" ? "true" : null,
      ondragstart: (e) => { run.dragCard = c.id; run.dragging = true; e.dataTransfer.setData("text/plain", c.id); },
      ondragend: () => { run.dragging = false; run.dragCard = null; setTimeout(() => { run.sig = null; render(); }, 0); } },
      c.outage ? h("span", { class: "chip danger" }, ic("alert"), " Outage! Users can't use the app") : null,
      c.urgent ? h("span", { class: "chip goal" }, ic("bolt"), " Urgent: bonus if done on time") : null,
      c.wave ? h("span", { class: "chip danger" }, ic("alert"), " Bug wave") : null,
      c.bounty ? h("span", { class: "chip good" }, "Bounty: extra points for a clean fix") : null,
      h("div", { class: "ptitle" }, ic(typeIcon(c.type)), h("b", {}, (c.spot ? "Spot check: " : "") + (c.title || typeLabel(c.type)))),
      h("div", { class: "pmeta", title: [c.payoff.points ? `Reward: +${c.payoff.points} points.` : "", c.penalty.cover ? `Ignore it and Suspicion goes up by ${c.penalty.cover}.` : ""].join(" ").trim() },
        h("span", { class: "pill kind-" + c.type }, TYPE_TERM[c.type] ? term(TYPE_TERM[c.type], typeLabel(c.type)) : typeLabel(c.type)),
        h("span", { class: "pwho" }, avatar(c.sender, "calm"), who(c.sender)),
        s.x && s.x.calm ? null : h("span", { class: "pdue" }, ic("clock"), liveDue(c.deadline_min, s.clock_min))),
      c.state === "delegated" ? h("div", { class: "pstate" }, `${who(c.assignee || "dev1")} is on it`) : c.state === "returned" ? h("div", { class: "pstate back" }, `Back from ${who(c.assignee || "dev1")}: check it`) : null,
      c.escalation ? h("div", { class: "tag louder" }, term("escalation", louder[c.escalation] || louder[2])) : null,
      s.x ? priceTag(s, c) : null,
      actions(c))));
}

// What a move costs right now, and which other requests would slip while you do it
function priceTag(s, c) {
  const x = s.x, cost = x.move_costs;
  const slip = (mins) => s.pile.filter((o) => o.id !== c.id && o.state !== "done" && o.state !== "delegated" && o.deadline_min != null && o.deadline_min <= s.clock_min + mins).length;
  const work = c.ticket ? cost.read : cost.open_other;
  const out = [];
  if (s.stage === "BUILD" && c.state === "pile") {
    const n = slip(work);   // only say something when there is a real cost to doing this now
    if (n) out.push(h("div", { class: "cost risk" }, `Doing this now: ${n} other request${n > 1 ? "s" : ""} will get louder`));
  }
  return out;
}

function codeDesk(s) {
  const w = s.work, f = new Set((s.x && s.x.features) || []);
  if (s.stage === "STANDUP" && s.standup) {
    const q = s.standup;
    const pr = s.x && s.x.prices, sus = (n) => "Suspicion " + (n > 0 ? "+" : "") + n;
    const calmMode = !!(s.x && s.x.calm);
    const label = calmMode ? { accurate: "Say honestly where it stands", vague: "Stay vague", wrong: "Say what sounds good (not true)" }
      : { accurate: "Explain honestly", vague: "Keep it vague", wrong: "Make something up" };
    const say = calmMode ? { accurate: "The team sees the real picture and can help.", vague: "A hidden problem: the team will make more mistakes.", wrong: "A bigger hidden problem: more mistakes later." }
      : { accurate: pr && `${sus(pr.standup.accurate)} now. If that fix later turns out broken: ${sus(pr.contradiction_cover)}.`,
      vague: pr && `${sus(pr.standup.vague * pr.vague_multiplier)}. A small bluff.`, wrong: pr && `${sus(pr.standup.wrong)}. A big bluff.` };
    const timer = s.x && s.x.standup_timer_s ? standupTimer(q, s.x.standup_timer_s) : null;
    return h("section", { class: "card", "aria-label": "Daily Scrum" }, h("h2", {}, "Daily ", term("standup"), " with " + who(q.teammate)),
      h("p", {}, `"How did your last fix go?"`),
      calmMode ? h("p", { class: "muted small" }, "The Daily Scrum works only when what we say is true. A hidden problem makes the team's next mistakes more likely.") : null, timer,
      h("div", { class: "row", "data-guide": "standup" }, q.choices.map((c) => h("button", { class: pr ? "deal" : "", onclick: () => cmd("reply_standup", { answer: c }) }, label[c] || c, pr ? h("small", {}, say[c]) : null))),
      q.choices.includes("accurate") || calmMode ? null : h("p", { class: "muted small" }, "Watch a video in ToobYou to unlock the honest answer."));
  }
  if (s.stage === "REVIEW" && s.guide) return reviewStage(s);
  if (s.stage === "RETRO" && s.guide) return retroStage(s);
  if (s.stage === "STANDUP") return h("section", { class: "card" }, h("h2", {}, s.x && s.x.calm ? "Daily Scrum done" : "Standup done"),
    h("button", { class: "primary", "data-guide": "start-build", onclick: () => cmd("advance_stage", { to: "BUILD" }) }, "Start the work day"));
  if (s.stage === "PLANNING" && s.guide) return planningStage(s);
  if (s.stage === "PLANNING") {
    const x = s.x, boss = x && (BOSSES[x.boss] || {});
    const soon = x && x.unlocks_next && x.unlocks_next.length ? x.unlocks_next.map((k) => FEATURE_NAMES[k]).filter(Boolean) : [];
    return h("div", {}, shopEl(s),
      h("section", { class: "card" }, h("h2", {}, "Planning" + (x ? ` · `: ""), x ? term("sprint", `sprint ${s.sprint} of ${x.sprints_total}`) : null),
        x && x.boss_live ? h("p", { class: "bossnote" }, ic("flag"), ` Boss sprint: ${boss.name}. ${boss.rule}`) : null,
        x ? h("p", { class: "goalnote" }, ic("flag"), " ", term("goal"), `: send ${x.goal.target} fix${x.goal.target > 1 ? "es" : ""} to users`) : null,
        h("button", { class: "primary", "data-guide": "start-sprint", onclick: () => cmd("advance_stage", { to: "STANDUP" }) }, "Start the sprint"),
        null));
  }
  const rev = s.stage === "BUILD" && !w && run.reviewing && s.pile.find((c) => c.id === run.reviewing && c.review);
  if (rev) return reviewDesk(s, rev);
  if (s.stage === "BUILD" && !w) {
    const next = s.day >= 2 ? ["REVIEW", "Finish the sprint", "end-sprint"] : ["STANDUP", "End day 1", "end-day"];
    const short = s.x && s.day >= 2 && !s.x.goal.met;
    return h("section", { class: "card" }, h("h2", {}, ic("branch"), " Your desk"),
      h("p", { class: "muted" }, s.open_card ? "This request needs a reply, not code." : "Pick a request from your to-do list."),
      s.open_card ? h("button", { class: "primary", "data-guide": "push", onclick: () => cmd("push") }, "Send reply") : null,
      short && !s.x.calm ? h("p", { class: "cost risk" }, `Sprint goal not met yet (${s.x.goal.shipped} of ${s.x.goal.target}). Finishing now means a strike.`) : null,
      s.x ? releaseEl(s) : null,
      h("div", { class: "row" }, h("button", { "data-guide": next[2], onclick: () => endStage(s, next[0]), disabled: !!s.open_card || needsWork(s, next[0]), title: needsWork(s, next[0]) ? "Pick an item first: fix it yourself or give it to Ines or Tobi" : "" }, next[1])));
  }
  if (!w) return h("section", { class: "card" }, h("h2", {}, "Your desk"));
  const lastRun = run.runs;
  const perks = s.perks.includes("ai_assistant");
  const box = { tests: "The test passed", matches_doc: "It does what the description says", no_security: "It's safe: strangers can't misuse it" };
  return h("section", { class: "card", "aria-label": "Code desk" }, h("h2", {}, ic(w.kind === "fix" ? "bug" : "hammer"), " " + w.title),
    w.speed ? h("div", { class: "speed", "data-speed": "" }, h("div", { class: "speedbar" }, h("i", {}), h("em", { class: "mark" })), h("b", { class: "speedtier" }), h("small", { class: "speedmiss" })) : null,
    h("div", { class: "doc" }, h("small", {}, "What it should do"), h("p", {}, w.doc)),
    h("p", { class: "muted small" }, w.kind === "fix" ? "One line is wrong. Click it fast." : "One line is missing. Pick it."),
    h("pre", { class: "code", "data-guide": "code" }, w.lines.map((t, i) => h("div", { class: "line" + (w.flagged === i + 1 ? " flagged" : ""), role: w.kind === "fix" ? "button" : null, tabindex: w.kind === "fix" ? "0" : null,
      onclick: () => w.kind === "fix" && cmd("flag_line", { line_no: i + 1 }), onkeydown: (e) => { if (e.key === "Enter" && w.kind === "fix") cmd("flag_line", { line_no: i + 1 }); } }, h("span", { class: "n" }, i + 1), t))),
    h("h3", {}, w.kind === "fix" ? "Replace it with" : "Fill the gap with"),
    h("div", { class: "opts", "data-guide": "patch" }, w.options.map((o) => h("button", { class: "opt" + (w.selected === o.id ? " sel" : "") + (w.assistant === o.id ? " hint" : ""), onclick: () => cmd("select_patch", { option_id: o.id }) }, o.text.trim()))),
    w.assistant ? h("p", { class: "muted" }, "The AI Assistant suggests the highlighted option. It can be wrong.") : null,
    h("div", { class: "row" }, h("button", { "data-guide": "test", title: "Run the description's examples on your fix" + needs(s, "test"), disabled: !hasCard(s, "test"), onclick: runScript }, ic("play"), " Test my fix" + (s.x ? ` (${s.x.move_costs.test} min)` : "")),
      perks ? h("button", { disabled: !hasCard(s, "assist"), title: needs(s, "assist"), onclick: () => cmd("use_assistant") }, "Ask the AI") : null),
    lastRun ? h("div", {}, lastRun.map((r) => h("div", { class: "run " + (r.pass ? "pass" : "fail") }, ic(r.pass ? "check" : "cross"), " ", r.text))) : null,
    w.scan ? h("div", { class: "run " + (w.scan === "hole" ? "fail" : "pass") }, ic(w.scan === "hole" ? "alert" : "search"), w.scan === "hole" ? " Security Scan: this fix leaves a security hole." : " Security Scan: no security problem found.") : null,
    h("h3", {}, term("dod")),
    h("div", { "data-guide": "dod" }, ["tests", "matches_doc", "no_security"].map((b) => h("label", { class: "check" }, h("input", { type: "checkbox", checked: w.dod[b], onchange: () => cmd("toggle_dod", { box: b }) }), h("span", {}, box[b])))),
    s.x ? pushDeal(s, w) : null,
    h("div", { class: "row" }, h("button", { class: "primary", "data-guide": "push", title: "Put your fix into the live app", onclick: () => cmd("push"),
      disabled: !w.selected || (s.x && s.x.boss_live && s.x.boss === "friday_deploy" && !Object.values(w.dod).every(Boolean)) }, ic("rocket"), " ", term("ship")), h("button", { onclick: () => cmd("hold") }, "Put it down")));
}


// ---- Learning mode: the five Scrum events as real screens, and the scene dialog that teaches each one
const WHEN_LABEL = { planning: "Sprint Planning", daily_1: "Daily Scrum", daily_2: "Daily Scrum", review: "Sprint Review", retro: "Retrospective" };
function backlogList(g) {
  return h("ol", { class: "backlog", "aria-label": "Product Backlog" }, g.backlog.map((b) => h("li", { class: b.in_sprint && g.committed ? "in" : "" },
    h("span", { class: "btitle" }, b.title), b.in_sprint && g.committed ? h("span", { class: "chip good" }, ic("check"), " In this Sprint") : (g.committed ? h("span", { class: "chip faint" }, "Stays in the Product Backlog") : null))));
}
function planningStage(s) {
  const g = s.guide, last = s.sprint >= s.x.sprints_total;
  return h("section", { class: "card stagecard", "aria-label": "Sprint Planning" }, h("h2", {}, ic("clipboard"), ` Sprint Planning · Sprint ${s.sprint} of ${s.x.sprints_total}`),
    h("p", { class: "lead" }, g.theme),
    h("div", { class: "goalbox" }, ic("flag"), h("div", {}, h("small", {}, "Sprint Goal"), h("b", {}, g.goal))),
    h("h3", {}, "Product Backlog (Marlo's order)"), backlogList(g),
    h("p", { class: "muted small" }, "The items marked for this Sprint are the Sprint Backlog: they appear on your list when the work starts. Nothing is timed."),
    h("button", { class: "primary", "data-guide": "start-sprint", onclick: () => cmd("advance_stage", { to: "STANDUP" }) }, "Begin the Sprint: Daily Scrum"));
}
function reviewStage(s) {
  const done = s.pile.filter((c) => c.state === "done" && c.ticket).length, tot = s.pile.filter((c) => c.ticket && c.state !== "backlog").length, g = s.x.goal;
  return h("section", { class: "card stagecard", "aria-label": "Sprint Review" }, h("h2", {}, ic("flag"), ` Sprint Review · Sprint ${s.sprint}`),
    h("div", { class: "goalbox" }, ic(g.met ? "check" : "flag"), h("div", {}, h("small", {}, "Sprint Goal"), h("b", {}, g.text), h("span", { class: "small" }, g.met ? ` Goal met: ${g.shipped} of ${g.target} items` : ` Goal not met: ${g.shipped} of ${g.target} items`))),
    h("p", {}, `${done} of ${tot} Sprint Backlog items were sent to users. Open ${appName("play")} to see what users said: that is the Sprint Review feedback.`),
    h("p", { class: "muted small" }, "Items that were not finished go back to the Product Backlog. The Product Owner decides what comes next."),
    h("button", { class: "primary", "data-guide": "to-retro", onclick: () => cmd("advance_stage", { to: "RETRO" }) }, "On to the Retrospective"));
}
function retroStage(s) {
  const last = s.sprint >= s.x.sprints_total;
  const skill = s.x.skill || {}, debt = s.x.debt || 0;
  const pct = (v) => Math.round(v * 100) + "%";
  return h("section", { class: "card stagecard", "aria-label": "Retrospective" }, h("h2", {}, ic("bulb"), ` Retrospective · Sprint ${s.sprint}`),
    h("p", {}, "The team looked at how it worked and chose one improvement."),
    s.x.practices.length ? h("p", { class: "pracs" }, s.x.practices.map((p) => h("span", { class: "pchip", title: (PRACTICES[p.id] || ["", ""])[1] }, practiceName(p.id)))) : null,
    s.x.team ? riskBars(s) : null,
    h("button", { class: "primary", "data-guide": "next-sprint", onclick: () => cmd("advance_stage", { to: "PLANNING" }) }, last ? "Finish the project" : `Start Sprint ${s.sprint + 1}`));
}

// The scene dialog: one Scrum moment, one question. A wrong answer explains why and lets you try again; nothing is timed or scored down.
const sceneLayer = h("div", { id: "scene", hidden: true });
document.body.append(sceneLayer);
function speakerAvatar(who_) { return who_ === "heron" ? h("span", { class: "heron", "aria-hidden": "true" }, ic("c-heron")) : h("span", { class: "heron", "aria-hidden": "true" }, avatar(who_, "calm")); }
function syncScene(s) {
  const g = s.guide, p = g && g.pending;
  if (!p) {
    if (run.sceneId) { run.sceneId = null; run.modal = null; sceneLayer.hidden = true; sceneLayer.replaceChildren(); }
    return;
  }
  const first = run.sceneId !== p.id;
  run.sceneId = p.id; run.modal = "scene";
  if (conceptLayer && !conceptLayer.hidden) { conceptLayer.hidden = true; conceptLayer.replaceChildren(); }
  const tried = new Map(p.tried.map((t) => [t.id, t]));
  const choice = (c) => {
    const t = tried.get(c.id), wrong = t && !t.ok, right = t && t.ok;
    return h("button", { class: "scene-choice" + (wrong ? " wrong" : "") + (right ? " right" : "") + (c.suggested ? " hint" : ""), disabled: p.resolved || !!t,
      onclick: () => cmd("guide_answer", { choice_id: c.id }) },
      h("span", { class: "ci", "aria-hidden": "true" }, right ? ic("check") : wrong ? ic("cross") : null),
      h("span", { class: "ct" }, h("b", {}, c.text), c.detail ? h("small", {}, c.detail) : null, c.suggested && !t ? h("small", { class: "evid" }, "The evidence from this Sprint points here") : null));
  };
  const last = p.tried[p.tried.length - 1];
  const prem = g.premise && p.step === 1 && p.when === "planning" ? h("div", { class: "premise" }, h("b", {}, g.premise.title), g.premise.lines.map((l) => h("p", {}, l))) : null;
  const card = h("div", { class: "scene-card", role: "dialog", "aria-modal": "true", "aria-labelledby": "scene-title" },
    h("div", { class: "scene-head" }, speakerAvatar(p.speaker),
      h("div", {}, h("small", { class: "newidea" }, `${WHEN_LABEL[p.when] || p.when} · scene ${p.step} of ${p.of}`), h("h2", { id: "scene-title" }, p.concept))),
    prem, h("p", { class: "scene-text" }, p.scene),
    h("h3", { class: "scene-q" }, p.question),
    h("div", { class: "scene-choices" }, p.choices.map(choice)),
    last ? h("div", { class: "scene-fb " + (last.ok ? "ok" : "no"), role: "status" }, h("b", {}, last.ok ? (p.kind === "pick" ? "Decision made. " : "Right. ") : "Not quite. "), last.feedback) : null,
    p.resolved ? h("div", { class: "scene-teach" }, ic("bulb"), h("div", {}, h("small", {}, "Scrum idea"), p.teach)) : null,
    p.resolved ? h("div", { class: "row" }, h("button", { class: "primary", "data-guide": "scene-next", onclick: () => cmd("guide_next") }, "Continue")) : (p.tried.length ? h("p", { class: "muted small" }, "Read why, then pick another answer.") : null),
    run.error ? h("div", { class: "err", role: "alert" }, run.error) : null);
  const keep = sceneLayer.querySelector(".scene-card");
  const top = keep ? keep.scrollTop : 0;
  sceneLayer.replaceChildren(card);
  sceneLayer.hidden = false;
  if (!first) card.scrollTop = top;
  if (first) { card.scrollTop = 0; const b = card.querySelector(".scene-choice:not([disabled])") || card.querySelector("button"); if (b) b.focus({ preventScroll: true }); }
}


// ---- Ending a day or a sprint (learning mode): day 1 needs some work first; finishing a sprint asks you to look at what is done
const needsWork = (s, to) => !!(s.guide && to === "STANDUP" && !s.guide.worked);
const confirmLayer = h("div", { id: "confirm", hidden: true });
document.body.append(confirmLayer);
function endStage(s, to) {
  if (!(s.guide && to === "REVIEW")) return cmd("advance_stage", { to });
  const items = s.pile.filter((c) => c.ticket && c.state !== "backlog");
  const group = (label, tone, list) => list.length ? h("div", { class: "cgroup " + tone }, h("b", {}, `${label} (${list.length})`), h("ul", {}, list.map((c) => h("li", {}, c.title)))) : null;
  const done = items.filter((c) => c.state === "done"), team = items.filter((c) => c.state === "delegated" || c.state === "returned"), todo = items.filter((c) => c.state === "pile" || c.state === "open");
  const close = () => { confirmLayer.hidden = true; confirmLayer.replaceChildren(); run.modal = null; };
  run.modal = "confirm";
  confirmLayer.replaceChildren(h("div", { class: "scene-card", role: "dialog", "aria-modal": "true", "aria-labelledby": "confirm-title" },
    h("h2", { id: "confirm-title" }, "Finish the Sprint?"),
    h("p", {}, "The Sprint ends and users see what was sent. Here is where your Sprint Backlog stands:"),
    group("Sent to users", "ok", done), group("With the team, not checked yet. It goes out unchecked", "warn", team), group("Not finished: back to the Product Backlog", "no", todo),
    h("p", { class: "muted small" }, "Only work that meets the Definition of Done counts toward the Increment."),
    h("div", { class: "row" }, h("button", { class: "primary", onclick: () => { close(); cmd("advance_stage", { to }); } }, "Finish the Sprint"), h("button", { onclick: () => { close(); run.sig = null; render(); } }, "Keep working"))));
  confirmLayer.hidden = false;
  confirmLayer.querySelector("button.primary").focus();
}

// A graphic, not a sentence: how likely each developer is to hand back work with a mistake (lower is better)
function riskBars(s) {
  const x = s.x, rows = ["dev1", "dev2"].map((d) => {
    const v = x.team ? x.team[d].bug_chance : 0, tone = v <= 0.2 ? "low" : v <= 0.4 ? "mid" : "high";
    const coach = (x.skill && x.skill[d]) || 0, debt = x.debt || 0;
    return h("div", { class: "riskrow" }, avatar(d, "calm"), h("b", {}, who(d)),
      h("div", { class: "risktrack", role: "img", "aria-label": `${who(d)}: ${Math.round(v * 100)} percent chance of a mistake` }, h("i", { class: tone })),
      h("span", { class: "riskpct" }, Math.round(v * 100) + "%"),
      coach > 0 ? h("span", { class: "chip good" }, "−" + Math.round(coach * 100) + "% coaching") : null,
      debt > 0 ? h("span", { class: "chip danger" }, "+" + Math.round(debt * 100) + "% skipped checks") : null);
  });
  const el = h("div", { class: "riskbars" }, h("h3", {}, "Chance of a mistake in work you hand over"), rows, h("small", { class: "muted" }, "Lower is better. Coaching lowers it. Skipped checks and untrue Daily Scrum answers raise it."));
  el.querySelectorAll(".risktrack i").forEach((bar, i) => { bar.style.width = Math.max(3, Math.round(100 * (x.team ? x.team[["dev1", "dev2"][i]].bug_chance : 0))) + "%"; });
  return el;
}

// ---- The guided first sprint: one small pointer at a time, each shown once, with a way to skip it all
const TOUR = [
  { id: "flow", when: (s) => s.stage === "PLANNING" && !s.guide.pending, at: () => ".stagecard", title: "How a Sprint goes", text: "Five moments, in order: Sprint Planning, Daily Scrum, Work, Sprint Review, Retrospective. The map on the left shows where you are. You are in Sprint Planning. Press the green button when you are ready." },
  { id: "daily", when: (s) => s.stage === "STANDUP" && !!s.standup, at: () => "[data-guide=standup]", title: "Daily Scrum", text: "Your teammate asks how the work is going. Pick an answer. The honest one is always the best: hidden problems make the team's later mistakes more likely." },
  { id: "tabs", when: (s) => s.stage === "BUILD" && !s.work && !s.guide.worked, at: () => ".tabstrip", title: "Your apps", text: "GitHab is where the work is, and where you will spend most of your time. Slackish is the team chat and the Daily Scrum. Play Storey shows what users say about your app." },
  { id: "pick", when: (s) => s.stage === "BUILD" && !s.work && !s.guide.worked, at: () => "#pile", title: "Your Sprint Backlog", text: "These are the items the team chose in Planning. Press Fix it myself on one, or give it to Ines or Tobi. You cannot end the day before you have started on something." },
  { id: "code", when: (s) => !!s.work, at: () => "pre.code", title: "Fixing an item", text: "Read 'What it should do' above, then click the line of code that does something different. Then pick the fix, press Test, tick the Done checklist honestly, and send it." },
  { id: "endday", when: (s) => s.stage === "BUILD" && !s.work && s.guide.worked, at: () => "[data-guide=end-day],[data-guide=end-sprint]", title: "Ending a day", text: "When you have done what you can for today, end the day. Tomorrow starts with another Daily Scrum. After day 2 the Sprint is finished and users see the result." },
  { id: "review", when: (s) => s.stage === "REVIEW" && !s.guide.pending, at: () => "[data-guide=to-retro]", title: "Sprint Review", text: "The team looks at what it made, and at what users said in Play Storey. Then the Retrospective: the team decides what to improve." },
  { id: "retro", when: (s) => s.stage === "RETRO" && !s.guide.pending, at: () => "[data-guide=next-sprint]", title: "Sprint complete", text: "The team picked one improvement and you can see how your coaching changed each developer's chance of a mistake. Then start the next Sprint." },
];
const tourLayer = h("div", { id: "tour", hidden: true, role: "note" });
document.body.append(tourLayer);
const tourOff = () => { try { return localStorage.getItem("tourOff:" + (me ? me.id : "x")) === "1"; } catch (_) { return false; } };
function syncTour(s) {
  const hide = () => { if (!tourLayer.hidden) { tourLayer.hidden = true; tourLayer.replaceChildren(); document.querySelectorAll(".tour-ring").forEach((e) => e.classList.remove("tour-ring")); run.tourId = null; } };
  if (!(s.x && s.x.calm && s.guide) || s.sprint !== 1 || run.modal || tourOff()) return hide();
  const step = TOUR.find((t) => !seen.has("tour:" + t.id) && t.when(s));
  if (!step) return hide();
  const target = [...document.querySelectorAll(step.at())].find((e) => e.offsetParent !== null);
  if (!target) return hide();
  document.querySelectorAll(".tour-ring").forEach((e) => { if (e !== target) e.classList.remove("tour-ring"); });
  target.classList.add("tour-ring");
  if (run.tourId !== step.id) {
    run.tourId = step.id;
    const n = TOUR.indexOf(step) + 1;
    tourLayer.replaceChildren(h("div", { class: "tourcard" }, h("small", {}, `Quick tour · ${n} of ${TOUR.length}`), h("b", {}, step.title), h("p", {}, step.text),
      h("div", { class: "row" }, h("button", { class: "primary", onclick: () => { markSeen("tour:" + step.id); run.tourId = null; syncTour(run.state); } }, "Got it"),
        h("button", { class: "quiet", onclick: () => { try { localStorage.setItem("tourOff:" + (me ? me.id : "x"), "1"); } catch (_) { /* storage can be blocked */ } syncTour(run.state); } }, "Skip the tour"))));
  }
  tourLayer.hidden = false;
  const r = target.getBoundingClientRect(), card = tourLayer.firstChild, ch = card.offsetHeight, cw = Math.min(340, innerWidth - 16);
  card.style.width = cw + "px";
  const below = r.bottom + 12, top = below + ch > innerHeight - 8 ? Math.max(8, r.top - ch - 12) : below;
  card.style.top = top + "px"; card.style.left = Math.max(8, Math.min(innerWidth - cw - 8, r.left)) + "px";
}
addEventListener("resize", () => run && run.state && syncTour(run.state));

function pushDeal(s, w) {
  const x = s.x, unticked = Object.values(w.dod).filter((v) => !v).length;
  const lines = [];
  if (unticked) lines.push(h("div", { class: "cost risk" }, x.calm ? `${unticked} box${unticked > 1 ? "es" : ""} unticked: this will not count as Done, and skipped checks make the team's next mistakes more likely.`
    : x.boss_live && x.boss === "friday_deploy" ? "Friday Deploy: tick every box before you can send."
    : `Sending with ${unticked} box${unticked > 1 ? "es" : ""} unticked: Suspicion +${x.prices.unticked_box} and a lower teamwork score.`));
  else if (!w.last_run) lines.push(h("div", { class: "cost risk" }, "You ticked 'The test passed' without testing. That counts as a dishonest checklist."));
  if (x.next_clean_factor < 1) lines.push(h("div", { class: "cost" }, `Users get bored of the same kind of fix: another clean one this sprint is worth ${Math.round(x.next_clean_factor * 100)}% of the first.`));
  if (x.last_stand) lines.push(h("div", { class: "cost good" }, "Last stand: an honest, clean fix now pulls your Suspicion back down."));
  if (x.mult) lines.push(h("div", { class: "cost good" }, `Points × ${x.mult.next_honest} if tested and fully ticked, × ${x.mult.next_other} otherwise.`));
  if (x.release) lines.push(h("div", { class: "cost" }, x.release.items.length >= x.release.max ? "Your release is full: send it to users first." : `It joins your release (${x.release.items.length + 1} of ${x.release.max}). Points arrive when you send the release.`));
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
  if (!t || !el || !run.state || !run.state.standup || run.modal) return;
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
    toast(ok ? "good" : "bad", ok ? "Every example gives the right answer!" : "Some examples give the wrong answer. Try a different fix.");
    if (ok) burst(14); else shakeScreen();
  }
  render();
}

function callCard(s) {
  return s.call ? h("div", { class: "callbar", role: "alert" }, h("span", { class: "ring", "aria-hidden": "true" }, ic("phone")),
    h("div", { class: "grow" }, h("b", {}, who(s.call.sender) + " is calling"), h("div", { class: "muted" }, "They're stuck. Answering takes 15 minutes. Ignoring it costs Energy.")),
    h("button", { class: "primary", "data-guide": "answer-call", disabled: !hasCard(s, "call"), title: "Answer" + needs(s, "call"), onclick: () => cmd("answer_call") }, hasCard(s, "call") ? "Answer" : "No Call card")) : null;
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

// ---- The live team board: drag a request onto a person (or use the buttons). Teammates work in real time.
const TEAM_INFO = { dev1: ["Ines", "Fast and careful"], dev2: ["Tobi", "Slow, more mistakes"] };
function dropZone(el, onDrop) {
  el.addEventListener("dragover", (e) => { if (run.dragCard) { e.preventDefault(); el.classList.add("over"); } });
  el.addEventListener("dragleave", () => el.classList.remove("over"));
  el.addEventListener("drop", (e) => { e.preventDefault(); el.classList.remove("over"); const id = run.dragCard; run.dragCard = null; if (id) onDrop(id); });
  return el;
}
function teamBoard(s) {
  const x = s.x, cb = x.combo;
  const next = s.day >= 2 ? ["REVIEW", "Finish the sprint", "end-sprint"] : ["STANDUP", "End the day", "end-day"];
  const short = s.day >= 2 && !x.goal.met;
  const me = dropZone(h("div", { class: "lane-card me" },
    h("div", { class: "lane-head" }, ic("c-heron", "lane-av"), h("div", {}, h("b", {}, "You"), h("small", {}, "Drop a request here to fix it yourself"))),
    x.calm ? (s.guide && !s.guide.worked && s.day < 2 ? h("p", { class: "muted small" }, "Start on an item first: fix it yourself, or give it to Ines or Tobi.") : null)
      : short ? h("p", { class: "cost risk" }, `Sprint goal not met yet (${x.goal.shipped} of ${x.goal.target}). Finishing now means a strike.`) : null,
    releaseEl(s),
    h("div", { class: "row" }, h("button", { "data-guide": next[2], onclick: () => endStage(s, next[0]), disabled: !!s.open_card || needsWork(s, next[0]), title: needsWork(s, next[0]) ? "Pick an item first: fix it yourself or give it to Ines or Tobi" : "" }, next[1]))),
    (id) => cmd("open_card", { card_id: id }));
  const mates = ["dev1", "dev2"].map((d) => {
    const m = x.team[d], [nm, trait] = TEAM_INFO[d];
    const body = !m.task ? h("p", { class: "lane-free" }, "Free. Drag a request here.")
      : [h("div", { class: "lane-task" }, ic("hammer"), " " + (m.title || "Working")),
        h("div", { class: "bar mprog" + (m.stuck ? " stuck" : ""), "data-dev": d }, h("i", {})),
        m.stuck ? h("div", { class: "stuckbox" }, h("b", {}, `${nm} is stuck!`),
          x.calm ? h("small", { class: "muted" }, "An impediment: removing it is the Scrum Master's job. Take your time.") : h("div", { class: "rescue", "data-dev": d }, h("i", {})),
          h("button", { class: "primary rescuebtn", "data-guide": "unblock:" + d, title: x.calm ? `Remove the blockage (${x.unblock_min} min of your time)` : `Unblock quickly for a bonus (${x.unblock_min} min of your time)`, onclick: () => cmd("unblock", { dev: d }) }, "Unblock"))
          : h("small", { class: "muted eta", "data-dev": d }, `About ${m.eta_min} min left`)];
    const el = h("div", { class: "lane-card" + (m.stuck ? " is-stuck" : m.task ? " busy" : " free"), "data-lane": d },
      h("div", { class: "lane-head" }, avatar(d, m.stuck ? "panicked" : "calm"), h("div", {}, h("b", {}, nm), h("small", {}, trait))), body);
    return m.task ? el : dropZone(el, (id) => cmd("delegate", { card_id: id, to: d }));
  });
  return h("section", { class: "board" },
    cb && cb.count ? h("div", { class: "combo hot" }, h("b", {}, `Combo ${cb.count}`), h("span", { class: "small" }, ` Next on-time finish pays ×${cb.next_mult}. A request getting louder breaks it.`)) : null,
    h("div", { class: "lanes3" }, me, mates));
}
// progress bars move every second without rebuilding the page
const TIER_LABEL = { perfect: "PERFECT", good: "GOOD", slow: "SLOW" };
function syncSpeed(s) {
  const box = document.querySelector(".speed[data-speed]");
  if (!box || !s.work || !s.work.speed) return;
  const sp = s.work.speed, frac = Math.max(0, 1 - sp.seconds / sp.good_s);
  const bar = box.querySelector(".speedbar"), fill = bar.firstChild;
  fill.style.width = Math.round(100 * frac) + "%";
  bar.querySelector(".mark").style.left = Math.round(100 * (1 - sp.perfect_s / sp.good_s)) + "%";   // the PERFECT zone is the part to the right of this mark
  box.className = "speed tier-" + sp.tier;
  const t = box.querySelector(".speedtier"), lbl = TIER_LABEL[sp.tier];
  if (t.textContent !== lbl) t.textContent = lbl;
  const m = box.querySelector(".speedmiss"), mt = sp.misses ? `${sp.misses} wrong: +${sp.misses * sp.penalty_s}s` : "";
  if (m.textContent !== mt) m.textContent = mt;
}

function syncTeam(s) {
  const team = s.x && s.x.team;
  if (!team) return;
  document.querySelectorAll(".rescue[data-dev]").forEach((b) => {
    const m = team[b.dataset.dev]; if (!m) return;
    b.firstChild.style.width = Math.max(0, Math.round(100 * (1 - m.stuck_min / s.x.stuck_limit))) + "%";
    b.classList.toggle("quick", m.stuck_min <= s.x.quick_min);
  });
  document.querySelectorAll(".mprog[data-dev]").forEach((b) => { const m = team[b.dataset.dev]; if (m) b.firstChild.style.width = Math.round(100 * m.progress) + "%"; });
  document.querySelectorAll(".stuckmin[data-dev]").forEach((e) => { const m = team[e.dataset.dev]; if (m && e.textContent !== String(m.stuck_min)) e.textContent = String(m.stuck_min); });
  document.querySelectorAll(".eta[data-dev]").forEach((e) => { const m = team[e.dataset.dev]; if (m && m.eta_min != null) e.textContent = `About ${m.eta_min} min left`; });
}

function githubApp(s) {
  const board = s.x && s.x.team && s.stage === "BUILD" && !s.work && !(run.reviewing && s.pile.some((c) => c.id === run.reviewing && c.review));
  if (board) return h("div", { class: "gh board-mode" }, h("aside", {}, pilePanel(s), intentsEl(s)), h("div", { class: "main" }, teamBoard(s)));
  const holdBacklog = s.x && s.x.calm && (s.stage === "PLANNING" || s.stage === "RETRO");
  const holdText = s.stage === "RETRO" ? "The Sprint is over. Unfinished items went back to the Product Backlog." : "Empty for now. The team fills it in Sprint Planning, and it shows up here when the Sprint begins.";
  return h("div", { class: "gh" }, h("aside", {}, holdBacklog ? h("section", { class: "card", id: "pile" }, h("h2", {}, ic("clipboard"), " Sprint Backlog"),
      h("p", { class: "muted" }, holdText)) : [lanesEl(s), pilePanel(s), intentsEl(s)]),
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

// The rating IS the average of the ten reviews shown. The server decides the rating; the reviews are drawn to agree with it:
// newest first, with the best outcomes given the higher stars. Older, plain reviews fill the list up to ten.
const BASE_GOOD = ["Does what it says.", "Solid app, works for me.", "Good value."];
const BASE_OKAY = ["Fine, a few rough edges.", "It's okay. Some things feel off.", "Works most of the time."];
const BASE_BAD = ["Too many problems for me.", "Keeps going wrong.", "Not happy with this one."];
const outcomeRank = (e) => { const l = String(e.label || "").toLowerCase(); return e.type !== "pushed" ? 0 : l.includes("clean") ? 4 : l.includes("accept") ? 3 : 2; };
function consistentReviews(s) {
  const L = 10, r = Math.max(1, Math.min(5, Number(s.meters.rating)));
  const real = reviewList().slice(-L).reverse().map(({ e, idx }) => ({ e, idx }));
  const items = real.concat(Array.from({ length: L - real.length }, (_, i) => ({ e: null, idx: 1000 + i })));
  const total = Math.max(L, Math.min(5 * L, Math.round(r * L)));
  const base = Math.min(5, Math.floor(total / L)), extra = total - base * L;
  const order = items.map((it, i) => ({ it, i, q: it.e ? outcomeRank(it.e) : 1 })).sort((a, b) => b.q - a.q || a.i - b.i);
  order.forEach((o, rank) => { o.it.k = Math.min(5, base + (rank < extra ? 1 : 0)); });
  return items;
}
function reviewBody(it) {
  const k = it.k, pick = (arr) => arr[it.idx % arr.length];
  if (!it.e) return pick(k >= 4 ? BASE_GOOD : k <= 2 ? BASE_BAD : BASE_OKAY);
  if (it.e.type === "push_blocked") return k <= 2 ? "The app crashes as soon as I open it." : "A crash showed up, but it is mostly fine.";
  if (it.e.type === "attack_check_resolved") return k <= 2 ? "I heard this app leaked user data. Uninstalling." : "There was a security scare, but it was handled.";
  const b = BLURBS[it.e.ticket];
  return b ? (k >= 4 ? b.good : k <= 2 ? b.bad : pick(BASE_OKAY)) : pick(k >= 4 ? BASE_GOOD : k <= 2 ? BASE_BAD : BASE_OKAY);
}

function playApp(s) {
  const r = Number(s.meters.rating), list = consistentReviews(s), shown = (list.reduce((a, it) => a + it.k, 0) / list.length);
  return h("div", { class: "play" },
    h("section", { class: "card store-head" }, h("div", { class: "app-icon", "aria-hidden": "true" }, ic("hammer")),
      h("div", {}, h("h2", {}, "Scrum Corp App"), h("div", { class: "muted" }, "Scrum Corp · Productivity"),
        h("div", { class: "big-rating" }, h("b", {}, shown.toFixed(1)), h("span", { class: "stars", "aria-label": shown.toFixed(1) + " out of 5 stars" }, stars(shown))),
        h("small", { class: "muted" }, `Average of the ${list.length} reviews below`))),
    h("section", { class: "card", "aria-label": "Reviews" }, h("h2", {}, "Reviews"), h("p", { class: "sub" }, "What the public says about your updates. Your app rating is the average of these."),
      list.map((it) => {
        const k = it.k, who = REVIEWERS[it.idx % REVIEWERS.length];
        return h("div", { class: "review" + (it.e && it.idx >= run.wallFresh ? " new" : "") }, h("span", { class: "rv rv" + (it.idx % 5), "aria-hidden": "true" }, who[0]),
          h("div", {}, h("b", {}, who), h("div", { class: "stars sm", "aria-label": k + " stars" }, stars(k), " ", h("span", { class: "muted" }, QUIP[k])), h("div", {}, reviewBody(it))));
      })));
}

function youtubeApp(s) {
  const card = ([icon, title, text, chip]) => h("div", { class: "w-card" }, h("span", { class: "w-icon" }, ic(icon, "w-cardic")),
    h("div", { class: "w-ctext" }, h("div", { class: "w-head" }, h("b", {}, title), chip ? h("span", { class: "w-chip info" }, chip) : null), h("span", {}, text)));
  return h("div", {},
    h("section", { class: "card", "aria-label": "Videos" }, h("h2", {}, "Learn something new"),
      h("p", { class: "sub" }, "Each short video teaches one topic (30 game minutes). Afterwards you can explain that kind of code honestly at standups."),
      h("div", { class: "videos" }, TUTORIALS.map((t, i) => {
        const got = s.unlocked.includes(t.id);
        return h("div", { class: "video" }, h("div", { class: "thumb th" + i, "aria-hidden": "true" }, ic(got ? "check" : "play")), h("b", {}, t.title),
          h("button", { onclick: () => cmd("watch_tutorial", { tutorial_id: t.id }), disabled: got || !hasCard(s, "learn"), title: needs(s, "learn") }, got ? "Watched" : hasCard(s, "learn") ? "Watch (30 min)" : "Needs a Learn card"));
      }))),
    h("details", { class: "card fold wordbook" }, h("summary", {}, ic("clipboard"), " Key words ", h("small", {}, `${CORE_TERMS.length} words`)),
      h("p", { class: "sub" }, "The words you need most. Tap any underlined word in the game for the others."),
      h("dl", {}, CORE_TERMS.map((k) => TERMS[k]).flatMap(([w, d]) => [h("dt", {}, w), h("dd", {}, d)]))),
    h("details", { class: "card fold welcome-like" }, h("summary", {}, ic("coin"), " How scoring works"),
      h("h3", {}, "What earns you points"), h("div", { class: "w-cards n4" }, SCORING.earn.map(card)),
      h("h3", {}, "What costs you"), h("div", { class: "w-cards n4" }, SCORING.lose.map(card)),
      h("p", { class: "w-note" }, ic("flag"), " " + SCORING.lose_when)));
}

// Skills you can buy any time with Points. Prices come from the server; wording stays free of numbers.
const SKILLS = {
  ai_assistant: ["Ask the AI", "robot", "Suggests a fix for you. It can be wrong."],
  keyboard_warrior: ["Keyboard Warrior", "bolt", "Reading and fixing code takes less time."],
  debug_master: ["Debug Master", "bug", "Tests are much faster."],
  security_scan: ["Security Scan", "search", "Tells you if a fix leaves a security hole. Tests can't."],
  focus_mode: ["Focus Mode", "bulb", "You start every morning with extra Energy."],
  team_training: ["Team Training", "chat", "Ines and Tobi make fewer mistakes."],
};
function skillCard(s, id, price) {
  const [name, icon, text] = SKILLS[id], own = s.perks.includes(id), noAi = id === "ai_assistant" && s.x && s.x.heat.includes("no_assistant");
  const short = price - s.meters.points;
  return h("div", { class: "skill" + (own ? " owned" : "") },
    h("span", { class: "skill-ic", "aria-hidden": "true" }, ic(icon)),
    h("div", { class: "skill-body" }, h("b", {}, name), h("span", {}, noAi ? "Switched off by Heat in this run." : text)),
    own ? h("span", { class: "skill-own" }, ic("check"), " Owned")
      : h("button", { class: short <= 0 ? "primary" : "", disabled: noAi || short > 0, title: short > 0 ? `You need ${short} more points` : "Buy this skill", onclick: () => cmd("buy_perk", { perk_id: id }) }, `${price} pts`));
}
function shopApp(s) {
  const list = (s.x ? s.x.perk_shop : [{ id: "ai_assistant", price: 150 }]).filter((p) => SKILLS[p.id]);
  return h("div", {},
    h("section", { class: "card", "aria-label": "Skills" }, h("h2", {}, ic("bolt"), " Skills"),
      h("p", { class: "sub" }, `Spend points on skills that stay with you for the whole run. You have ${s.meters.points} points.`),
      h("div", { class: "skills" }, list.map((p) => skillCard(s, p.id, p.price)))),
    s.x ? shopEl(s) : null);
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

// ------------------------------------------------------------ ORIGINAL (spec-breaking) mechanics (state.x.hand / release / mult / review)
const CARD_KINDS = {
  work: ["Work", "hammer", "Open a card, or fix a faulty change"], test: ["Test", "play", "Run the script, or test one change"],
  delegate: ["Delegate", "chat", "Hand a card to the team"], coach: ["Coach", "bulb", "Coach a teammate through a help call"],
  defer: ["Defer", "clock", "Push a card to later"], call: ["Call", "phone", "Answer a ringing call"],
  learn: ["Learn", "tv", "Watch a tutorial"], assist: ["Assist", "robot", "Ask the AI Assistant"],
};
const hasCard = (s, kind) => !s.x || !s.x.hand || s.x.hand.cards.includes(kind);
const needs = (s, kind) => hasCard(s, kind) ? "" : ` (needs a ${CARD_KINDS[kind][0]} card)`;

function handEl(s) {
  const hd = s.x && s.x.hand;
  if (!hd) return h("div", { class: "hand", "data-region": "hand", hidden: true });
  return h("div", { class: "hand", "data-region": "hand", "aria-label": "Your action cards" },
    h("span", { class: "lbl" }, "Hand"),
    hd.cards.length ? hd.cards.map((k) => h("span", { class: "acard k-" + k, title: CARD_KINDS[k][2] }, ic(CARD_KINDS[k][1]), " " + CARD_KINDS[k][0]))
      : h("span", { class: "muted small" }, "No cards left."),
    h("span", { class: "muted small" }, `Deck ${hd.deck} · discard ${hd.discard}`),
    s.stage === "BUILD" ? h("button", { class: "ult", "data-guide": "regroup", title: "Throw this hand away and draw a fresh one", onclick: () => cmd("regroup") }, `Regroup (${hd.regroup_min} min)`) : null);
}

function releaseEl(s) {
  const r = s.x && s.x.release;
  if (!r) return null;
  const n = r.items.length;
  return h("section", { class: "card release", "aria-label": "Release train" },
    h("h3", {}, ic("rocket"), ` Release train: ${n} of ${r.max} waiting`),
    n ? h("ul", {}, r.items.map((i) => h("li", {}, `${i.ticket} · ${i.points} pts`))) : h("p", { class: "muted small" }, "Pushes wait here until you ship the release."),
    h("p", { class: "small" }, n ? `Ship now: ${r.base} × ${r.mult} = ${Math.round(r.base * r.mult)} pts. One more push makes it × ${r.next_mult}. If anything in it is buggy, the bonus is lost.`
      : `Each extra push adds to the release bonus (× ${r.next_mult} for two). Anything left unshipped goes out at the review.`),
    s.stage === "BUILD" ? h("button", { class: "primary", "data-guide": "ship-release", disabled: !n, onclick: () => cmd("ship_release") }, ic("rocket"), ` Send the release to users (${r.ship_min} min)`) : null);
}

// Change-by-change review of returned work: the count is known, which change is faulty is not
function reviewDesk(s, c) {
  const r = c.review, R = s.x.review || {}, perks = s.perks.includes("ai_assistant");
  const trust = R.trust ? R.trust[r.assignee || "dev1"] : null;
  const fixed = r.changes.filter((ch) => ch.fixed).length, found = r.changes.filter((ch) => ch.shown === "faulty").length;
  return h("section", { class: "card", "aria-label": "Review submission" },
    h("h2", {}, ic("search"), ` Check ${who(r.assignee || "dev1")}'s work: ` + (c.title || c.ticket)),
    h("p", { class: "bossnote" }, r.faulty_count ? `${r.faulty_count} of ${r.changes.length} changes have a mistake. Find and fix them before users see it.` : `None of the ${r.changes.length} changes has a mistake. You can send it straight to users.`),
    h("div", { class: "changes" }, r.changes.map((ch, i) => h("div", { class: "change " + (ch.fixed ? "fixed" : ch.shown || "unknown") },
      h("b", {}, `Change ${i + 1}`), h("span", { class: "small" }, ch.fixed ? "Fixed" : ch.shown === "faulty" ? "Faulty" + (ch.sure ? "" : " (AI says)") : ch.shown === "ok" ? (ch.sure ? "Fine" : "Fine (AI says)") : "Not checked"),
      ch.fixed || (ch.sure && ch.shown === "ok") ? null : ch.shown === "faulty"
        ? h("button", { class: "primary", "data-guide": "fixchange", disabled: !hasCard(s, "work"), title: "Fix this change" + needs(s, "work"), onclick: () => cmd("review_fix", { card_id: c.id, index: i }) }, `Fix (${R.fix_min} min)`)
        : h("div", { class: "row" },
          h("button", { "data-guide": "inspect", disabled: !hasCard(s, "test"), title: "Run the tests on this change" + needs(s, "test"), onclick: () => cmd("review_inspect", { card_id: c.id, index: i, tool: "test" }) }, `Test ${R.inspect_min}m`),
          h("button", { disabled: trust === 0, title: "Ask the author. Costs their trust.", onclick: () => cmd("review_inspect", { card_id: c.id, index: i, tool: "ask" }) }, "Ask"),
          perks ? h("button", { disabled: !hasCard(s, "assist"), title: "AI Assistant: wrong 1 time in 5" + needs(s, "assist"), onclick: () => cmd("review_inspect", { card_id: c.id, index: i, tool: "assistant" }) }, "AI") : null)))),
    h("p", { class: "muted small" }, `Found ${found}, fixed ${fixed}.` + (trust != null ? ` ${NAMES[r.assignee || "dev1"]} trust: ${trust} of ${R.trust_max}. Low trust means more bugs from them.` : "")),
    h("div", { class: "row" },
      h("button", { class: "primary", "data-guide": "review-ship", onclick: () => { run.reviewing = null; cmd("review_ship", { card_id: c.id }); } }, ic("rocket"), " Send to users"),
      h("button", { onclick: () => { run.reviewing = null; cmd("review_send_back", { card_id: c.id }); } }, "Send it back"),
      h("button", { onclick: () => { run.reviewing = null; run.sig = null; render(); } }, "Close")));
}

function multEl(s) {
  const m = s.x && s.x.mult;
  return m ? h("span", { class: "chip", title: "Push points are multiplied by your process score and your honest-push streak." }, ic("star"), ` ×${m.next_honest} honest · streak ${m.streak}`) : null;
}

function hudEl(s) {
  const x = s.x;
  if (!x) return h("div", { class: "hud", "data-region": "hud", hidden: true });
  const boss = BOSSES[x.boss] || { name: x.boss, rule: "" };
  const mom = h("div", { class: "bar mom" }, h("i", {}));
  mom.firstChild.style.width = Math.min(100, 100 * x.momentum / x.momentum_full) + "%";
  const ready = x.momentum >= x.momentum_full && s.stage === "BUILD";
  const has = (k) => (x.features || []).includes(k);
  return h("div", { class: "hud", "data-region": "hud" },
    h("div", { class: "hud-row" },
      h("span", { class: "chip" }, ic("calendar"), ` Sprint ${s.sprint} of ${x.sprints_total}`),
      x.calm ? null : goalChip(x.goal),
      x.calm ? null : h("span", { class: "chip" }, ic("check"), " ", term("teamwork"), ` ${x.process_score}`),
      multEl(s),
      x.release ? h("span", { class: "chip", title: "Pushes waiting in the release" }, ic("rocket"), ` Release ${x.release.items.length}/${x.release.max}`) : null,
      x.last_stand ? h("span", { class: "chip danger" }, ic("warn"), " Last stand") : null,
      x.wave && !x.wave.failed ? h("span", { class: "chip danger wavechip" }, ic("alert"), ` Bug wave: ${x.wave.left} of ${x.wave.total} left`) : null,
      x.protected_min ? h("span", { class: "chip good" }, ic("check"), ` Protected ${x.protected_min} min`) : null,
      x.boss_live ? h("span", { class: "chip boss", title: boss.rule }, ic("flag"), ` Boss: ${boss.name}. ${boss.rule}`)
        : null),
    has("momentum") || x.practices.length ? h("div", { class: "hud-row" },
      has("momentum") ? [h("span", { class: "lbl" }, "Momentum"), mom] : null,
      !has("momentum") ? null : ready ? Object.keys(ULTIMATES).map((k) => h("button", { class: "ult", title: ULTIMATES[k].text, onclick: () => cmd("use_ultimate", { kind: k }) }, ULTIMATES[k].name))
        : h("span", { class: "muted small" }, "Fills when you help, test honestly, check work and tell the truth."),
      x.practices.length ? h("span", { class: "pracs" }, x.practices.map((p) => h("span", { class: "pchip" + (DUOS.has(p.id) ? " duo" : ""), title: (PRACTICES[p.id] || ["", ""])[1] }, practiceName(p.id) + (p.level > 1 ? " (Lv 2)" : "")))) : null) : null);
}

// Sprint goal: ship this many tickets yourself (or reviewed) before Review, or get a demotion warning
const goalChip = (g) => h("span", { class: "chip goalchip " + (g.met ? "good" : "goal"), title: g.text ? `Sprint Goal: ${g.text}` : "" },
  ic(g.met ? "check" : "flag"), " ", term("goal"), g.text ? `: ${g.text} (${g.shipped} of ${g.target} items)` : `: ${g.shipped} of ${g.target} sent`);

function intentsEl(s) {
  const x = s.x;
  if (!x || !(x.features || []).includes("intents")) return null;
  return h("section", { class: "card intents", "aria-label": "Coming up" }, h("h3", {}, ic("clock"), " Coming up"),
    x.intents.length ? h("ul", {}, x.intents.slice(0, 5).map((i) => h("li", {}, h("b", { class: "live-in", "data-at": String(s.clock_min + i.in_min) }, inText(s.clock_min + i.in_min, s.clock_min)), " " + i.text)))
      : h("p", { class: "muted small" }, "Nothing announced for the next two hours."));
}

function lanesEl(s) {
  if (!s.x || s.x.calm || !(s.x.features || []).includes("lanes")) return null;
  const n = (st) => s.pile.filter((c) => st.includes(c.state)).length;
  const lanes = [["To do", ["pile"]], ["With you", ["open"]], ["With the team", ["delegated"]], ["Back to check", ["returned"]], ["Done", ["done"]]];
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
      h("div", { class: "row" }, h("button", { class: "primary", "data-guide": "shop-take", disabled: full || (!sh.free && s.meters.points < o.price), onclick: () => cmd("buy_practice", { practice_id: o.id }) }, sh.free ? "Take it" : `Buy · ${o.price} pts`),
        h("button", { onclick: () => cmd("lock_offer", { practice_id: o.id }), title: "A locked offer stays when you reroll" }, o.locked ? "Unlock" : "Lock"))))),
    h("div", { class: "row" }, h("button", { onclick: () => cmd("reroll_shop"), disabled: s.meters.points < sh.reroll_price }, `Reroll (${sh.reroll_price ? sh.reroll_price + " pts" : "free"})`),
      full ? h("span", { class: "muted" }, "All practice slots are full.") : null),
    x.hand && !sh.free ? h("div", { class: "deckshop" }, h("h3", {}, "Your deck"), h("p", { class: "muted small" }, `Add a card for ${x.hand.add_price} pts or remove one for ${x.hand.remove_price} pts. A thinner deck draws what you need more often.`),
      h("div", { class: "decklist" }, Object.keys(CARD_KINDS).filter((k) => x.hand.deck_list[k] || x.hand.shop_cards.includes(k)).map((k) => h("div", { class: "deckrow" },
        h("span", { class: "acard k-" + k }, ic(CARD_KINDS[k][1]), ` ${CARD_KINDS[k][0]} × ${x.hand.deck_list[k] || 0}`),
        x.hand.shop_cards.includes(k) ? h("button", { disabled: s.meters.points < x.hand.add_price, onclick: () => cmd("add_card", { kind: k }) }, "+") : null,
        h("button", { disabled: !(x.hand.deck_list[k] > 0) || s.meters.points < x.hand.remove_price, onclick: () => cmd("remove_card", { kind: k }) }, "−"))))) : null);
}

// One big project per difficulty. Only the Easy project is playable so far.
const PROJECTS = [
  { level: "Easy", title: "The Checkout Fix", blurb: "Learn Scrum by running three Sprints", live: true },
  { level: "Medium", title: "Coming soon", blurb: "A bigger app, a bigger mess", live: false },
  { level: "Hard", title: "Coming soon", blurb: "Real users, real pressure", live: false },
];
const PATH_NODES = [
  { icon: "clipboard", label: "Sprint Planning", app: "github" },
  { icon: "chat", label: "Daily Scrum · day 1", app: "slack" },
  { icon: "hammer", label: "Work · day 1", app: "github" },
  { icon: "chat", label: "Daily Scrum · day 2", app: "slack" },
  { icon: "hammer", label: "Work · day 2", app: "github" },
  { icon: "flag", label: "Sprint Review", app: "github" },
  { icon: "bulb", label: "Retrospective", app: "github" },
];
// where the player is on the path (the day counter goes up when Build ends into the second Standup)
function pathIndex(s) {
  if (s.stage === "PLANNING") return 0;
  if (s.stage === "STANDUP") return s.day >= 2 ? 3 : 1;
  if (s.stage === "BUILD") return s.day >= 2 ? 4 : 2;
  return s.stage === "RETRO" ? 6 : 5;
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
      const sub = state === "now" && n.label.startsWith("Work") ? `${doneCards} of ${s.pile.length} done` : "";
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
const laterApp = (id) => !!(run && run.state && run.state.x && run.state.x.calm && run.state.sprint === 1 && (id === "youtube" || id === "shop"));
const attached = () => APPS.filter((a) => !run.notes.some((n) => n.id === a.id) && !laterApp(a.id));   // apps still in the browser
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

function openApp(id) { if (!run || isNote(id)) return; run.app = id; run.sig = null; render(); applyGuide(run.state); }
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
      if (Math.hypot(ev.clientX - sx, ev.clientY - sy) < 14) return;   // a click that wobbles a little is still a click
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
  const el = h("section", { class: `note app-${n.id}` + (n.min ? " min" : "") + (n.ping ? " ping" : ""), role: "group", "aria-label": app.name + " sticky note", "data-id": n.id },
    h("div", { class: "note-head", onpointerdown: (e) => startNoteDrag(e, n, el) },
      ic("pin"), h("span", { class: "ai", "aria-hidden": "true" }, ic(app.icon)), h("b", {}, app.name),
      b > 0 ? h("span", { class: "badge", "aria-label": badgeLabel(n.id, b) }, b) : null, h("span", { class: "grow" }),
      h("button", { class: "nbtn nmin", title: n.min ? "Open note" : "Shrink note", "aria-label": n.min ? "Open note" : "Shrink note", onclick: (e) => {
        n.min = !n.min; const btn = e.currentTarget; btn.title = btn.ariaLabel = n.min ? "Open note" : "Shrink note"; btn.replaceChildren(ic(n.min ? "open" : "minus")); el.classList.toggle("min", n.min);
      } }, ic(n.min ? "open" : "minus")),
      h("button", { class: "nbtn", title: "Put back in the browser", "aria-label": "Put back in the browser", onclick: () => dock(n.id) }, ic("undo"))),
    h("div", { class: "note-body" }, PAGES[n.id](s)));
  el.style.left = n.x + "px"; el.style.top = n.y + "px"; el.style.width = n.w + "px"; el.style.zIndex = 20 + n.z; el.style.setProperty("--tilt", n.tilt + "deg");
  el.addEventListener("pointerdown", () => { n.z = ++noteZ; el.style.zIndex = 20 + n.z; });
  // Remember the width you pulled it to. offsetWidth is the layout width: unlike getBoundingClientRect it ignores the tilt and any
  // grow-in animation, so it can never read "smaller" than the note really is. It only stores a number; it never redraws anything.
  if (typeof ResizeObserver !== "undefined") new ResizeObserver(() => { if (el.classList.contains("min")) return; const w = el.offsetWidth; if (w > 0 && Math.abs(w - n.w) > 2) n.w = w; }).observe(el);
  return el;
}

// ---- The browser frame is built once. After that render() patches only the regions whose data changed,
// so tabs, hover, scroll position and running animations are not thrown away every few seconds.
function badgeEl(id, s) { const n = badgeFor(id, s); return n > 0 ? h("span", { class: "badge", "aria-label": badgeLabel(id, n) }, n) : null; }
const popOut = () => { const app = APPS.find((a) => a.id === run.app); detach(app.id, innerWidth - 470 - 34 * run.notes.length, 150 + 34 * run.notes.length); };

function tabsEl(s) {
  const left = attached();
  return h("div", { class: "tabstrip", role: "tablist", "aria-label": "Open apps", "data-region": "tabs" }, left.map((a) => h("button", { class: `btab app-${a.id}` + (a.id === run.app ? " active" : ""), role: "tab", "aria-selected": String(a.id === run.app), "data-app": a.id, "data-guide": "tab:" + a.id,
    onpointerdown: (e) => startTabDrag(e, a.id), onclick: () => { if (!swallow) openApp(a.id); } },
    h("span", { class: "fav", "aria-hidden": "true" }, ic(a.icon)), h("span", { class: "tname" }, a.name), badgeEl(a.id, s))),
    h("button", { class: "nbtn pop", title: "Pop this app out as a sticky note", "aria-label": "Pop out as a sticky note", onclick: popOut }, ic("note")));
}
// unread counts change often: update them in place instead of rebuilding the tabs
function syncBadges(s) {
  document.querySelectorAll("#browser .btab").forEach((b) => {
    const id = b.dataset.app, n = badgeFor(id, s);
    b.classList.toggle("active", id === run.app); b.setAttribute("aria-selected", String(id === run.app));
    const pop = document.querySelector("#browser .tabstrip .pop"); if (pop) pop.disabled = attached().length <= 1;
    let el = b.querySelector(".badge");
    if (n > 0) { if (!el) { el = h("span", { class: "badge" }); b.append(el); } el.textContent = String(n); el.setAttribute("aria-label", badgeLabel(id, n)); }
    else if (el) el.remove();
  });
}
const buildAddr = () => h("div", { class: "addr" }, h("div", { class: "url" }, ic("lock"), h("span", { class: "urltext" })), buildMeters());
function syncAddr(s) {
  const u = document.querySelector("#browser .urltext"), url = APPS.find((a) => a.id === run.app).url;
  if (u && u.textContent !== url) u.textContent = url;
  syncMeters(s);
}
function shownGuide(s) {
  const g = guide(s);
  if (g.app && g.app !== run.app && !isNote(g.app)) return { ...g, step: `Open ${appName(g.app)}, then: ${g.step[0].toLowerCase() + g.step.slice(1)}`, target: "tab:" + g.app };
  return g;
}
const buildCoach = () => h("div", { class: "coach" }, h("span", { class: "heron", "aria-hidden": "true" }, ic("c-heron")),
  h("div", { class: "say" }, h("div", { class: "gline" }, h("span", { class: "nextlbl" }, "Next"), h("b", { class: "gstep" })), h("div", { class: "gwhy" })));
function syncCoach(s) {
  const g = shownGuide(s), st = document.querySelector("#browser .gstep"), why = document.querySelector("#browser .gwhy");
  if (!st) return;
  const key = "why:" + String(g.target || g.step).split(":")[0];
  if (run.whyKey && run.whyKey !== key) markSeen(run.whyKey);   // you moved on: you have read it
  run.whyKey = key;
  const showWhy = !!g.why && !seen.has(key);
  if (st.textContent !== g.step) st.textContent = g.step;
  st.title = g.why || "";
  const text = showWhy ? g.why : "";
  if (why.textContent !== text) why.textContent = text;
  why.hidden = !showWhy;
}
// A hand that shows the drag, so no sentence is needed. It plays until the first request has been handed to a teammate.
const demo = h("div", { id: "demo", "aria-hidden": "true", hidden: true }, h("span", { class: "demo-card" }), h("span", { class: "demo-dot" }));
document.body.append(demo);
let demoAnim = null, demoKey = null;
function stopDemo() { if (demoAnim) { demoAnim.cancel(); demoAnim = null; } demo.hidden = true; demoKey = null; }
function startDemo(from, to, key) {
  const a = from.getBoundingClientRect(), b = to.getBoundingClientRect();
  const x1 = a.left + a.width / 2, y1 = a.top + 22, x2 = b.left + b.width / 2, y2 = b.top + b.height / 2;
  if (demoKey === key && demoAnim) return;
  stopDemo(); demoKey = key; demo.hidden = false;
  if (REDUCED) { demo.style.transform = `translate(${x2}px, ${y2}px)`; return; }
  const at = (x, y, o) => ({ transform: `translate(${x}px, ${y}px)`, opacity: o });
  demoAnim = demo.animate([{ ...at(x1, y1, 0), offset: 0 }, { ...at(x1, y1, 1), offset: .12 }, { ...at(x1, y1, 1), offset: .3 }, { ...at(x2, y2, 1), offset: .75 }, { ...at(x2, y2, 1), offset: .88 }, { ...at(x2, y2, 0), offset: 1 }],
    { duration: 2800, iterations: Infinity, easing: "ease-in-out" });
}
function syncDemo(g) {
  const m = g.target && g.target.match(/^give:([^:]+):(dev\d)$/);
  if (!m || seen.has("demo_give") || run.modal) return stopDemo();
  const btn = document.querySelector(`[data-guide="${g.target}"]`), lane = document.querySelector(`[data-lane="${m[2]}"]`);
  const card = btn && btn.closest(".pile-item");
  if (!card || !lane) return stopDemo();
  startDemo(card, lane, g.target);
}

// The glow moves only when the target changes. It is never removed and re-added on every update (that restarted the animation).
function revealInPage(el) {
  const sc = el.closest(".page, .note-body");
  if (!sc) return;
  const r = el.getBoundingClientRect(), p = sc.getBoundingClientRect();
  if (r.top < p.top + 8 || r.bottom > p.bottom - 8) sc.scrollTo({ top: sc.scrollTop + (r.top - p.top) - p.height / 3, behavior: REDUCED ? "auto" : "smooth" });   // scroll the page only, never the whole window
}
function applyGuide(s) {
  const g = shownGuide(s);
  const el = g.target ? [...document.querySelectorAll(`[data-guide="${g.target}"]`)].find((e) => e.offsetParent !== null) : null;
  document.querySelectorAll(".guide-on").forEach((e) => { if (e !== el) e.classList.remove("guide-on"); });
  syncDemo(g);
  if (!el) return;
  if (!el.classList.contains("guide-on")) el.classList.add("guide-on");
  if (run.lastGuide !== g.target) { run.lastGuide = g.target; revealInPage(el); }
}
const callEl = (s) => h("div", { class: "callslot", "data-region": "call" }, callCard(s), run.error ? h("div", { class: "err pad", role: "alert" }, run.error) : null);
// One live page per app. Switching tabs only shows and hides them, so scroll position, typed text and
// open panels survive. A page is redrawn only when its own data changes (and only while it is on screen).
function syncPages(s) {
  const body = document.querySelector("#browser .winbody");
  if (!body) return;
  run.pageSigs = run.pageSigs || {};
  for (const a of APPS) {
    let el = body.querySelector(`.page[data-app="${a.id}"]`);
    if (el && isNote(a.id)) { el.remove(); run.pageSigs[a.id] = null; continue; }   // it lives in a sticky note now
    const show = a.id === run.app && !isNote(a.id);
    if (!el && !show) continue;
    if (!el) { el = h("div", { class: "page", role: "tabpanel", "aria-label": a.name, "data-app": a.id }); body.append(el); run.pageSigs[a.id] = null; }
    el.hidden = !show;
    if (!show) continue;
    const sig = JSON.stringify(PAGE_DEPS[a.id](s));
    if (sig === run.pageSigs[a.id]) continue;
    run.pageSigs[a.id] = sig;
    const keep = el.scrollTop, inner = [...el.querySelectorAll(".chat")].map((c) => c.scrollTop);
    el.replaceChildren(PAGES[a.id](s));
    el.scrollTop = keep;
    el.querySelectorAll(".chat").forEach((c, i) => { if (inner[i] != null) c.scrollTop = inner[i]; });
  }
}
const activePage = () => document.querySelector(`#browser .page[data-app="${run.app}"]`);
const notesLayer = (s) => h("div", { class: "notes" });
// Sticky notes are created once and then only patched: position, stacking, unread badge and, only when its own data changes, the page inside.
function syncNotes(s) {
  const layer = document.querySelector(".notes");
  if (!layer) return;
  const have = new Map([...layer.children].map((e) => [e.dataset.id, e]));
  for (const [id, e] of have) if (!run.notes.some((n) => n.id === id)) e.remove();
  for (const n of run.notes) {
    const el = have.get(n.id), sig = JSON.stringify(PAGE_DEPS[n.id](s));
    if (!el) { layer.append(noteEl(s, n)); n.sig = sig; continue; }
    el.classList.toggle("min", !!n.min); el.classList.toggle("ping", !!n.ping);
    if (!run.dragging) { el.style.left = n.x + "px"; el.style.top = n.y + "px"; }
    el.style.zIndex = 20 + n.z;
    const head = el.querySelector(".note-head"), b = badgeFor(n.id, s);
    let badge = head.querySelector(".badge");
    if (b > 0) { if (!badge) { badge = h("span", { class: "badge" }); head.insertBefore(badge, head.querySelector(".grow")); } if (badge.textContent !== String(b)) badge.textContent = String(b); badge.setAttribute("aria-label", badgeLabel(n.id, b)); }
    else if (badge) badge.remove();
    if (sig !== n.sig) {
      n.sig = sig;
      const body = el.querySelector(".note-body"), keep = body.scrollTop;
      body.replaceChildren(PAGES[n.id](s));
      body.scrollTop = keep;
    }
  }
}

function browserFrame(s) {
  return h("div", { class: "win", id: "browser" }, tabsEl(s), buildAddr(), buildCoach(), hudEl(s), handEl(s), callEl(s), h("div", { class: "winbody" }));
}

// what each page actually draws; a page is rebuilt only when this changes
const PAGE_DEPS = {
  slack: (s) => [run.lines.slice(-12).map((l) => l.id), s.stage, s.standup, s.x ? [s.x.standup_timer_s, s.x.prices] : null],
  github: (s) => [s.pile, s.stage, s.guide && [s.guide.backlog, s.guide.committed, s.guide.goal], s.x && [s.x.skill, s.x.debt, s.x.team && Object.values(s.x.team).map((m) => m.bug_chance)],
    s.work && { ...s.work, speed: s.work.speed && s.work.speed.misses }, s.open_card, s.day, s.perks, run.runs, s.standup,
    s.x ? [s.x.shop, s.x.intents.map((i) => [i.text, i.kind]), s.x.move_costs, s.x.retro_left, s.x.next_clean_factor, s.x.practices, s.meters.points, s.x.goal,
      s.x.hand, s.x.release, s.x.mult, s.x.review, run.reviewing,
      s.x.team && Object.values(s.x.team).map((m) => [m.task, m.stuck]), s.x.combo] : null],
  play: (s) => [Number(s.meters.rating), reviewList().length],
  youtube: (s) => [s.unlocked],
  shop: (s) => [s.perks, s.x ? [s.x.shop, s.meters.points, s.x.heat, s.x.hand] : null],
};
const REGIONS = {
  tabs: { sig: () => attached().map((a) => a.id).join(), build: tabsEl },
  hud: { sig: (s) => JSON.stringify(s.x ? [s.sprint, s.stage, s.x.clock_running, s.x.process_score, s.x.style.rank, s.x.last_stand,
    s.x.protected_min, s.x.momentum, s.x.practices.map((p) => [p.id, p.level]), s.x.boss_live, s.x.goal, s.x.mult, s.x.release && s.x.release.items.length, s.x.wave] : null), build: hudEl },
  hand: { sig: (s) => JSON.stringify(s.x && s.x.hand ? [s.x.hand, s.stage] : null), build: handEl },
  call: { sig: (s) => JSON.stringify(s.call || null) + "|" + (run.error || "") + "|" + hasCard(s, "call"), build: callEl },
  rail: { sig: (s) => [pathIndex(s), s.sprint, s.pile.filter((c) => c.state === "done").length, s.pile.length].join(), build: roadmap },
};
const scrollables = () => [...document.querySelectorAll(".note-body")];

// Everything that only needs its text, width or class changed: patched in place, never rebuilt.
function syncChrome(s) {
  syncAddr(s); syncCoach(s); syncBadges(s); syncTeam(s); syncLive(s); syncSpeed(s);
}

function updateScreen(s) {
  const frame = document.getElementById("browser");
  if (!frame) {                                   // first time on this screen: build everything once
    mount(h("div", { class: "gamelayout" }, roadmap(s), browserFrame(s)), notesLayer(s));
    run.regs = Object.fromEntries(Object.entries(REGIONS).map(([k, r]) => [k, r.sig(s)])); run.pageSigs = {};
    syncPages(s); syncChrome(s); syncNotes(s);
    return;
  }
  const keep = scrollables().map((e) => e.scrollTop);   // a rebuilt list must not jump back to the top
  for (const [name, r] of Object.entries(REGIONS)) {
    const sig = r.sig(s);
    if (sig === run.regs[name]) continue;
    run.regs[name] = sig;
    document.querySelector(`#root [data-region="${name}"]`).replaceWith(r.build(s));
  }
  syncPages(s);
  syncChrome(s);
  syncNotes(s);
  scrollables().forEach((e, i) => { if (keep[i]) e.scrollTop = keep[i]; });
}

function render() {
  if (!run || !run.state || run.dragging) return;   // never rebuild the screen under a drag
  const s = run.state;
  const sig = JSON.stringify({ ...s, clock_min: 0, day_used_min: 0 }) + run.lines.length + run.wall.length + JSON.stringify(run.runs || null) + (run.error || "");
  if (sig === run.sig && document.getElementById("meters")) { syncMeters(s); syncLive(s); return; }  // nothing changed but the clock
  run.sig = sig;
  // a new stage opens the app where that stage happens (or nudges its note if you pulled it out)
  if (!run.app) run.app = s.stage === "STANDUP" ? "slack" : "github";
  else if (run.lastStage && run.lastStage !== s.stage && ["PLANNING", "STANDUP", "BUILD"].includes(s.stage)) {
    const to = s.stage === "STANDUP" ? "slack" : "github";
    if (isNote(to)) pingNote(to);
    else if (to !== run.app) run.app = to;
  }
  if (isNote(run.app)) run.app = attached()[0].id;
  const at = pathIndex(s);
  const lastId = run.lines.length ? run.lines[run.lines.length - 1].id : 0;
  run.freshAfter = run.slackSeen ?? 0; run.wallFresh = run.playSeen ?? 0;   // only lines you have not seen yet animate in
  updateScreen(s);
  syncScene(s);
  applyGuide(s);
  if (!run.modal && !(s.x && s.x.calm)) { const c = conceptFor(s); if (c) showConcept(c); }
  syncTour(s);
  if (visible("slack")) run.slackSeen = lastId;
  if (visible("play")) run.playSeen = run.wall.length;
  if (run.lastStage && run.lastStage !== s.stage && !REDUCED) { const d = activePage(); if (d) { d.classList.add("swap"); setTimeout(() => d.classList.remove("swap"), 700); } }
  run.lastStage = s.stage; run.lastApp = run.app; run.lastPath = at;
}

async function debrief() {
  timers.forEach(clearInterval);
  const d = await api(`/api/v1/runs/${run.id}/debrief`);
  const names = { win: d.x && d.x.scrum ? "You ran all " + d.x.sprints_played + " Sprints" : d.x ? "You survived all " + d.x.sprints_played + " sprints" : "You survived the sprint", lose_rating: "Fired: Rating fell below 2.0", lose_cover: "Exposed: Cover hit 100", lose_warnings: "Demoted twice" };
  mount(h("section", { class: "card narrow" }, h("div", { class: "hero", "aria-hidden": "true" }, ic(d.ending === "win" ? "c-heron-cheer" : "c-heron-oops")), h("h2", {}, names[d.ending] || d.ending),
    h("table", {}, (d.x && d.x.scrum ? [["App rating", Number(d.rating).toFixed(1)], ["Points", d.points]]
      : [["Rating", Number(d.rating).toFixed(2)], ["Cover", d.cover], ["Points", d.points], ["Process score", d.process_score], ["Gap (rating % minus process)", d.gap]]).map(([k, v]) => h("tr", {}, h("th", {}, k), h("td", {}, v)))),
    d.x && d.x.scrum ? null : h("p", { class: "muted" }, "Points never count toward your process score: honest process does."),
    d.x ? xDebrief(d.x) : null,
    h("div", { class: "row" }, h("button", { class: "primary", onclick: () => questions("post", () => mount(h("section", { class: "card narrow" }, h("h2", {}, "Thanks for playing")))) }, "Take the post-test"), h("button", { onclick: setupRun }, "Play again"))));
  if (d.ending === "win") { lastPt = null; burst(40); setTimeout(() => burst(30), 350); }
  if (d.x) showLeaderboard(d.x.seed);
}

function xDebrief(x) {
  if (x.scrum) return h("div", { class: "xdeb" },
    h("div", { class: "row" }, h("span", { class: "chip good" }, ic("check"), ` Scrum questions right first try: ${x.scrum.first_try} of ${x.scrum.asked}`)),
    h("h3", {}, "What the team says"), x.story.map((l) => h("p", { class: "story" }, l)),
    x.practices.length ? h("p", { class: "muted" }, "Practices: " + x.practices.map(practiceName).join(", ")) : null,
    null);
  return h("div", { class: "xdeb" },
    x.scrum ? h("div", { class: "row" }, h("span", { class: "chip good" }, ic("check"), ` Scrum questions right first try: ${x.scrum.first_try} of ${x.scrum.asked}`)) : null,
    h("div", { class: "row" }, h("span", { class: "chip" }, ic("coin"), ` Run score ${x.run_score}` + (x.heat.length ? ` (Heat ${x.heat.length})` : "")),
      h("span", { class: "chip" }, ic("star"), " Style " + (x.style.map((r) => r.rank).join(" · ") || "-")),
      h("span", { class: "chip" + (x.near_miss ? " danger" : "") }, ic("search"), ` Highest Cover ${x.max_cover}` + (x.near_miss ? " · close call" : "")),
      x.clutches ? h("span", { class: "chip good" }, ic("check"), ` ${x.clutches} clutch save${x.clutches > 1 ? "s" : ""}`) : null,
      x.goals.length ? h("span", { class: "chip" }, ic("flag"), " Goals " + x.goals.map((g) => g.met ? "met" : "missed").join(" · ")) : null),
    h("h3", {}, "What the team says"), x.story.map((l) => h("p", { class: "story" }, l)),
    x.practices.length ? h("p", { class: "muted" }, "Practices: " + x.practices.map(practiceName).join(", ")) : null,
    h("p", { class: "muted" }, `Challenge code ${x.seed}: share it so classmates can play the same sprints.`),
    h("div", { id: "lb" }));
}

// O5: public leaderboard for this challenge code
async function showLeaderboard(seed) {
  const box = document.getElementById("lb");
  if (!box) return;
  try {
    const lb = await api("/api/v1/leaderboard?seed=" + seed);
    box.replaceChildren(h("h3", {}, ic("chest"), ` Leaderboard for code ${seed}`),
      h("table", {}, h("tr", {}, ["#", "Player", "Run score", "Style", "Ending"].map((x) => h("th", {}, x))),
        lb.top.map((r) => h("tr", { class: r.you ? "you" : "" }, h("td", {}, r.place), h("td", {}, r.name + (r.you ? " (you)" : "")), h("td", {}, r.score), h("td", {}, r.style), h("td", {}, r.ending)))),
      h("p", { class: "muted" }, lb.your_best ? `Your best: #${lb.your_best.place} of ${lb.players} · the median score is ${lb.median}.` : `${lb.players} finished runs on this code.`));
  } catch (_) { box.replaceChildren(); }   // leaderboard switched off
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
