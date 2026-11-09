// Example requests copied from the demo scripts in README-pbl-engine.md.
const EXAMPLES = {
  context_chaining: {
    job_id: "context-demo-01",
    algorithm: "context_chaining",
    input: {
      current_stage: "BUILD",
      token_budget: 1000,
      mode: "auto",
      segments: [
        { id: "planning-goal", tokens: 180, relevance: 0.95, stage: "PLANNING", pinned: true },
        { id: "standup-update", tokens: 220, relevance: 0.75, stage: "STANDUP" },
        { id: "build-decision", tokens: 300, relevance: 0.90, stage: "BUILD" },
        { id: "old-planning-note", tokens: 250, relevance: 0.40, stage: "PLANNING" },
        { id: "review-feedback", tokens: 200, relevance: 0.85, stage: "REVIEW" },
      ],
    },
  },
  learning_gain: {
    job_id: "cohort-demo-10",
    algorithm: "learning_gain",
    input: {
      max_score: 100,
      students: [
        { id: "S01", pre: 45, post: 75 },
        { id: "S02", pre: 50, post: 80 },
        { id: "S03", pre: 60, post: 85 },
        { id: "S04", pre: 40, post: 70 },
        { id: "S05", pre: 55, post: 78 },
        { id: "S06", pre: 35, post: 65 },
        { id: "S07", pre: 70, post: 90 },
        { id: "S08", pre: 48, post: 76 },
        { id: "S09", pre: 52, post: 82 },
        { id: "S10", pre: 42, post: 72 },
      ],
      bootstrap_B: 1000,
      seed: 7,
    },
  },
};

const requestBox = document.getElementById("request");
const responseBox = document.getElementById("response");
const statusBadge = document.getElementById("status");
const submitButton = document.getElementById("submit");

function selectedAlgorithm() {
  return document.querySelector('input[name="algorithm"]:checked').value;
}

function loadExample() {
  requestBox.value = JSON.stringify(EXAMPLES[selectedAlgorithm()], null, 2);
  responseBox.textContent = "Submit a request to see the response.";
  statusBadge.textContent = "";
  statusBadge.className = "status";
}

function showStatus(text, ok) {
  statusBadge.textContent = text;
  statusBadge.className = "status " + (ok ? "ok" : "error");
}

async function submitRequest() {
  submitButton.disabled = true;
  responseBox.textContent = "Running...";
  try {
    const res = await fetch("/api/v1/algorithm/solve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: requestBox.value,
    });
    const text = await res.text();
    let shown = text;
    try {
      shown = JSON.stringify(JSON.parse(text), null, 2);
    } catch (_) {
      // Not JSON: show the raw body.
    }
    showStatus(`HTTP ${res.status}`, res.ok);
    responseBox.textContent = shown;
  } catch (err) {
    showStatus("Network error", false);
    responseBox.textContent = String(err);
  } finally {
    submitButton.disabled = false;
  }
}

document.querySelectorAll('input[name="algorithm"]').forEach((radio) =>
  radio.addEventListener("change", loadExample)
);
document.getElementById("reset").addEventListener("click", loadExample);
submitButton.addEventListener("click", submitRequest);

loadExample();
