// Landing page: reveal on scroll, rotating headline, and a one-question demo. No game rules here.
const root = document.documentElement;
const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
root.classList.add("js");

// reveal sections as they scroll into view
const io = new IntersectionObserver((entries) => {
  for (const e of entries) if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
}, { threshold: 0.15 });
document.querySelectorAll(".reveal").forEach((el) => io.observe(el));

// rotating "Today you will ..." line
const swap = document.getElementById("swap");
const lines = ["fix a bug", "calm a developer", "dodge a hacker", "survive Friday", "bluff a standup", "watch a video to hide"];
let i = 0;
if (swap && !REDUCED) setInterval(() => {
  i = (i + 1) % lines.length;
  swap.textContent = lines[i];
  swap.style.animation = "none"; void swap.offsetWidth; swap.style.animation = "";
}, 2300);

// confetti from the spot you pressed
const fx = document.createElement("div");
fx.id = "fx"; fx.setAttribute("aria-hidden", "true");
document.body.append(fx);
function burst(x, y, n = 26) {
  if (REDUCED) return;
  for (let k = 0; k < n; k++) {
    const p = document.createElement("i");
    p.className = "conf c" + (k % 5);
    const a = Math.random() * Math.PI * 2, d = 60 + Math.random() * 120;
    p.style.left = x + "px"; p.style.top = y + "px";
    p.style.setProperty("--dx", Math.cos(a) * d + "px"); p.style.setProperty("--dy", Math.sin(a) * d - 60 + "px"); p.style.setProperty("--r", Math.random() * 720 - 360 + "deg");
    p.addEventListener("animationend", () => p.remove());
    fx.append(p);
  }
}

// try-one-question widget
const fb = document.getElementById("fb");
document.querySelectorAll(".choice").forEach((btn) => btn.addEventListener("click", (ev) => {
  if (btn.dataset.ok === "yes") {
    btn.classList.add("right");
    document.querySelectorAll(".choice").forEach((b) => { b.disabled = true; });
    fb.className = "feedback good";
    fb.textContent = "Yes! The Product Owner decides the order. Your team just got a little less confused.";
    const r = btn.getBoundingClientRect();
    burst(ev.clientX || r.left + r.width / 2, ev.clientY || r.top);
  } else {
    btn.classList.remove("wrong"); void btn.offsetWidth; btn.classList.add("wrong");
    fb.className = "feedback bad";
    fb.textContent = "Not quite. Try another one.";
  }
}));
