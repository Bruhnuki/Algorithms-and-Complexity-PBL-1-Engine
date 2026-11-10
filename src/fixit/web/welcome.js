// Welcome flow: a short, friendly intro shown right after sign-up, before consent and the quiz.
// It only explains the game. The numbers below mirror content/balance.yaml and a test keeps them in sync; no rules run here.
// app.js passes in its own h() (text nodes only), ic() and mount(), so this file never touches innerHTML.

const card = (icon, title, text, chip, tone = "good") => ({ icon, title, text, chip, tone });

const STEPS = [
  { kind: "hello", pose: "c-heron", say: "Hi! I'm Herb, your coach." },
  { kind: "hello", pose: "c-heron-cheer", say: "Let's get you ready." },
  { kind: "cards", pose: "c-heron", say: "Scrum means building in small steps.", cards: [
    card("calendar", "Sprint", "A short work round. Yours lasts two days."),
    card("c-marlo", "Product Owner", "Marlo decides what matters."),
    card("c-ines", "Developers", "Ines and Tobi build the app."),
    card("star", "Scrum Master", "That's you. You help the team."),
  ] },
  { kind: "cards", pose: "c-heron", say: "You lead the team and review its work.", cards: [
    card("chat", "Lead", "Run standups. Unblock people."),
    card("branch", "Review", "Read the clues, then push or hold."),
    card("search", "Stay hidden", "You can't really code. Bluffing raises Cover."),
    card("star", "Mind your Rating", "Public reviews judge your updates."),
  ] },
  { kind: "cards", pose: "c-heron", say: "Your teammates are AI.", cards: [
    card("chat", "Chatty teammates", "Their lines come from an AI model."),
    card("robot", "AI Assistant", "Suggests fixes, but it's wrong about 1 time in 5.", "150 pts", "info"),
    card("check", "Fair rules", "The AI only chats. Game rules set your score."),
  ] },
  { kind: "cards", pose: "c-heron-cheer", say: "How you earn points.", cards: [
    card("rocket", "Clean push", "Tests pass, nothing risky.", "+100 pts"),
    card("play", "Good enough push", "Works, but not perfect.", "+50 pts"),
    card("chat", "Honest standup", "Accurate answers lower your Cover.", "Cover −10"),
    card("check", "Good process", "Standups, coaching and reviews count up to 3 times each.", "Process score", "info"),
  ] },
  { kind: "cards", pose: "c-heron", say: "What costs you.", cards: [
    card("bug", "Broken push", "A crash blocks it.", "−30 pts", "bad"),
    card("alert", "Security hole", "Found at review.", "−150 pts, −0.8 Rating", "bad"),
    card("search", "Bluffing", "Vague: Cover +5. Wrong: Cover +15. Caught out: Cover +10.", "Cover up", "bad"),
    card("clipboard", "Skipped checklist", "Each unticked box: Cover +5.", "Cover up", "bad"),
  ], note: "You lose if Rating drops below 2.0, Cover reaches 100, or you get 2 warnings." },
  { kind: "pick", pose: "c-heron", say: "Pick a project.", cards: [
    { id: "easy", level: "Easy", name: "The Coupon Shop", live: true, text: "Fix the bugs and ship without being found out.", meta: "One sprint, two days" },
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
