# Game UI Design Specification

Example mockup: [UI Example Design.html](UI%20Example%20Design.html)

## 1. Design Direction

Redesign the game interface as a cartoonish, hand-drawn workplace comedy.

The game should feel like a chaotic startup office brought to life as a comic book. It should have personality, expressive illustrations, imperfect hand-drawn details, and playful typography.

The visual identity must feature:

- Hand-inked black outlines with visible texture.
- Slightly wobbly and imperfect edges.
- Naturally varying line thickness.
- Organic, hand-drawn shapes.
- Expressive cartoon characters and illustrations.
- Warm, colorful backgrounds.
- Playful typography that feels handwritten without looking childish.

The overall impression should be a **hand-illustrated indie comic game**, not a generic corporate dashboard.

IMPORTANT: This is a UI redesign. Do not remove or change the existing gameplay mechanics.

---

## 2. Preserve the Existing Game

The game is a workplace-survival comedy where the player is a Scrum Master who faked their résumé and must survive after the company's technical leads have been fired.

The player is not supposed to become the actual coding lead. Instead, they must manage the team, understand the work being submitted, make decisions, and survive the increasingly chaotic workplace.

Preserve all existing gameplay systems and content, including:

- Simulated browser and interconnected applications.
- Slack-style team communication.
- GitHub-style code review and push workflow.
- Play Store feedback and reviews.
- Facebook reputation and public feedback.
- Documentation and semi-pseudocode submissions.
- Debugging and testing.
- Security checks.
- Push decisions.
- Timed agile days and sprint progression.
- Cash, performance, reputation, and EXP.
- Demotion and firing consequences.
- AI Coding Assistant.
- Keyboard Master.
- Debug Master.
- YouTube learning.
- Hacker patch events.
- Existing completion and lesson systems.

### PBL Machine

DO NOT SKIP OR REMOVE THE PBL MACHINE.

Keep the PBL machine as an existing game element. Preserve its current functionality and purpose.

You may redesign its appearance to match the new cartoon art direction, but do not replace its mechanics or hide it behind unrelated menus.

---

## 3. Visual Style: Hand-Drawn Comic Aesthetic

This is the most important part of the redesign.

I do not want perfectly straight, smooth, uniform black outlines.

I want outlines that look like an actual illustrator drew them using an ink pen, brush, or marker.

### Outline Characteristics

Use:

- Slightly irregular and wobbly contours.
- Uneven stroke thickness.
- Natural variations in black ink density.
- Subtle dry-brush textures.
- Rough ink edges.
- Organic corners and imperfect curves.
- Small overlapping sketch lines.
- Occasional visible hand-drawn corrections.
- Subtle paper and ink grain.

The outlines should feel handmade rather than digitally generated.

### Important Distinction

The result should look intentionally hand-drawn, not poorly rendered.

The texture should be noticeable but controlled.

Use stronger roughness for:
- Character illustrations.
- Large interface panels.
- Decorative frames.
- Buttons.
- Illustrated objects.
- Background decorations.

Keep smaller controls and text areas readable.

### Avoid

- Perfectly straight vector outlines.
- Uniform stroke widths.
- Smooth SVG-like borders.
- Generic rounded rectangles.
- Excessive grunge textures.
- Random scratches everywhere.
- Messy outlines that make elements difficult to recognize.

Think of an indie cartoon game with hand-inked illustrations and a comic-book personality.

---

## 4. Color Palette

Use a warm, energetic comic-inspired palette.

| Role | Color | Usage |
|---|---|---|
| Main background | #FFF4D6 | Warm paper-like canvas |
| Black ink | #202020 | Outlines and primary text |
| Yellow | #FFD65A | Highlights and rewards |
| Coral | #FF786B | Urgent messages and danger |
| Sky blue | #72C8F2 | Information and selection |
| Mint | #91D8A7 | Successful actions |
| Lavender | #B9A4F5 | Special events and upgrades |
| White | #FFFFFF | Cards and content surfaces |

Keep the background relatively quiet so the game remains readable.

Use colors consistently across the entire interface.

Never rely on color alone to communicate important information. Include icons, labels, or other visual indicators.

---

## 5. Typography

I want typography that feels playful, rounded, and slightly comic-like.

However, DO NOT USE COMIC SANS.

Recommended fonts:

### Headings
- Baloo 2 ExtraBold
- Lilita One

### Buttons and Section Titles
- Baloo 2 Bold
- Nunito ExtraBold

### Body Text
- Nunito Sans
- Atkinson Hyperlegible

### Code and Semi-Pseudocode
- JetBrains Mono

The typography should feel friendly and expressive without sacrificing readability.

Avoid thin fonts and overly formal corporate typography.

Use uppercase text only for short reactions, alerts, and status labels.

---

## 6. Main Interface Layout

The game takes place inside a fake desktop browser.

Make the browser feel like a cartoon operating system.

### Desktop Shell

Include:

- Compact browser bar.
- Playful window controls.
- Application tabs.
- Main content area.
- Persistent game status area.
- Notification area.
- Current day and sprint information.
- Cash and EXP indicators.
- Important performance indicators.

