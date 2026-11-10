# Engagement Research: What Makes High-Intensity Games Hard to Put Down

Research and analysis only. Nothing here is built. Every recommendation is tagged **[PROPOSED]** in the same way as `Gameplay Design - Two Hats.md`, which this document extends.

Sources: established public knowledge of these games' published mechanics, developer talks and common game-design analysis. No new playtesting was done. Treat claims about psychology as design heuristics, not lab results.

**Spec alignment.** Every mechanic in section 6 has been checked against `Spec/Fix it with Scrum Product and Technical Specification.md` and `docs/` (PRD, MVP scope, architecture, implementation status). Section 6.0 holds the result. Mechanics that broke a fixed requirement have been rewritten to fit it; the original idea is kept only as a note that needs a spec change. The MVP cut rule in `docs/mvp-scope.md` still applies: nothing outside the MVP list is built until the MVP acceptance gate passes.

---

## 0. Diagnosis: why "Fix it with Scrum" feels like a sequence of buttons

Before borrowing anything, name the actual problem. The current loop (from `content/balance.yaml` and the rules engine) is:

> A scripted card arrives → the player clicks an action (read, patch, test, push, delegate, coach, defer, answer call) → the action costs game minutes → meters move.

This loop is missing the five things every game in this study has:

| Missing ingredient | What it looks like now | Why it kills fun |
| --- | --- | --- |
| **Scarcity that forces trade-offs** | Actions only cost minutes, and minutes feel abundant until suddenly they are not. | No action excludes another, so no click feels like a decision. |
| **Uncertainty with readable odds** | Outcomes are mostly hidden, then appear as a meter delta. | The player cannot reason about risk, so a good or bad result feels random or invisible. |
| **Variety between runs** | The `schedule` is fixed: the same cards at the same minutes every run. | Run two is a memory test, not a new situation. |
| **Growth the player authored** | Only one perk (AI Assistant). | No "build", so no sense of "my strategy worked". |
| **Escalation and climax** | One sprint, flat pacing, ends on a timer. | No rising tension, no boss, no clutch moment, no peak to remember. |

Every recommendation below is chosen to fix one of these five, not to decorate the screen.

A constraint specific to this project: this is a **learning game** with a pre-test and post-test. Whatever the fun loop rewards, the player will learn. So the rewarded behaviour must be **good Scrum judgment** (honesty, protecting the sprint, coaching, reviewing before shipping), never the bluff or the shortcut. Several mechanics below are chosen because they make the honest play also the exciting play.

---

## 1. Core game-design techniques across the study

These are the recurring techniques, independent of genre. Each is named, then explained.

### 1.1 Meaningful scarcity
A limited resource that every option draws on, so taking one thing means giving up another.
- Slay the Spire: 3 energy per turn, 5 cards in hand.
- DOOM Eternal: low ammo forces weapon switching; low health forces a glory kill; low armour forces the flame belch.
- Valorant and Counter-Strike 2: round money forces "buy now or save for next round".
- Balatro: 4 hands and 3 discards per blind.

**Principle:** fun choices come from the cost of the options not taken.

### 1.2 Readable risk (telegraphing and known odds)
The player sees the danger and the probabilities before committing, so the outcome feels earned or deserved, never arbitrary.
- Slay the Spire enemy **intents** show what the enemy will do next turn.
- Buckshot Roulette tells you how many live and blank shells are loaded, but not their order.
- Into the Breach shows every enemy attack in advance.
- Black Desert Online shows the enhancement success chance.

**Principle:** randomness is exciting when the player can reason about it, and frustrating when they cannot.

### 1.3 Synergy and build-crafting
Individual pieces are modest; combinations are explosive, and the player discovers or engineers them.
- Balatro jokers (order matters; chips × mult).
- Hades duo boons (two gods combine).
- Vampire Survivors weapon evolutions (weapon + passive item at max level).
- The Binding of Isaac item interactions (hundreds of items, emergent combinations).
- Risk of Rain 2 proc chains (one on-hit item triggers another).
- Noita wand building.

**Principle:** the player's feeling of cleverness comes from authorship. "I built this" beats "the game gave me this".

### 1.4 Multiplicative scoring
Additive scores grow linearly; multiplied scores explode, which creates the "number goes absurd" moment.
- Balatro: chips × mult, with ×mult jokers stacking.
- ULTRAKILL style meter and rank (D to ULTRAKILL).
- Tony Hawk-style combos, Geometry Dash percentages, Risk of Rain 2 stacking.

**Principle:** multipliers make one well-planned moment worth more than many average ones, which rewards planning and creates peaks.

### 1.5 Push-your-luck and banking
The player holds an at-risk pile and chooses when to bank it.
- Extraction shooters (Escape from Tarkov, Dead Cells cells that are only banked if you survive to the next area, Deep Rock Galactic drop pod).
- Lethal Company: scrap is only safe on the ship; the quota must be met.
- Sea of Thieves: treasure must be carried to an outpost and can be stolen.
- Buckshot Roulette "double or nothing".
- Balatro interest: keep money unspent to earn more, at the cost of a weaker build now.

**Principle:** the choice to stop is a decision with real tension, and losing an unbanked pile is a memorable story.

### 1.6 Short runs, permanent learning, near-zero restart cost
- Super Meat Boy, Celeste, Hotline Miami: death to retry in under a second.
- Roguelites: a run lasts 20 to 40 minutes; the player keeps knowledge and some unlocks.
- Trackmania: instant reset and a ghost of your best attempt.

**Principle:** "one more try" requires that a try be cheap and that the last failure taught something specific.

### 1.7 Escalation within a session
- Vampire Survivors: enemy density rises over 30 minutes; so does player power.
- Risk of Rain 2: difficulty rises with real time, so lingering is risky.
- Fortnite and Apex: the shrinking storm or ring forces fights.
- Hades and Slay the Spire: each region is harder and ends in a boss.

**Principle:** tension must rise toward a climax. A flat curve gives no peak to remember (peak-end rule).

### 1.8 Branching route choice
- Slay the Spire map: elites (risk, better relics) vs safe rooms vs ? events.
- Hades door rewards are shown before you choose.
- Dead Cells biome choice.

**Principle:** choosing your own risk level puts the player in charge of the difficulty curve.

### 1.9 Boss encounters as exams
- Hades, Dead Cells, Cuphead, FFXIV raids, WoW raids.
- A boss tests the skill or build the player developed during the run.

**Principle:** a boss turns a run into a story with a climax, and is where mastery is proven.

### 1.10 Emergent chaos from interacting systems
- Helldivers 2 (friendly fire, stratagems, physics), Lethal Company (monsters + proximity voice + greed), RimWorld (storyteller AI), Garry's Mod, Noita (every pixel simulated), Gang Beasts (physics bodies).

**Principle:** when systems collide the game generates stories the designer never scripted. Players retell them, which is the strongest replay driver.

### 1.11 Social pressure and comparison
- Leaderboards (Trackmania, Geometry Dash), ranked ladders (Valorant, League of Legends), daily seeded runs (The Binding of Isaac daily, Spelunky daily), co-op dependence (Overcooked 2, Deep Rock Galactic, raids).

**Principle:** another person's score turns "good enough" into "I can beat that".

### 1.12 Information asymmetry and deduction
- Rainbow Six Siege (droning before the round), Counter-Strike (sound cues), Buckshot Roulette (magnifying glass, phone), social deduction games.

**Principle:** gathering information has a cost, and acting on partial information is a skill.

### 1.13 Physical skill expression under pressure
- Helldivers 2 stratagem codes typed while being chased.
- Hotline Miami, ULTRAKILL parries, Rocket League aerials, Celeste dashes.

