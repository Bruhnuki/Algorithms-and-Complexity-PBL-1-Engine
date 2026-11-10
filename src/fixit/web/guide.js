// Beginner copy: every word a new player might not know, the "new idea" cards that introduce one concept
// at a time, and the plain-language scoring guide. Edit wording here; app.js only decides WHEN to show it.
// Scoring numbers mirror content/balance.yaml and a test keeps them in sync. No rules run here.

// key: [the word players see, a one-line everyday explanation]
export const TERMS = {
  scrum: ["Scrum", "A way of working where a small team builds something in short rounds, checks in every day, and improves as it goes."],
  sprint: ["Sprint", "A short round of work. Here a sprint lasts 2 days. At the end, users see what the team made."],
  standup: ["Standup", "A quick meeting at the start of each day. Everyone says what they did and what is blocking them."],
  todo: ["To-do list", "Every request waiting for the team. Real teams call it the backlog."],
  po: ["Product Owner", "Decides what is most important to build next. Here that is Marlo."],
  dev: ["Developer", "Writes the code. Ines and Tobi are your developers."],
  sm: ["Scrum Master", "That is you. You do not write the code yourself; you keep the team working smoothly and clear what blocks them."],
  bug: ["Bug", "A mistake in the code that makes the app do the wrong thing."],
  feature: ["New feature", "Something new the app should be able to do."],
  code: ["Code", "The instructions that tell the app what to do. Each line is one step."],
  test: ["Test", "Running the examples from the description to see whether the code gives the right answers."],
  dod: ["Done checklist", "The team's promise of what 'finished' means: it works, it matches the description, and it is safe. Real teams call it the Definition of Done."],
  ship: ["Send to users", "Putting your change into the live app, where real people use it. Developers call it pushing or releasing."],
  review: ["Review", "Checking a teammate's work before it goes to users."],
  delegate: ["Ask the team", "Handing a request to a developer instead of doing it yourself. You still check their work when it comes back."],
  coach: ["Help them", "Teaching a stuck teammate how to solve it, so next time they do not need you."],
  rating: ["App rating", "What users think of the app, from 1 to 5 stars. If it falls below 2 you are fired."],
  suspicion: ["Suspicion", "How close the company is to finding out you faked your résumé. At 100 you are caught."],
  energy: ["Energy", "How fresh you are. Low energy makes everything take longer. Some comes back every morning."],
  strikes: ["Strikes", "Official warnings from management. Two strikes and you are demoted."],
  points: ["Points", "Your score. You can spend them on upgrades."],
  teamwork: ["Teamwork score", "How well you work like a real Scrum Master: holding standups, helping people, reviewing, being honest. Separate from points."],
  escalation: ["Getting louder", "Ignore a request and it comes back louder: first a message, then a call, then a meeting, and Suspicion goes up."],
  security: ["Security hole", "A mistake that lets strangers see or change data they should not. Tests often do not catch it."],
  goal: ["Sprint goal", "What the team promises to finish this sprint. Miss it and you get a strike."],
  practice: ["Practice", "A good team habit, like checking work before it ships. Here practices are power-ups that change the rules in your favour."],
  release: ["Release", "A batch of finished changes sent to users together."],
  cards: ["Action cards", "Your hand of moves for the day. Each move needs the matching card."],
  clock: ["Game clock", "Time only moves while you are choosing what to do next, plus the time each action takes. Reading code never costs real seconds."],
};

// "New idea" cards. Each one teaches ONE concept the first time it matters. app.js decides when.
export const CONCEPTS = {
  welcome: { title: "Your to-do list", text: "Requests from your team appear here. Your first job: get one fix to users before the sprint ends.", terms: ["sprint"] },
  standup: { title: "The daily standup", text: "Every morning a teammate asks how it's going. Be honest: bluffing raises Suspicion.", terms: ["suspicion"] },
  bug: { title: "What is a bug?", text: "A mistake in the app's code. Read what it should do, then find the line that doesn't match.", terms: ["bug"] },
  team: { title: "Your team works live", text: "Drag a request onto Ines or Tobi and watch their bar fill. Each can do one thing at a time. Drop it on You to fix it yourself.", terms: [] },
  test: { title: "Testing", text: "A test runs the examples from the description. Green means they work, but tests can miss safety problems.", terms: ["test"] },
  dod: { title: "The Done checklist", text: "Tick only what is true. Ticking boxes you did not check is a lie that raises Suspicion.", terms: ["dod"] },
  review_changes: { title: "Checking a teammate's work", text: "You know how many changes are faulty, not which. Test or ask to find them, fix them, then send it to users.", terms: ["review"] },
  stuck: { title: "Someone is stuck", text: "A stuck teammate stops working until you unblock them. That is a Scrum Master's real job.", terms: ["sm"] },
  outage: { title: "Outage!", text: "The app is broken for everyone. Fix it fast for a big bonus. If it drags on, your rating drops.", terms: ["rating"] },
  practices: { title: "Practices", text: "Good team habits, here as power-ups that change a rule in your favour. Pick one.", terms: ["practice"] },
  hand: { title: "Action cards", text: "Each move now needs a matching card from your hand. Out of the right card? Regroup draws a new hand.", terms: ["cards"] },
  release: { title: "Releases", text: "Fixes now wait in a release. Send it to users to collect the points. Bigger pays more, but one bug loses the bonus.", terms: ["release"] },
  boss: { title: "Boss sprint", text: "The last sprint changes one rule. Read it at the top before you start.", terms: [] },
};

// Plain-language scoring guide (shown in ToobYou). Numbers are checked against balance.yaml by a test.
export const SCORING = {
  earn: [
    ["rocket", "Clean fix sent to users", "Tests pass, nothing risky.", "+100 pts"],
    ["play", "Good enough fix", "Works, but not perfect.", "+50 pts"],
    ["chat", "Honest standup", "Explaining truthfully lowers Suspicion.", "Suspicion −10"],
    ["check", "Good teamwork", "Standups, helping, honest checklists and reviews each count up to 3 times each.", "Teamwork score"],
  ],
  lose: [
    ["bug", "App crashes", "A fix that crashes is blocked.", "−30 pts"],
    ["alert", "Security hole", "Found at the sprint review.", "−150 pts, −0.8 Rating"],
    ["search", "Bluffing", "Vague: Suspicion +5. Made up: Suspicion +15. Caught in a lie later: Suspicion +10.", "Suspicion up"],
    ["clipboard", "Skipping the Done checklist", "Each send with an unticked box: Suspicion +5.", "Suspicion up"],
  ],
  extras: [
    ["robot", "AI Assistant", "An upgrade that suggests a fix, but it is wrong about 1 time in 5.", "150 pts"],
  ],
  lose_when: "You lose if the app rating falls below 2.0, Suspicion reaches 100, or you collect 2 strikes.",
};

// The short list shown in the Word book. Every other word is still explained when tapped in the game.
export const CORE_TERMS = ["sprint", "standup", "todo", "bug", "test", "dod", "ship", "review", "suspicion", "rating", "teamwork", "sm"];