The interface should feel like a browser inside a cartoon world.

Do not replace the existing browser navigation system.

### Application Navigation

Use illustrated icons and short labels for existing applications:

- Slack / Team Chat
- GitHub / Code
- Play Store / App Feedback
- Facebook / Public Reputation
- YouTube / Learning
- Fake Amazon / Purchases and Upgrades
- Documentation
- PBL Machine
- Other existing game applications

Do not invent new applications just to fill empty space.

---

## 7. Application-Specific Design

### Team Chat

Make the chat feel busy, human, and chaotic.

Use:

- Hand-drawn speech bubbles.
- Distinct teammate avatars.
- Expressive character reactions.
- Readable names and messages.
- Urgent message indicators.
- Unread notifications.
- Small reaction stickers.

The player should feel constantly interrupted by their team.

However, messages must remain easy to read.

### GitHub and Code Review

Make code review approachable instead of intimidating.

Use:

- Large readable submission panels.
- Clear file labels.
- Change indicators.
- Test results.
- Documentation sections.
- Semi-pseudocode panels.
- Clear push and debugging actions.

The player should feel like someone trying to understand submitted work, not someone using a professional IDE.

### Testing and Debugging

Use illustrated warning cards.

Show:

- Error descriptions.
- Failed tests.
- Successful tests.
- Possible causes.
- Consequences.
- Retry and debugging actions.

Use comic-style visual emphasis for critical failures.

Do not obscure important technical information.

### Play Store and Facebook

Represent public feedback using:

- Illustrated review cards.
- Stars and ratings.
- Speech bubbles.
- Profile illustrations.
- Expressive reactions.
- Reputation indicators.

Make negative reviews visually noticeable.

### Learning and Upgrades

Make YouTube learning feel like a temporary escape from workplace chaos.

Present upgrades as collectible illustrated cards or tools.

Clearly display:

- Upgrade name.
- Cost.
- Effect.
- Current level.

Preserve all existing upgrade functionality.

### PBL Machine

Give the PBL machine the same hand-drawn treatment.

Use:
- Textured black outlines.
- Organic illustrated shapes.
- Expressive details.
- Clear labels.
- Readable controls.

Keep its original behavior and functionality.

---

## 8. Buttons and Interactive Elements

Buttons should feel like physical cartoon objects.

Use:

- Rough hand-inked outlines.
- Slightly imperfect shapes.
- Offset shadows.
- Playful press-down animations.
- Clear hover states.
- Strong visual feedback.

### Interaction States

Every interactive element should have:

1. Default
2. Hover
3. Pressed
4. Selected
5. Disabled
6. Loading
7. Success
8. Warning
9. Error

Keep the interaction consistent throughout the game.

---

## 9. Animations and Feedback

Use animations to make the game feel alive.

Examples:

- Buttons slightly move down when clicked.
- New messages pop into the interface.
- Failed tests briefly shake.
- Successful tests display illustrated checkmarks.
- Push actions have a clear confirmation animation.
- Cash and EXP values animate when updated.
- Characters change expressions based on events.
- Notifications appear with playful movement.

Avoid excessive bouncing and unnecessary animations.

The game should remain responsive.

Respect reduced-motion preferences.

---

## 10. Overall User Experience

The interface should communicate three things:

### 1. Chaos

The workplace is disorganized.

The player receives constant messages, unexpected problems, and requests from teammates.

### 2. Comedy

The visual presentation should make the situation entertaining.

Use expressive characters, funny reactions, playful illustrations, and comic-style effects.

### 3. Pressure

The player must manage deadlines, understand submissions, make decisions, and avoid getting fired.

The interface should communicate urgency without becoming confusing.

---

## 11. Things to Avoid

DO NOT:

- Use Comic Sans.
- Use perfectly straight and uniform vector outlines.
- Make the interface look like a generic SaaS dashboard.
- Use sterile corporate UI components.
- Use thin grey borders.
- Use excessive gradients or glassmorphism.
- Use photorealistic illustrations.
- Make everything overly polished and symmetrical.
- Add excessive decorative elements.
- Make text difficult to read.
- Replace the simulated browser with a different navigation system.
- Remove the PBL machine.
- Change the PBL machine's functionality.
- Remove existing game mechanics.
- Simplify the core gameplay loop.

---

## 12. Final Design Goal

The final interface should look like a **hand-drawn indie cartoon game about surviving a completely dysfunctional startup company.**

Imagine a comic book artist designing an entire desktop operating system.

Everything should feel illustrated:

- Buttons look hand-drawn.
- Panels have textured ink outlines.
- Characters have expressive cartoon appearances.
- Icons have organic shapes.
- Cards have imperfect borders.
- Typography feels playful and friendly.
- Animations feel like a cartoon.

The most important visual characteristic is the **rough, textured, hand-inked black outline**.

I do not want clean vector art with a cartoon color palette.

I want something that genuinely feels illustrated by hand.

At the same time, the interface must remain readable, functional, and easy to navigate.

**Preserve the entire existing game. Redesign its visual identity, not its gameplay.**