**Principle:** pressure + a small physical task = adrenaline. The task must be quick and fair.

### 1.14 Meta-progression
- Hades mirror and story, Dead Cells blueprints, Risk of Rain 2 challenge-based unlocks, Balatro decks and stakes, Path of Exile 2 and Diablo IV gear, RuneScape skills.

**Principle:** even a failed run moves something forward, which removes the feeling that time was wasted.

### 1.15 Voluntary difficulty for extra reward
- Hades Pact of Punishment (Heat), Balatro stakes, Slay the Spire Ascension, Risk of Rain 2 Artifacts.

**Principle:** experts set their own challenge and keep playing long after the base game is solved.

---

## 2. Psychological triggers

| Trigger | What it is | Where it shows up | Note for a learning game |
| --- | --- | --- | --- |
| **Reward prediction error** | Dopamine responds most to rewards that beat expectation, and to cues that predict a reward. Anticipation is a large part of the pleasure. | Balatro score count-up, loot beams in Diablo IV, chest opening in Vampire Survivors. | Make the "reveal" of a decision's outcome a moment with build-up. |
| **Variable-ratio reinforcement** | Rewards on an unpredictable schedule are compulsive (the slot-machine schedule). | Loot drops in WoW, RuneScape and Path of Exile 2; gacha in Genshin Impact. | Use it for **content variety**, not for monetisation or grind. Avoid paid randomness entirely. |
| **Near-miss effect** | Almost winning feels like progress and drives retry. | Geometry Dash "94%", Getting Over It falls, Only Up!, Tarkov extraction with a sliver of health. | Show how close the player came ("Cover 96/100, you survived"). |
| **Loss aversion** | Losses hurt about twice as much as equal gains feel good. | Tarkov gear fear, unbanked cells in Dead Cells, Lethal Company scrap left behind. | Use for banking decisions; never let one loss wipe out a whole session's learning. |
| **Mastery and competence** | Self-determination theory: competence, autonomy and relatedness drive intrinsic motivation. | Celeste, Super Meat Boy, Trackmania, Dark Souls-likes. | Competence must be in **Scrum judgment**, so mastery = learning. |
| **Autonomy** | Meaningful choice over route and build. | Slay the Spire map, Hades boons, Path of Exile 2 passive tree. | Let the player choose which practices to adopt. |
| **Flow** | Challenge matched to skill, clear goals, immediate feedback. | Rhythm games, DOOM Eternal, Tetris. | Adaptive pressure (a director) keeps the player near the edge. |
| **Curiosity gap / Zeigarnik effect** | Unfinished tasks and unknown outcomes nag at us. | Locked items, "?" rooms, unexplored map, half-filled collection. | Show locked practices and silhouettes of unknown events. |
| **Goal-gradient effect** | Effort increases as a goal gets closer. | XP bars, quota counters in Lethal Company, boss health bars. | A visible sprint goal bar. |
| **Peak-end rule** | People judge an experience by its most intense moment and its end. | Boss fights, last-circle fights, final score screens. | End each sprint with a climax (demo day) and a strong summary. |
| **IKEA effect / authorship** | We value what we helped create. | Builds, factories (Factorio, Satisfactory), bases (Minecraft). | The player's "process" (chosen practices) is their build. |
| **Social comparison** | We measure ourselves against peers. | Leaderboards, ranked tiers, kill feeds. | Cohort leaderboards on the same seed fit a classroom perfectly. |
| **Agency in failure** | Failure that the player can explain ("I got greedy") invites a retry; unexplained failure invites quitting. | Hotline Miami, Slay the Spire, Spelunky. | Every loss screen must say *why* in one sentence. |
| **Escalation of commitment / sunk cost** | Investment makes quitting harder. | MMO grinds, daily login streaks. | **Avoid** exploiting this. It drives play without fun. |
| **Urgency** | Time limits narrow attention and raise arousal. | Overcooked orders, DRG escape timer, storm circles. | Short bursts only. Constant timers exhaust learners. |

---

## 3. Mechanics catalogue

Specific mechanics grouped by type, with the games that do them best.

### 3.1 Combos, multipliers and chains
- **Chips × mult** (Balatro): two numbers, one added and one multiplied, make planning legible.
- **Style meter** (ULTRAKILL, DMC): variety of actions raises rank; repetition decays it. Rewards creativity, punishes spam.
- **Proc chains** (Risk of Rain 2): one effect triggers another, which can trigger the first.
- **Combo timer** (Hotline Miami, Tony Hawk): keep acting within a window to keep the multiplier.
- **Chain reactions** (Noita explosions, Peggle, Vampire Survivors screens full of hits).

### 3.2 Critical hits and random spikes
- Crits in Diablo IV and Path of Exile 2, "viral" moments, Risk of Rain 2 Lens-Maker's Glasses.
- The project already has a `viral_chance` on pushes. That is a crit. It just isn't framed or anticipated.

### 3.3 Upgrades, synergies and builds
- Relics (Slay the Spire), jokers (Balatro), boons (Hades), items (Isaac, Gungeon, RoR2, Brotato), mods (Warframe), passive tree (Path of Exile 2).

### 3.4 Random events
- ? rooms (Slay the Spire), shrines (RoR2), devil deals (Isaac: pay max health for power), cursed chests (Dead Cells), raids (RimWorld), weather and storms.

### 3.5 Escalating difficulty
- Timer-based (RoR2), wave-based (Brotato, Vampire Survivors), region-based (Hades, Dead Cells), ascension or heat (StS, Hades), shrinking zone (battle royales).

### 3.6 Unlockables, achievements and meta
- Blueprints that drop and must be carried out (Dead Cells), challenge unlocks (RoR2: "do X to unlock Y"), deck and stake unlocks (Balatro), mirror talents (Hades), cosmetics (Fortnite).

### 3.7 Streaks
- Win streaks and loss-streak bonus money (CS2, Valorant economy), kill streaks, Duolingo streaks, Trackmania medals.
- Loss-streak compensation is underrated: it prevents a death spiral.

### 3.8 Boss fights
- Phased bosses (Hades, Dead Cells), raid mechanics with roles (WoW, FFXIV), boss blinds that change the rules (Balatro: "all hearts are debuffed").
- **Balatro's boss blinds are the best fit here:** a boss is a *rule change*, not a big health bar.

### 3.9 Time pressure
- Overcooked orders, DRG escape timer, Lethal Company ship departure, chess-clock turns, storm circles.

