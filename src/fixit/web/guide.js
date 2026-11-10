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
  welcome: { title: "Your to-do list", text: "Everything your team needs from you lands here, one request per card. Your first job: fix one bug before the sprint ends.", terms: ["todo", "sprint", "goal"] },
  standup: { title: "The daily standup", text: "Every morning the team has a two-minute check-in. A teammate asks how your last fix went. Honest answers keep Suspicion low. Bluffing raises it, and lies get noticed later.", terms: ["standup", "suspicion"] },
  bug: { title: "What is a bug?", text: "A bug is a mistake in the app's code. Users notice it, so fixing bugs keeps your app rating up. Press Fix it myself on a bug to look at its code.", terms: ["bug", "rating"] },
  code: { title: "Reading code, the beginner way", text: "You do not need to be a programmer. Read the description at the top, then read each line and ask: does this line do what the description says? The line that does not is the bug.", terms: ["code"] },
  test: { title: "Testing", text: "A test runs the examples from the description and checks the answers. Green means the examples work. A test cannot catch everything, which is why the Done checklist also asks about safety.", terms: ["test", "security"] },
  dod: { title: "The Done checklist", text: "Before work goes to users, the team agrees it really is finished. Only tick what is true. Ticking boxes you did not check is a lie that comes back as Suspicion.", terms: ["dod"] },
  shipped: { title: "Your change is live", text: "Real users now have your fix. They leave reviews in Play Storey, and those reviews move your app rating at the end of the sprint.", terms: ["ship", "rating"] },
  call: { title: "Someone is calling", text: "A teammate is stuck and needs a quick answer. Answering costs a little time but clears a blocker, which is the Scrum Master's real job. Missed calls cost Energy.", terms: ["sm", "energy"] },
  help: { title: "A teammate needs help", text: "Help requests are a chance to coach. Coaching takes time now, but the teammate learns and calls you less later. It also raises your teamwork score.", terms: ["coach", "teamwork"] },
  escalation: { title: "Ignored requests get louder", text: "A request you leave too long escalates: a message, then a call, then a meeting, and each step adds Suspicion. Pick what matters, and push less urgent cards to later on purpose.", terms: ["escalation"] },
  suspicion: { title: "Careful: Suspicion is rising", text: "Suspicion shows how close management is to discovering you cannot really code. Honesty and finished work lower it. At 100 the game is over.", terms: ["suspicion"] },
  review_end: { title: "Sprint review", text: "The sprint is over. Users have reviewed your changes and your rating moves. Next sprint you will learn to share the work with your team.", terms: ["sprint"] },
  team: { title: "Your team works live", text: "Ines and Tobi work while the clock runs. Drag a request onto one of them (or press Give to...) and watch their bar fill. You can only give each one task at a time, so keep them busy. Drop a request on You to fix it yourself.", terms: ["delegate", "dev"] },
  stuck: { title: "Someone is stuck", text: "Real developers get blocked: a question, a broken tool, a missing answer. A stuck teammate stops working until you unblock them. Left too long, the request gets louder.", terms: ["sm"] },
  outage: { title: "Production outage!", text: "Something broke for every user right now. Fix it fast: it pays a big bonus and lifts your rating. If it drags on, the rating drops hard.", terms: ["bug", "rating"] },
  combo: { title: "Combo!", text: "Finishing requests on time, one after another, builds a combo that multiplies your bonus. Any request that gets louder, or anything broken reaching users, breaks it.", terms: [] },
  delegate: { title: "New: ask the team", text: "You do not have to fix everything yourself. Ask the team hands a card to a developer. When their work comes back, review it before it goes to users: some of it will have mistakes.", terms: ["delegate", "review", "dev"] },
  review_changes: { title: "New: reviewing a teammate's work", text: "Their work comes back as 5 changes. You are told how many are faulty, not which ones. Test a change or ask the author to find the faulty ones, fix them, then send it to users.", terms: ["review"] },
  practices: { title: "New: practices", text: "Real teams build good habits. Here each habit is a power-up that changes a rule in your favour. Pick one now; you can buy more between sprints.", terms: ["practice"] },
  coming_up: { title: "New: see what is coming", text: "The Coming up list shows calls and requests that will arrive soon, so you can plan instead of only reacting.", terms: [] },
  hand: { title: "New: action cards", text: "From now on every move needs a matching card from your hand: Work, Test, Ask the team, and so on. Each morning you get a fresh hand. If you are stuck, Regroup draws a new hand but costs time.", terms: ["cards"] },
  release: { title: "New: releases", text: "Finished fixes now wait in a release instead of going out one by one. Send the release to users to collect the points. Bigger releases pay a bonus, but one bug inside loses it.", terms: ["release"] },
  multiplier: { title: "New: teamwork pays", text: "Your points are now multiplied by your teamwork score and by how many honest, tested fixes you sent in a row.", terms: ["teamwork"] },
  momentum: { title: "New: special moves", text: "Good habits fill the Momentum bar. When it is full you can use one special move, like protecting the sprint from new requests.", terms: [] },
  boss: { title: "Boss sprint", text: "The last sprint changes one rule to test what you have learned. Read the boss rule at the top before you start.", terms: [] },
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
