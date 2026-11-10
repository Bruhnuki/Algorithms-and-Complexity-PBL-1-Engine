// Welcome flow: a short, friendly intro shown right after sign-up, before consent and the quiz.
// It only sets the scene: story, team, how a round works. Scoring is taught during play (see guide.js); no rules run here.
// app.js passes in its own h() (text nodes only), ic() and mount(), so this file never touches innerHTML.

const card = (icon, title, text, chip, tone = "good") => ({ icon, title, text, chip, tone });

const STEPS = [
  { kind: "hello", pose: "c-heron", say: "Hi! I'm Herb, your coach." },
  { kind: "cards", pose: "c-heron", say: "Here's your story.", cards: [
    card("alert", "The shop app is in trouble", "Customers leave at checkout because the prices come out wrong."),
    card("star", "You are the Scrum Master", "You do not code and you do not set priorities. You help the team work the Scrum way."),
    card("flag", "Three Sprints to learn it", "Each Sprint has the same five moments real teams use. Nothing is timed."),
  ] },
  { kind: "cards", pose: "c-heron", say: "Meet your team.", cards: [
    card("c-marlo", "Marlo, Product Owner", "Decides what matters most. Sends you requests."),
    card("c-ines", "Ines, Developer", "Writes code. Tired, very good."),
    card("c-tobi", "Tobi, Developer", "Writes code. New, often stuck."),
  ] },
  { kind: "cards", pose: "c-heron-cheer", say: "How the game works.", cards: [
    card("calendar", "Five Scrum moments", "Sprint Planning, the Daily Scrum, the work, the Sprint Review and the Retrospective."),
    card("chat", "Short scenes", "Each moment starts with a quick scene and one question. A wrong answer just explains why."),
    card("check", "I'll guide every step", "Take your time. Look for the glowing button."),
  ] },
  { kind: "pick", pose: "c-heron", say: "Pick a project.", cards: [
    { id: "easy", level: "Easy", name: "The Checkout Fix", live: true, text: "Learn what Scrum really is by running three Sprints.", meta: "3 Sprints · no timers" },
    { id: "medium", level: "Medium", live: false, text: "A bigger app and a bigger mess." },
    { id: "hard", level: "Hard", live: false, text: "Real users and real pressure." },
  ] },
];

export function runWelcome({ h, ic, mount, onDone }) {
  let at = 0, project = "easy";

  const fill = h("i", {});
  const progress = h("div", { class: "w-progress", role: "progressbar", "aria-label": "Intro progress", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": "0" }, fill);
  const stage = h("div", { class: "w-stage", "aria-live": "polite" });
  const finish = () => { try { sessionStorage.setItem("project", project); } catch (_) { /* storage can be blocked */ } onDone(); };
  const back = h("button", { class: "w-back", "aria-label": "Go back", onclick: () => { if (at > 0) { at--; show(false); } } }, ic("chev-l"));
  const next = h("button", { class: "w-go", onclick: () => { if (at < STEPS.length - 1) { at++; show(false); } else finish(); } }, "Continue");

  const mascot = (pose) => h("div", { class: "w-stand" }, ic(pose, "w-mascot"));
  const bubble = (text, cls) => h("div", { class: "w-bubble " + cls, tabindex: "-1" }, text);
  const ask = (s) => h("div", { class: "w-ask" }, mascot(s.pose), bubble(s.say, "w-side"));
  const head = (title, chip, tone) => h("div", { class: "w-head" }, h("b", {}, title), chip ? h("span", { class: "w-chip " + tone }, chip) : null);

  const hello = (s) => h("section", { class: "w-hello" }, bubble(s.say, "w-above"), mascot(s.pose));

  const cards = (s) => h("section", { class: "w-lesson" }, ask(s),
    h("div", { class: "w-cards n" + s.cards.length }, s.cards.map((c) => h("div", { class: "w-card" },
      h("span", { class: "w-icon" }, ic(c.icon, "w-cardic")),
      h("div", { class: "w-ctext" }, head(c.title, c.chip, c.tone), h("span", {}, c.text))))),
    s.note ? h("p", { class: "w-note" }, ic("flag"), " " + s.note) : null);

  const pick = (s) => {
    const group = h("div", { class: "w-cards n3", role: "radiogroup", "aria-label": "Projects" });
    const paint = () => group.querySelectorAll(".w-pick").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.id === project)));
    s.cards.forEach((c) => group.append(h("button", { class: "w-card w-pick" + (c.live ? "" : " locked"), role: "radio", "data-id": c.id, "aria-checked": String(c.id === project), disabled: !c.live,
      onclick: () => { project = c.id; paint(); } },
      h("span", { class: "w-icon" }, ic(c.live ? "hammer" : "lock", "w-cardic")),
      h("div", { class: "w-ctext" }, head(c.live ? `${c.level}: ${c.name}` : c.level, c.live ? null : "Coming soon", "info"), h("span", {}, c.text), c.meta ? h("small", {}, c.meta) : null))));
    return h("section", { class: "w-lesson" }, ask(s), group);
  };

  function show(first) {
    const s = STEPS[at], last = at === STEPS.length - 1;
    stage.replaceChildren(s.kind === "hello" ? hello(s) : s.kind === "pick" ? pick(s) : cards(s));
    stage.classList.toggle("is-hello", s.kind === "hello");
    const pct = s.kind === "hello" ? 0 : Math.round(100 * (at - 1) / (STEPS.length - 1));
    fill.style.width = pct + "%"; progress.setAttribute("aria-valuenow", String(pct)); progress.classList.toggle("quiet", s.kind === "hello");
    back.style.visibility = at === 0 ? "hidden" : "visible";
    next.textContent = last ? "Start the game" : "Continue";
    if (!first) (stage.querySelector(".w-bubble") || stage).focus({ preventScroll: true });   // read the new screen out
    window.scrollTo(0, 0);
  }

  mount(h("div", { class: "welcome" },
    h("div", { class: "w-top" }, back, progress, h("button", { class: "w-skip", onclick: finish }, "Skip")),
    stage, h("div", { class: "w-foot" }, next)));
  show(true);
}