### 3.10 Emergent gameplay
- Physics (Gang Beasts, Noita), AI storytellers (RimWorld), player-made chaos (Garry's Mod, Roblox), systemic friendly fire (Helldivers 2).

### 3.11 Information tools with costs
- Buckshot Roulette items (magnifier reveals the current shell; phone reveals a future shell; beer ejects a shell), Siege drones, CS2 utility, StS scouting cards.

### 3.12 Economy between rounds
- Balatro shop with interest, Brotato shop between waves (lock items, reroll for a rising price), CS2 buy phase, Teamfight-style rerolls.
- **Reroll with rising price** is a cheap, powerful mechanic: it gives agency over randomness with a cost.

---

## 4. Dopamine and adrenaline loops

Four loop shapes repeat across every game studied.

### 4.1 The micro-loop (seconds)
**Act → immediate readable feedback → small decision.**
DOOM Eternal's resource dance, Balatro's single hand, Overcooked's chop-and-plate. Feedback is immediate and numerical or physical. Our game's equivalent today is "click → minutes pass → maybe a meter changes", which has no immediate readable result.

### 4.2 The tension loop (one to five minutes)
**Commit to a risk → tension rises → reveal → relief or loss → bank or push on.**
Buckshot Roulette's trigger pull, a Tarkov extraction, a Valorant 1v3 clutch, Balatro's last hand of a boss blind. Its structure:
1. Stakes are visible (the score you need, the shells loaded).
2. The player commits with partial information.
3. A short delay before the reveal (the count-up, the click of the hammer).
4. A strong, specific outcome.

### 4.3 The run loop (twenty to forty minutes)
**Start weak → draft a build → escalate → climax → summary → unlock → "one more run".**
Hades, Slay the Spire, Balatro, Vampire Survivors, Dead Cells. The player's memory of the run is the build they made and the moment it either broke the game or collapsed.

### 4.4 The meta loop (days and weeks)
**New unlocks, harder difficulty tiers, leaderboards, story beats revealed by dying.**
Hades' narrative progress on death is the gold standard: even losing is rewarding.

### 4.5 How clutch moments are manufactured
Clutch moments are not luck. Games design for them:
- **A failure threshold that is visible and close** (health bar, ring, Cover meter at 90).
- **A comeback mechanic** that gives the losing side a strong but risky option (Mario Kart blue shell, MOBA bounties, CS2 loss bonus, Apex respawn beacons, Hades Death Defiance).
- **A last-second decision** where one correct action reverses the outcome (a parry, a defuse, a correct shell guess).
- **Escalating pressure** that compresses decisions into fewer seconds.

### 4.6 How "I feel clever" moments are manufactured
- Hidden rules the player can discover (Isaac synergies, Noita wand mechanics).
- Combos whose value is greater than their parts (Balatro).
- Puzzles solved under pressure (Into the Breach, Factorio bottlenecks).
- Exploiting an enemy's telegraphed intent.

---

## 5. Game-by-game analysis

Each entry: core loop, strongest mechanics, why it hooks, and what to steal.

The "Steal" lines are raw ideas taken from each game and are **not** checked against the spec. Some of them (a hand of action cards, a score multiplier fed by process, public leaderboards) break fixed requirements. Section 6 holds the checked versions; follow section 6, not these lines.

### 5.1 Roguelikes and roguelites

**Balatro**
- *Loop:* play poker hands to beat a score threshold (blind); buy jokers between blinds; every third blind is a boss that changes a rule.
- *Strongest mechanics:* chips × mult; joker order matters; interest on saved money; boss blinds as rule changes; stakes for difficulty.
- *Why it hooks:* the simplest possible base (poker hands everyone knows) with a multiplier system that explodes. The player is constantly one joker away from a broken build. Score count-up animation sits on top of a real calculation the player planned.
- *Steal:* a two-number score (base × multiplier) where the player's chosen practices are the multipliers; boss sprints as **rule changes** ("this sprint, standups are cancelled"); interest on banked Focus.

**Hades I and II**
- *Loop:* fight through rooms; choose a door based on its shown reward; gods offer boons; die; return home; talk to characters; upgrade; retry.
- *Strongest mechanics:* boons from different gods with duo boons when you combine them; door reward shown before choosing; story advances when you die; Heat (Pact of Punishment).
- *Why it hooks:* death is never wasted; characters react to how you died. Choices are always between good things.
- *Steal:* **failure advances the story** (teammates comment on why the last sprint failed); duo practices (two practices combine into a stronger one); show the reward of a choice before taking it.

**Dead Cells**
- *Loop:* fast combat across biomes; collect cells and blueprints; spend them only at the end of a biome if you survive.
- *Strongest mechanics:* banking at checkpoints (extraction); timed doors that reward speed; cursed chests (big reward, one hit kills you until you kill 10 enemies); Boss Cells difficulty tiers.
- *Steal:* **cursed chests** as "cursed tickets": a high-payoff card that puts you in a fragile state until you complete it cleanly; timed bonus for fast, correct decisions.

**Risk of Rain 2**
- *Loop:* loot items, charge the teleporter, kill the boss, leave. Difficulty rises with real time.
- *Strongest mechanics:* item stacking (each copy adds more); proc chains; difficulty tied to the clock, so lingering to farm is a risk; Artifacts as modifiers.
- *Steal:* **difficulty that rises with game time** so dithering has a cost; stacking practices.

**The Binding of Isaac**
- *Loop:* explore rooms, find item rooms, fight bosses, descend.
- *Strongest mechanics:* hundreds of items with surprising interactions; devil deals (trade maximum health for a powerful item); secret rooms; daily runs.
- *Steal:* **devil deals**: a tempting shortcut with a permanent cost. This maps perfectly to bluffing in standups or skipping the Definition of Done. **Daily seeded run** for the whole class.

**Enter the Gungeon**
- *Loop:* bullet-hell rooms, dodge roll, find guns, bosses per floor.
- *Strongest mechanics:* the dodge roll's invincibility frames make skill expressive; synergies between named guns; secrets.
- *Steal:* one reliable "panic button" with a cooldown (for example "Call a timeout" that pauses incoming work for a moment but costs something).

**Slay the Spire**
- *Loop:* branching map; card battles; build a deck; collect relics; boss at the end of each act.
- *Strongest mechanics:* **enemy intents** (you see what the enemy will do next turn); energy scarcity; card removal (thinning is as strong as adding); map route choice with elites; Ascension.
- *Why it hooks:* every turn is a solvable puzzle with visible stakes. Losing feels like *your* mistake.
- *Steal:* **intents** for teammates and the Product Owner; a hand of action cards with energy instead of a free menu; route choice between safe and risky work.

**Vampire Survivors**
- *Loop:* move only; weapons fire automatically; pick one of three upgrades per level; survive 30 minutes.
- *Strongest mechanics:* minimal input with maximal power growth; weapon evolutions; treasure chest roulette; screen-filling escalation.
- *Steal:* **evolutions**: a practice levelled up and paired with a matching habit becomes an evolved version. Choose 1 of 3 upgrades on level-up (fast, low-friction decisions).

**Brotato**
- *Loop:* 20 short waves; shop between waves; build around stats.
- *Strongest mechanics:* very short waves; shop with **lock** and **reroll** (reroll price rises); characters that change the rules.
- *Steal:* **between-day shop with lock and rising reroll cost**; short, dense "waves" (days) rather than one long block.

**Noita**
- *Loop:* descend through a world where every pixel is simulated; build wands.
- *Strongest mechanics:* full physics and chemistry simulation; wand-building as programming; emergent self-destruction.
- *Steal:* the idea that the player's **build is a small program**. For a game about code this is thematic: practices that trigger on conditions ("when a test fails, …").

### 5.2 High-adrenaline and chaotic games

**DOOM Eternal**
- *Loop:* "combat chess": each enemy has a weak point; each resource comes from a specific action.
- *Strongest mechanics:* resource loop that forces aggression (chainsaw for ammo, glory kill for health, flame belch for armour). Being low on something tells you what to do next.
- *Steal:* **each meter is refilled by a specific Scrum action**: Focus by a retro or a break, Trust by coaching, Cover reduction by honesty. A low meter becomes a prompt, not just a threat.

**ULTRAKILL and its style-ranking system**
- *Loop:* fast FPS; health comes from enemy blood up close; style meter rates variety.
- *Strongest mechanics:* style rank from D to ULTRAKILL; repeating the same weapon decays style ("freshness"); parrying; healing from aggression.
- *Steal:* a **Sprint Style rank** that rewards *varied* good practice (review, coach, standup, refactor) and decays when the player spams one action. This directly attacks "button clicking": the same button pressed repeatedly stops scoring.

**Hotline Miami**
- *Loop:* one hit kills you and enemies; plan, execute, die, retry instantly.
- *Strongest mechanics:* instant restart; a level is a short puzzle of improvised violence; score for speed and variety.
- *Steal:* **instant retry of a single day** with a short checkpoint.

**Helldivers 2**
- *Loop:* co-op missions; call stratagems by typing arrow codes under fire; friendly fire.
- *Strongest mechanics:* stratagem input codes; systemic friendly fire; a shared war map driven by everyone's missions.
- *Steal:* **a short input under pressure**: for example, a stand-up answer typed or selected from fragments with a timer. A **cohort war map** where the class collectively "saves the company".

**Deep Rock Galactic**
- *Loop:* co-op mining; complete the objective; call the drop pod; escape before it leaves.
- *Strongest mechanics:* the escape timer at the end; class roles; optional secondary objectives.
- *Steal:* **end-of-sprint escape**: once demo day is called you have a short window to get the last work in.

**Lethal Company**
- *Loop:* collect scrap to meet a rising quota; monsters; the ship leaves at a fixed time.
- *Strongest mechanics:* **quota** that rises each cycle; greed versus survival; proximity voice creating comedy.
- *Steal:* **rising sprint quota** (velocity target) that the Product Owner raises each sprint, and the tension of "one more ticket before the deadline".

**Content Warning**
- *Loop:* film scary things for views on a fake video site.
- *Strongest mechanics:* the camera; risk taken for content; a fake platform scoring you.
- *Steal:* the project already has fake apps. Play Storey ratings can be the "views": a fake public judging your work.

**Peak**
- *Loop:* co-op climbing with stamina; teammates help each other up.
- *Strongest mechanics:* shared stamina management, emergent rescue moments.
- *Steal:* teammates who visibly depend on you: Tobi stuck on a ticket loses stamina until you unblock him.

**Gang Beasts**
- *Loop:* wobbly physics brawling.
- *Strongest mechanics:* imprecise physics creates comedy and unpredictability.
- *Steal:* little directly; the lesson is that **imperfect control can be fun if failure is funny**.

**Overcooked 2**
- *Loop:* fulfil orders in a kitchen whose layout fights you; communicate.
- *Strongest mechanics:* interdependent tasks; changing layouts; star thresholds.
- *Steal:* **orders queue with timers** and **star thresholds** (1, 2, 3 stars) per sprint; task dependency (you cannot push until it is reviewed, you cannot review until it is built).

### 5.3 Competitive and high-pressure multiplayer

**Valorant and Counter-Strike 2**
- *Loop:* round-based; buy phase; plant or defuse; first to 13.
- *Strongest mechanics:* **economy**: buy, half-buy or save; loss bonus that grows with consecutive losses; one life per round; clutch situations (1 vs many).
- *Steal:* a **between-day economy** with save versus spend, and a **loss bonus** so a bad day gives you more resources tomorrow (prevents a death spiral).

**Apex Legends**
- *Loop:* squad battle royale with legends' abilities.
- *Strongest mechanics:* ping system (communication without voice); respawn beacons (comeback); shrinking ring.
- *Steal:* the **ping system** idea: one-click context signals to teammates ("look at this", "blocked here").

**Fortnite**
- *Loop:* 100 players, storm closes in, build to survive.
- *Strongest mechanics:* the storm; building as instant defence; loot rarity colours.
- *Steal:* a **closing scope**: as the sprint ends, unfinished work is forcibly cut.

**League of Legends and Dota 2**
- *Loop:* lanes, last-hitting, objectives, team fights.
- *Strongest mechanics:* last-hit timing (micro-skill); snowballing; bounties on players who are ahead (comeback); objectives that change the map.
- *Steal:* **bounties as comeback**: if the player is behind, a risky high-payoff ticket appears.

**Rocket League**
- *Loop:* 5-minute matches of car football.
- *Strongest mechanics:* simple rules, unlimited skill ceiling, overtime.
- *Steal:* **overtime**: if the sprint ends tied with the target, a sudden-death final decision.

**Overwatch 2**
- *Loop:* objective-based team fights with ultimates.
- *Strongest mechanics:* ultimate charge that builds over time and is spent at a decisive moment.
- *Steal:* an **"ultimate"**: a powerful Scrum move (for example "Protect the Sprint": rejects all scope creep for a day) charged by good practice and spent at the right moment.

**Rainbow Six Siege**
- *Loop:* prep phase (droning, fortifying) then action phase.
- *Strongest mechanics:* information gathering before commitment; destructible environment.
- *Steal:* **sprint planning as a prep phase** that actually changes the action phase (fortify against expected problems).

**Escape from Tarkov**
- *Loop:* bring gear in, loot, extract or lose everything.
- *Strongest mechanics:* extreme loss aversion; extraction points; gear fear.
- *Steal:* the **extraction** structure, but softened: only unbanked points are at risk.

### 5.4 MMORPGs and progression-heavy games

**World of Warcraft**
- *Loop:* quests, dungeons, raids, loot.
- *Strongest mechanics:* raid mechanics requiring roles; variable loot; weekly lockouts; boss phases.
- *Steal:* **role-based boss encounters** (each teammate's strength matters).

**Final Fantasy XIV**
- *Loop:* story-driven MMO, choreographed raids.
- *Strongest mechanics:* telegraphed raid mechanics you learn and then execute; strong story.
- *Steal:* bosses whose patterns are learnable across attempts.

**Black Desert Online**
- *Loop:* grind and gear enhancement.
- *Strongest mechanics:* enhancement with visible success chance and a pity system (failstacks raise future odds).
- *Steal:* **pity**: each failure raises your odds next time. Do not copy its monetised randomness.

**RuneScape and Old School RuneScape**
- *Loop:* train many skills; rare drops.
- *Strongest mechanics:* many parallel progress bars; very rare drops; satisfying level-up moments.
- *Steal:* **skills that level by doing**: Facilitation, Reviewing, Coaching each level up separately.

**Genshin Impact**
- *Loop:* open-world exploration, gacha characters.
- *Strongest mechanics:* **elemental reactions** (two elements combine into a stronger effect).
- *Steal:* reactions between practices. **Avoid** the gacha.

**Warframe**
- *Loop:* fast movement, missions, modding gear.
- *Strongest mechanics:* deep modding with capacity limits (choose which mods fit).
- *Steal:* **capacity-limited loadout**: only N practices active per sprint.

**Diablo IV and Path of Exile 2**
- *Loop:* kill, loot, upgrade, push harder content.
- *Strongest mechanics:* loot rarity tiers; huge passive trees (PoE2); endgame scaling.
- *Steal:* rarity tiers for practices (common, rare, legendary) with clear visual identity; a small skill tree.

### 5.5 Sandbox, simulation and emergent games

**Minecraft**
- *Loop:* gather, build, survive the night.
- *Strongest mechanics:* day and night threat cycle; player-set goals.
- *Steal:* **the night**: a predictable daily danger (end-of-day status meeting) you prepare for.

**Terraria**
- *Loop:* explore, craft, summon bosses.
- *Strongest mechanics:* progression gated by bosses the player chooses when to summon.
- *Steal:* **player-chosen boss timing**: call demo day early for a bonus, or later for safety.

**Garry's Mod and Roblox**
- *Loop:* user-made modes.
- *Steal:* low direct relevance; the lesson is that **tools that combine freely generate content**.

**Sea of Thieves**
- *Loop:* sail, loot, carry treasure home; other players can steal it.
- *Steal:* carried-value-at-risk (extraction) and emergent encounters.

**Satisfactory and Factorio**
- *Loop:* automate production chains; fix bottlenecks.
- *Strongest mechanics:* the satisfaction of a system that runs itself; bottleneck diagnosis.
- *Steal:* **workflow as a pipeline**: a ticket moves through Build → Review → Test → Push; the player finds and fixes bottlenecks (Scrum's flow ideas). Very thematic.

**RimWorld**
- *Loop:* colony sim with an AI storyteller choosing events.
- *Strongest mechanics:* storyteller adjusts event intensity to tell a story with rising and falling tension.
- *Steal:* an **event director** for chaos events, tuned to tension rather than a fixed schedule.

### 5.6 Other highly engaging games

**Geometry Dash**
- *Steal:* the % progress near-miss and practice mode with checkpoints.

**Trackmania**
- *Steal:* **ghost of your best run** and a leaderboard on the same track; instant reset.

**Getting Over It and Only Up!**
- *Steal:* falls that lose progress create extreme near-miss emotion. Too punishing for a learning game; take the near-miss display only.

**Super Meat Boy**
- *Steal:* instant retry; **replay of all your attempts at once** on the win screen (shows growth).

**Celeste**
- *Steal:* **assist mode** (accessibility without shame); optional hard collectibles (strawberries) for experts.

**Baldi's Basics**
- *Why it matters most here:* it is a parody of edutainment. Answering wrong makes the teacher angrier and faster, and he chases you. It shows that **a wrong answer can create tension instead of a red X**.
- *Steal:* mistakes raise a visible threat that changes the game (Marlo gets suspicious and starts checking your work).

**Buckshot Roulette and similar risk games**
- *Loop:* shotgun with a known count of live and blank shells in unknown order; take turns; items manipulate information and odds.
- *Strongest mechanics:* **known odds, unknown order**; items that reveal (magnifier), skip (handcuffs), double damage (saw), eject (beer); shooting yourself with a blank gives you another turn (risk for tempo); double-or-nothing.
- *Why it hooks:* every pull is a readable probability decision with life-or-death stakes. Simple rules, huge tension.
- *Steal:* this is the **single best model for code review** in this game (see M2).

---

## 6. Ranked mechanics to adapt to "Fix it with Scrum"

Ranked by impact on fun and replayability, weighted by fit with learning goals and implementation cost. Difficulty is relative to the current architecture: rules in `src/fixit/rules/`, numbers in `content/balance.yaml`, server-authoritative state, and the `app.js` front end.

- **S** = a few days, mostly rules plus one UI view.
- **M** = about a week, new state plus UI.
- **L** = multiple weeks, new subsystems.

### 6.0 Alignment with the specification

Status values:
- **Fits now:** no requirement changes; can be built inside the MVP once the gate allows.
- **Post-MVP:** fits the full game (7 sprints, more tickets, perks, HACK-1) but not the MVP list.
- **Rewritten:** the first version broke a requirement; the version below fits. The original needs a spec change.

| Mechanic | Status | Requirements it touches | Notes |
| --- | --- | --- | --- |
| M1 Visible trade-offs on existing moves | Rewritten | PILE-2, TIME-1, G1, Architecture #2 | Original card hand removed moves and was turn-based. |
| M2 Review as Buckshot-style evidence gathering | Rewritten | CODE-1 to CODE-5, PILE-4, G3 | Original let tools reveal answers, so the player could skip reading code. |
| M3 Practices as jokers | Post-MVP | PERK-1, TUT-1, PROC-1 | Effects must never add to the process score or grade. |
| M4 Two-score tension made visible | Rewritten | CODE-5, METER-1, PERK-1, PROC-1, END-1, G2 | Original multiplied Points by process score, which erases the Points-vs-process gap the debrief exists to show. |
| M5 Seeded runs | Post-MVP | Architecture #3, PILE-1, MVP gate 2 | Seeds already exist; needs more than the 4 MVP tickets. |
| M6 Boss sprints | Post-MVP | HACK-1, SPRINT-1 | Matches the planned hacker events in sprints 4 and 7. |
| M7 Release train | Post-MVP, partial | CODE-5, review order in spec 3.1 | The spec resolves each push on its own; batching needs a spec change. |
| M8 Intents | Fits now | PILE-3, calls and pings | Ping **traps** stay hidden: they are meant to tempt. |
| M9 Devil deals | Fits now | CODE-4, STAND-1, MEM-1 | Reframes existing costs; no new numbers. |
| M10 Style rank | Fits now (display only) | METER-1, PROC-1 | Must not feed Points. |
| M11 Suspicion and last stand | Post-MVP, partial | METER-2, STAND-1 | Changes lose and standup numbers; all in `balance.yaml`. |
| M12 Shop with lock, reroll, interest | Post-MVP | PERK-1, Review flow | The spec opens the Toolbox at Review only. |
| M13 Director | Post-MVP | PILE-1, PILE-3, Architecture #3 | Must use its own seeded random stream. |
| M14 Comeback mechanics | Post-MVP | METER-1 | New balance values. |
| M15 Same-seed class discussion | Rewritten | MVP out-of-scope list, non-goals, INSTR-1 | Original was a public leaderboard and shared war map. |
| M16 Unlocks through learning | Fits now | TUT-1 | |
| M17 Voluntary difficulty | Post-MVP | `balance.yaml` | |
| M18 Failure advances the story | Fits now | TEAM-1, Architecture #4 | Model writes lines only; it never changes state. |
| M19 Pipeline view | Post-MVP, partial | PILE-2, PILE-4 | One card at a time stays; the pipeline shows delegated work in flight. |
| M20 Short skill moments | Post-MVP, rewritten in part | CODE-2, gateway 6.5.1 | Choices only; no typed student text reaches the model. |
| M21 Ultimate move | Post-MVP | balance values | |

**Pacing.** Section 1.6 cites 20 to 40 minute roguelite runs. The spec targets about 45 minutes for the whole 7-sprint campaign and 6 to 10 real minutes per MVP sprint. In this game a "run" is the campaign, and a sprint is one short round inside it.

**Other conflicts found during the check** (not caused by this document):
- `docs/mvp-scope.md` defers the fake browser with tabs; `Spec/Game UI Design Specification.md` says to keep browser navigation. The two documents disagree, and the current build follows the UI spec.
- The UI spec asks for hand-drawn, uneven outlines and rejects clean vector art. The current art had its wobble filter removed on request, which departs from that spec.
- INSTR-1 needs students linked to a cohort. The sign-up cohort code was removed, so there is currently no way to link them.
- The UI spec says the PBL machine must be preserved, but no document or code defines it.

### Tier 1: transforms the game

#### M1. Visible trade-offs on the existing moves [PROPOSED, rewritten to fit PILE-2 and TIME-1]
- **How it works:** keep every move the spec defines (Work, Triage, Delegate, Coach, Defer, Hold) available at all times, on the real-time clock. What changes is that the player **sees the price before choosing**. Each move shows its in-game time cost, the Focus it will leave, and which other card's deadline it will miss if taken now ("Coach Tobi: 15 min. Marlo's status demand will escalate to a call."). Focus below 30 already raises every cost by 50% (TIME-1), so a tired player sees every option get more expensive. One card is worked at a time (PILE-2), so opening one card is visibly a choice not to open another.
- **Used by:** Slay the Spire (energy and visible card costs), Overcooked 2 (orders with timers competing for one pair of hands), CS2 buy phase (every purchase shows what it leaves you for next round).
- **Why it engages:** scarcity is already in the rules (8 hours a day, one card at a time, deadlines that escalate), but today it is invisible until it hurts. Showing the opportunity cost turns each click into a decision between known losses, which is what makes card games tense.
- **Fit:** costs come from `costs_min` and `time.focus_low_cost_multiplier`; deadlines and escalation from the scheduler. No rule changes, only exposing values the server already knows.
- **Difficulty:** S to M (state already has the numbers; the UI needs a preview per move).
- **Replay impact:** medium on its own; high when combined with M5 seeded runs.
- **Needs a spec change:** the original idea (draw a hand of 5 action cards per day, play them with Focus as energy, possibly turn-based) removes moves the spec guarantees, can make a card impossible to settle in 1 to 3 actions (G1), and replaces the real-time clock (Architecture #2). Revisit only if the spec is changed after playtesting.

#### M2. Review as Buckshot-style evidence gathering [PROPOSED, rewritten to fit CODE-1 to CODE-5 and G3]
- **How it works:** the review stays what the spec defines: read 5 to 15 lines of ScrumScript, flag a line, pick 1 of 3 to 4 patches, Run Script, tick the Definition of Done, push. The Buckshot Roulette structure is added **around** that, using odds the rules already have:
  - **Known odds, hidden location.** A delegated card that comes back carries a hidden bug about half the time (PILE-4). Say so plainly on the card: "Roughly 1 in 2 delegated tickets comes back with a bug." The player knows the odds, not the answer.
  - **Every tool costs time and none gives the answer.** Run Script (5 min) shows pass or fail on the doc's examples only, and a security hole passes all runs (CODE-3). The AI Assistant (5 min) is wrong about 1 time in 5. Reading the code and flagging the line is the only certain way to find the bug. Tutorials remove `???` from unfamiliar lines (TUT-1), which works like Buckshot's magnifying glass.
  - **The ship decision.** At any point the player can push with boxes unticked (+5 Cover and a lower process score, CODE-4), hold, or keep investigating while the clock runs and other cards escalate.
  - **The reveal.** The result stays hidden until Review (current behaviour). Play Storey reviews then show what shipped, which is the trigger-pull moment.
- **Used by:** Buckshot Roulette (count shown, order hidden; magnifier), Minesweeper, Rainbow Six Siege (scouting before committing).
- **Why it engages:** review becomes a probability decision with readable stakes, and the only way to remove the risk is to read the code, which is learning goal G3. The tension rewards the correct behaviour (review before push) instead of a shortcut.
- **Fit:** uses PILE-4's hidden-bug rate, CODE-3's runs, the AI Assistant error rate and the review-time reveal. No new requirement.
- **Difficulty:** S to M (mostly showing odds and costs, plus a stronger review reveal).
- **Replay impact:** high, once there are more tickets than the 4 in the MVP.
- **Needs a spec change:** the original idea (a submission split into N changes, tools that reveal individual faulty changes, a teammate Trust cost for asking) lets the player find bugs without reading code, which defeats G3. It also needs a Trust stat the spec does not have. Do not build it.

#### M3. Practices as jokers: synergy build-crafting [PROPOSED, post-MVP]
- **How it works:** between sprints the player chooses 1 of 3 **Practices** (Scrum and engineering habits) for a limited set of slots. Each practice **changes a rule**: a time cost, what a tool shows, or how a teammate behaves. Practices never change the Points table (CODE-5) and never add to the process score or grade (PERK-1). Examples:
  - *Definition of Done:* the first Run Script on each ticket costs 0 minutes.
  - *Pair Programming:* coached help calls return one line of explanation that removes a `???` for free.
  - *Daily Standup:* after an accurate standup answer, the next ping from that teammate is never a trap.
  - *WIP Limit:* while no card is held, every move costs 20% less time.
  - *Retrospective:* once per sprint, reset one escalated card to level 0.
  - **Duo practices** (Hades): owning *Pair Programming* and *Definition of Done* unlocks a stronger combined version.
  - **Evolutions** (Vampire Survivors): a practice used enough times in a run upgrades.
- **Used by:** Balatro jokers, Hades boons and duo boons, Slay the Spire relics, Vampire Survivors evolutions, Isaac items, Brotato items.
- **Why it engages:** the player authors a strategy and gets "broken build" moments. Every practice is a real Scrum or engineering practice, so building a strong build means learning what each practice is for.
- **Fit:** extends PERK-1's Toolbox (bought with Points, which the spec allows) with a pool defined in `balance.yaml`. Tutorials (TUT-1) can add practices to the pool.
- **Difficulty:** M to L (rule hooks for each effect; start with 8 to 10 simple ones).
- **Replay impact:** very high.

#### M4. Two-score tension made visible [PROPOSED, rewritten to fit G2, CODE-5, PROC-1 and END-1]
- **How it works:** the spec deliberately keeps two scores apart. **Points** come from the push table (CODE-5), with repeat rewards shrinking by 30% each time (METER-1). The **process score** comes from logged behaviour (PROC-1). The lesson (G2) is that doing everything yourself raises Points fastest but lowers the process score, and the debrief shows the gap (END-1). Make that tension visible **during play**, not only at the debrief:
  - Show both scores side by side, live, with the last change to each ("+100 Points, process unchanged: you fixed it yourself").
  - Show the repeat decay before the push ("3rd identical clean push: worth 49 of 100").
  - Let the player watch the gap widen or close as they choose between fixing and coaching.
- **Used by:** Balatro (both halves of the score always visible, so planning is legible), Overcooked 2 (separate star thresholds), Hades (two currencies with different uses).
- **Why it engages:** the player feels the trade-off at the moment of choice. A strong run keeps both scores high, which is harder and more satisfying than maximising one number.
- **Fit:** both numbers already exist; this is display plus event copy. No rule changes.
- **Difficulty:** S.
- **Replay impact:** medium to high: "close my own gap" is a replay goal.
- **Needs a spec change:** the original idea (Points × a multiplier taken from the process score) breaks PERK-1 ("Points never feed the process score or final grade"), the CODE-5 table and the END-1 gap. Do not build it.

#### M5. Seeded runs: randomised sprints [PROPOSED]
- **How it works:** replace the fixed `schedule` with a **seed** that draws tickets, teammate quirks, events and their times from pools. The same seed always gives the same sprint (fair for comparison and for tests).
- **Used by:** every roguelite; The Binding of Isaac daily runs; Spelunky daily challenge; Trackmania.
- **Why it engages:** each run is a new situation; knowledge transfers but memorisation does not.
- **Fit:** the rules engine already draws cards (`rules/draw`). Pools go in content files. Seeds keep the existing deterministic tests valid.
- **Difficulty:** M.
- **Replay impact:** very high.

#### M6. Boss sprints that change the rules [PROPOSED]
- **How it works:** every third sprint (or the final day of a sprint) is a boss with a rule twist, shown in advance:
  - *The Auditor:* every push is checked for security holes; one hole ends the run.
  - *Scope Creep Marlo:* a new ticket arrives every hour; you must say no to some.
  - *Friday Deploy:* the CEO demands a release by 5 p.m.; Definition of Done boxes cannot be skipped.
  - *Demo Day:* rapid stakeholder questions with a timer; wrong or vague answers raise Cover fast.
- **Used by:** Balatro boss blinds (rule change), Hades and Dead Cells bosses, Slay the Spire act bosses, FFXIV raid mechanics.
- **Why it engages:** climax and peak-end; tests whether the player's build handles the twist.
- **Fit:** extends chaos events (Two Hats 3.5) and the existing scripted `attack_check`.
- **Difficulty:** M per boss (each is a rule modifier plus copy).
- **Replay impact:** high.

### Tier 2: adds tension, clutch moments and depth

#### M7. Release train: bank or push your luck [PROPOSED]
- **How it works:** finished tickets go into an unshipped **release**. The player chooses when to ship it. Each extra ticket added raises the release multiplier, but also the chance that one hidden fault ships with it. A failed release loses the unbanked multiplier, not the banked points.
- **Used by:** Tarkov and DRG extraction, Dead Cells cell banking, Lethal Company, Sea of Thieves, Buckshot Roulette double or nothing, Balatro interest.
- **Why it engages:** "ship now or one more?" is the tightest tension loop there is. Teaches small, frequent releases (a real agile principle): the safe play is to ship often.
- **Fit:** wraps the existing push. **Spec status: post-MVP, needs a spec change.** CODE-5 resolves every push to one result with fixed effects, so a batched release with a multiplier changes that table. A version that fits today: no multiplier, just the choice of when to stop working tickets and move to Review while unreviewed delegated work is still out.
- **Difficulty:** S to M.
- **Replay impact:** high.

#### M8. Intents: telegraphed teammate and Product Owner moves [PROPOSED]
- **How it works:** each teammate shows what they will do next, Slay-the-Spire style: "Tobi: will push without tests in 40 min", "Marlo: will add scope at 2 p.m.", "Ines: burning out (−Focus per hour)". The player can preempt with an action (coach Tobi, negotiate with Marlo, send Ines home).
- **Used by:** Slay the Spire, Into the Breach, FFXIV telegraphs.
- **Why it engages:** turns surprises into puzzles. The player plans instead of reacting.
- **Fit:** the schedule's calls, pings and escalation are hidden intents today. Show them. **Spec status: fits now.** Keep ping **traps** hidden: the spec uses them to tempt the player into skipping the Definition of Done, and a telegraphed trap teaches nothing. "Burning out" and "add scope" intents need new rules and wait for post-MVP.
- **Difficulty:** S to M.
- **Replay impact:** medium to high.

#### M9. Devil deals: tempting shortcuts with lasting costs [PROPOSED]
- **How it works:** at key moments the game frames an existing shortcut as a deal with its price stated: "Vague standup answer: no time spent now, Cover +5, and a later contradiction costs +10 more", "Push with a box unticked: saves the test time, Cover +5, lower process score". The cost is visible and lasting. **Spec status: fits now.** Use only the costs in STAND-1, MEM-1 and CODE-4; invent no new prices until post-MVP.
- **Used by:** The Binding of Isaac devil deals, Dead Cells cursed chests, Hades Chaos boons (curse now, blessing later), Balatro's high-risk jokers.
- **Why it engages:** temptation with a clear price. **It makes the Scrum lesson ("bluffing backfires") a felt experience rather than a rule.**
- **Fit:** standup vague and wrong answers and `dod_unticked_cover` already exist. Frame them as deals with a stated price.
- **Difficulty:** S.
- **Replay impact:** medium.

#### M10. Style rank that punishes spam [PROPOSED]
- **How it works:** each day gets a rank (D, C, B, A, S) based on **variety** of good practice and correctness. Repeating the same action stops adding to style ("freshness" decays). **Spec status: fits now as display only.** The rank is shown on the debrief and during play; it never changes Points (CODE-5) and is not a second process score. It can be computed from the same logged events E2 uses.
- **Used by:** ULTRAKILL, Devil May Cry, Hotline Miami scoring.
- **Why it engages:** rewards creative, varied play; directly punishes button mashing.
- **Fit:** extends `process_score.max_per_behaviour`, which already caps repeated behaviour at 3.
- **Difficulty:** S.
- **Replay impact:** medium.

#### M11. Suspicion as a pursuing threat, with a clutch threshold [PROPOSED]
- **How it works:** Cover is no longer a quiet meter. Above 70, management starts "checking": random spot-checks on your work appear with short timers. Above 90 is **Last Stand**: one more mistake ends the run, but one perfect review drops Cover by a large amount. Show near-misses on the end screen ("You survived at 96 Cover").
- **Used by:** Baldi's Basics (wrong answers make the threat faster), Alien: Isolation, Apex ring, Hades Death Defiance, Valorant clutch.
- **Why it engages:** creates adrenaline and comebacks from a meter that today only goes up.
- **Fit:** `cover`, `cover_lose_at: 100` exist. **Spec status: post-MVP, partial.** Showing the near-miss on the debrief fits now. Spot-checks and a large Cover drop change METER-2 and STAND-1 numbers, so they need new values in `balance.yaml` and a playtest.
- **Difficulty:** S to M.
- **Replay impact:** medium to high.

#### M12. Between-day shop with lock, reroll and interest [PROPOSED]
- **How it works:** at Review (where the spec opens the Toolbox), spend Points on perks and practices. You can **lock** an offer for the next sprint and **reroll** for a cost that rises each time. Unspent Points earn interest up to a cap. **Spec status: post-MVP.** Keep it at Review, not between days, to match the spec's Review flow; Points spent here still never feed the process score (PERK-1).
- **Used by:** Balatro, Brotato, Teamfight Tactics, CS2 buy phase.
- **Why it engages:** an economy layer with save-vs-spend decisions; agency over randomness.
- **Fit:** the existing Amazin' shop app already sells perks; points already exist.
- **Difficulty:** M.
- **Replay impact:** high.

#### M13. Escalating clock and a director [PROPOSED]
- **How it works:** the longer the sprint runs, the more frequent events become. A director (RimWorld/Left 4 Dead style) watches the player's state and adds pressure when they are comfortable and eases off when they are drowning.
- **Used by:** Risk of Rain 2, Vampire Survivors, Left 4 Dead AI Director, RimWorld storytellers.
- **Why it engages:** keeps the player in flow; manufactures rising tension toward each boss.
- **Fit:** `escalation` and `density` exist in `balance.yaml`. **Spec status: post-MVP.** The director must draw from its own seeded random stream (spec 6.4), so the same seed and commands still give the same event log and the scripted bot stays deterministic.
- **Difficulty:** M.
- **Replay impact:** medium to high.

#### M14. Comeback mechanics [PROPOSED]
- **How it works:** when the player is behind, offer a high-risk, high-reward **bounty ticket** (MOBA bounty) or a **loss bonus** (CS2) of extra Focus tomorrow.
- **Used by:** CS2 loss bonus, League of Legends bounties, Mario Kart items, Apex respawns.
- **Why it engages:** prevents the "run is already lost, why continue" feeling; creates clutch comebacks.
- **Difficulty:** S.
- **Replay impact:** medium.

### Tier 3: depth, social and meta

#### M15. Same-seed class discussion [PROPOSED, rewritten to fit the MVP scope and non-goals]
- **How it works:** the instructor can give a cohort one shared seed, so every student plays the same sprint. Students see only their own runs. The instructor sees all runs side by side in the existing cohort view (INSTR-1) and uses them to discuss choices in class: who coached, who bluffed, where the bug shipped.
- **Used by:** The Binding of Isaac and Spelunky daily runs (same seed for everyone), Trackmania (same track).
- **Why it engages:** "we all faced the same sprint" makes class discussion concrete and gives students a reason to replay and compare, without a public ranking.
- **Fit:** seeds already exist (Architecture #3) and INSTR-1 already lists cohort runs. It needs students linked to a cohort, which the removed sign-up cohort code used to do.
- **Difficulty:** S to M.
- **Replay impact:** medium to high.
- **Needs a spec change:** the original idea (public leaderboard, ghost comparison against the class, shared war map) is excluded: leaderboards and streaks are out of MVP scope, and multiplayer is a v1 non-goal.

#### M16. Meta-progression through learning [PROPOSED]
- **How it works:** watching a ToobYou lesson and then using its idea successfully in a run unlocks a new practice or a "lens" (Two Hats 3.4). Challenge-based unlocks: "Finish a sprint with no bluffs to unlock *Psychological Safety*".
- **Used by:** Risk of Rain 2 challenges, Hades mirror, Dead Cells blueprints, Balatro decks.
- **Why it engages:** every run moves something forward; ties learning content to power.
- **Difficulty:** M.
- **Replay impact:** high.

#### M17. Voluntary difficulty: Heat or Stakes [PROPOSED]
- **How it works:** after a first win, unlock modifiers the player can turn on for a score bonus: "Product Owner changes priorities twice a day", "No AI Assistant", "Two warnings end the run → one".
- **Used by:** Hades Heat, Balatro stakes, Slay the Spire Ascension.
- **Difficulty:** S per modifier.
- **Replay impact:** high for strong players.

#### M18. Failure advances the story [PROPOSED]
- **How it works:** after a lost run, teammates react to how it ended (Marlo found the bluff; Ines burned out) and a little more of the company's story unlocks.
- **Used by:** Hades.
- **Why it engages:** removes wasted-time feelings; makes characters matter.
- **Fit:** the LLM gateway can voice these lines.
- **Difficulty:** S to M.
- **Replay impact:** medium.

#### M19. Pipeline view with bottlenecks [PROPOSED]
- **How it works:** tickets flow through visible lanes (Build → Review → Test → Ship). Work piles up where capacity is lowest. The player rebalances (coach a dev, add a WIP limit).
- **Used by:** Factorio, Satisfactory, Overcooked.
- **Why it engages:** the satisfaction of fixing a system; deeply thematic (Kanban, flow, WIP limits).
- **Difficulty:** M to L.
- **Replay impact:** medium.

#### M20. Short skill moments under pressure [PROPOSED]
- **How it works:** a few real-time micro-tasks at peak moments, not everywhere: flag the faulty line in a short ScrumScript snippet within a time limit during a boss (the same flag-a-line action as CODE-2); pick the standup answer from the accurate, vague and wrong choices before the timer runs out (STAND-1); triage 4 incoming requests into Now, Later or Defer (PILE-2 Triage). **Spec status: post-MVP.** All input stays as choices. No typed student text, because the gateway only gives the model structured input to block prompt injection (spec 6.5.1).
- **Used by:** Helldivers 2 stratagem codes, WarioWare, Overcooked.
- **Why it engages:** adrenaline from physical speed. Used sparingly so it does not exhaust.
- **Fit:** the interpreter for tickets exists (`interpreter.step_limit`), so diffs are real.
- **Difficulty:** M.
- **Replay impact:** medium.
- **Caution:** keep an assist option (Celeste) for students who need more time.

#### M21. Ultimate move charged by good practice [PROPOSED]
- **How it works:** a meter fills from honest, high-quality play. Spend it on one strong move: "Protect the Sprint" (block all new scope for a day), "Swarm" (whole team on one ticket), "Retro Now" (reset all escalated cards one level). **Spec status: post-MVP.** The charge must come from logged behaviour and must not change the process score.
- **Used by:** Overwatch 2 ultimates, Hades Call, DOOM's Crucible.
- **Difficulty:** S.
- **Replay impact:** medium.

---

## 7. Mechanics to avoid

| Mechanic | Why to avoid |
| --- | --- |
| Gacha and loot boxes (Genshin Impact) | Paid or compulsive randomness; ethically wrong for a student audience. |
| Daily login streaks and FOMO timers | Drive attendance through guilt, not fun; harms learning motivation. |
| Long grinds (MMO levelling) | Fill time without decisions; the opposite of what this game needs. |
| Full-loss punishment (Tarkov, Getting Over It) | Too harsh for learners; a single loss should never erase a session's progress. |
| Rewarding the bluff | If bluffing scores well, students learn to bluff. Every shortcut must have a visible lasting price. |
| Constant real-time pressure | Tires learners and punishes slower readers. Keep timers to short peaks. |
| Pure randomness without counterplay | Feels unfair. Every random element needs a tool to read or influence it. |

---

## 8. A combined loop: what a sprint could feel like

Two versions. The first uses only mechanics that fit the spec now. The second adds post-MVP mechanics for the 7-sprint game.

### 8.1 Inside the MVP (fits now)

1. **Planning:** the Pile shows the first cards. Each teammate shows what they will do next (M8): "Tobi will ask for help in about 90 min", "Marlo wants a status update by 4 p.m."
2. **Build:** the player picks a card. Every move shows its price before it is taken (M1): "Coach Tobi: 15 min. Marlo's status demand will escalate to a call."
3. **Review a returned card:** the card says "Roughly 1 in 2 delegated tickets comes back with a bug" (M2). Run Script passes all 5 runs, but security holes pass too. The AI Assistant says it is fine, but it is wrong 1 time in 5. Only reading the code and flagging the line removes the risk. The clock keeps running and another card is about to escalate.
4. **The deal:** pushing with a box unticked is offered with its price spelled out: saves time, Cover +5, process score down (M9).
5. **Live scores:** Points and process score sit side by side, and the player watches the gap open when they fix things themselves instead of coaching (M4).
6. **Standup:** answer accurate, vague or wrong; the price of each is stated (M9).
7. **Review:** Play Storey reviews reveal what actually shipped. The debrief shows Points, process score, the gap, a style rank (M10), how close Cover came to 100, and teammates' reactions to how the sprint went (M18).

### 8.2 Full game (post-MVP)

Adds a seeded sprint with a boss rule twist (M5, M6), practices bought at Review that change rules and combine (M3, M12), rising pressure from a seeded director (M13), a comeback ticket when behind (M14), a last-stand state near Cover 100 (M11), and a shared seed for class discussion (M15).

Every step is a choice with a cost, uncertainty with readable odds, or a build decision. None of it changes the push table, the process score rules or the two-score debrief.

---

## 9. Suggested order of work

Highest value per effort first. Each step is playable on its own. Steps 1 to 3 fit the MVP; steps 4 onward wait for the MVP gate, as the cut rule in `docs/mvp-scope.md` requires.

1. **M4 two scores visible** and **M10 style rank, display only** (S): make the core lesson felt during play using numbers that already exist.
2. **M2 evidence-gathering review** and **M9 deals with stated prices** (S to M): reframe existing review, Definition of Done and standup costs.
3. **M1 visible trade-offs** and **M8 intents** (S to M): expose costs, deadlines and upcoming calls the server already knows.
4. **M5 seeded runs** (M): needs more tickets than the MVP's 4.
5. **M6 boss sprints** (M): built alongside HACK-1 in sprints 4 and 7.
6. **M3 practices** and **M12 shop at Review** (M to L): build-crafting.
7. **M11 last stand**, **M13 director**, **M14 comeback** (M): tension and clutch moments.
8. **M15 to M21**: class discussion, meta-progression and depth.

Not to build unless the spec changes: the card hand (original M1), the change-by-change review (original M2), Points × process multiplier (original M4), a public leaderboard (original M15), and typed student text in any form.

## 10. Open questions [OPEN]

- The spec fixes about 45 minutes for 7 sprints and 6 to 10 minutes per MVP sprint. Should a single sprint be replayable on its own as a short practice round?
- Should the original card-hand idea (M1) be playtested as a spec change after the MVP gate, or dropped?
- How many practices in the first pool? Balatro launched with 150 jokers; start with 8 to 10 and playtest.
- How do students join a cohort now that the sign-up cohort code is removed? INSTR-1 and M15 both depend on it.
- Which documents win when they disagree: `docs/mvp-scope.md` defers the fake browser, the UI spec requires it; the UI spec asks for hand-drawn outlines, the current art is smooth.
- What is the PBL machine? The UI spec requires it but no document or code defines it.
- Which numbers go into `content/balance.yaml` first? All new values must live there, not in the front end, and need a playtest.
