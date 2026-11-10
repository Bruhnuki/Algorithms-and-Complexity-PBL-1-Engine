// Welcome flow: a short, friendly intro shown right after sign-up, before consent.
// It explains what the program is, who the team is and how a Sprint goes. The story lives in the first project scene. Scoring is taught during play (see guide.js); no rules run here.
// app.js passes in its own h() (text nodes only), ic() and mount(), so this file never touches innerHTML.

const card = (icon, title, text, chip, tone = "good") => ({ icon, title, text, chip, tone });

const STEPS = [
  { kind: "hello", pose: "c-heron", say: "Hi! I'm Herb, your coach." },
  { kind: "hello", pose: "c-heron", say: "This is a game where you learn Scrum by actually doing it, not by reading about it." },
  { kind: "hello", pose: "c-heron", say: "You'll play the Scrum Master of a small team, helping them get work done one short round at a time. We call those rounds Sprints." },
  { kind: "hello", pose: "c-heron", say: "Don't worry, I'll explain each idea as we go." },
  { kind: "cards", pose: "c-heron", say: "Let me introduce your team.", cards: [
    card("c-marlo", "Marlo, Product Owner", "Decides what matters most. Sends you requests."),
    card("c-ines", "Ines, Developer", "Writes code. Tired, very good."),
    card("c-tobi", "Tobi, Developer", "Writes code. New, often stuck."),
  ] },
  { kind: "flow", pose: "c-heron-cheer", say: "Here's how every Sprint goes." },
  { kind: "hello", pose: "c-heron", say: "Before the real thing, we'll play a short practice Sprint together. I'll walk you through every part of the screen." },
  { kind: "hello", pose: "c-heron", say: "After each Sprint, we'll look back at what your choices did, so you can try something different next time." },
  { kind: "pick", pose: "c-heron", say: "Pick a project.", cards: [
    { id: "easy", level: "Easy", name: "The Checkout Fix", live: true, text: "Learn what Scrum really is by running three Sprints.", meta: "3 Sprints · no timers" },
    { id: "medium", level: "Medium", live: false, text: "A bigger app and a bigger mess." },
    { id: "hard", level: "Hard", live: false, text: "Real users and real pressure." },
  ] },
];

// The Sprint as a flowchart: a few words per node, an arrow back to the start for the next Sprint. Used by the intro and the "main Sprint" screen.
export const SPRINT_NODES = [
  { icon: "clipboard", label: "Sprint Planning" }, { icon: "chat", label: "Daily Scrum" }, { icon: "hammer", label: "Work" },
  { icon: "flag", label: "Sprint Review" }, { icon: "bulb", label: "Retrospective" },
];
export function flowChart({ h, ic }, nodes, loopText, here = -1) {
  return h("div", { class: "fc" + (here >= 0 ? " has-here" : "") },
    h("ol", { class: "fc-row" }, nodes.map((n, i) => h("li", { class: "fc-node" + (i === here ? " here" : "") }, i === here ? h("span", { class: "fc-here" }, "YOU ARE HERE") : null,
      h("span", { class: "fc-ic" }, ic(n.icon)), h("b", {}, n.label), n.sub ? h("small", {}, n.sub) : null))),
    h("div", { class: "fc-loop", role: "img", "aria-label": loopText }, h("span", {}, loopText)));
}

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

  const flow = (s) => h("section", { class: "w-lesson" }, ask(s), flowChart({ h, ic }, SPRINT_NODES, "Next Sprint"));
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
    stage.replaceChildren(s.kind === "hello" ? hello(s) : s.kind === "pick" ? pick(s) : s.kind === "flow" ? flow(s) : cards(s));
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
