# e& Visual Identity & UI Direction
## Prototype Adaptation Guide for an Internal AI Interview Platform

**Purpose:** Practical visual-design reference for prototyping an AI interview / career platform during an e& internship.

**Design principle:** Build a product that feels like it belongs to the e& ecosystem without copying the corporate website. Preserve recognizable e& brand DNA, then introduce a controlled product personality around AI, career development, confidence, and human potential.

---

## 1. Brand Context

e& changed its group identity from Etisalat Group to **e&** in February 2022 as part of its transformation toward a global technology and investment group. Its current global brand positioning is **“Go for More”**, introduced in November 2024. e& describes the positioning around possibilities, empowerment, digital experiences, innovation, and enabling people and businesses to achieve more.

The current e& ecosystem spans connectivity, digital services, entertainment, fintech, enterprise solutions, AI, cloud, cybersecurity, and other technology services.

### What this means for the prototype

The product should feel:

- Technology-led
- Human-centered
- Ambitious
- Confident
- Modern
- Enterprise-ready
- Simple rather than visually complicated
- Capable of extending beyond interviews into wider talent/career experiences

**Recommended product-brand relationship:**

> e& → Product Name → AI Interview / Career Experience

For example:

> **e& HEMMA**  
> AI Interview & Career Experience

The product name can have its own personality, but the visual system should remain recognizably connected to e&.

---

# 2. Core Brand Colors

A published e& enterprise brand guideline provides the following core logo palette.

| Token | HEX | RGB | Role |
|---|---|---|---|
| e& Red | `#E00800` | `224, 7, 0` | Primary brand accent |
| e& Grey | `#636363` | `99, 99, 99` | Core neutral / secondary brand color |
| e& White | `#FFFFFF` | `255, 255, 255` | Primary background / negative space |

### Recommended supporting colors

A published e& enterprise guideline also shows a broader visual system containing darker and neutral supporting tones. For product prototyping, use these conservatively:

| Token | HEX | Recommended use |
|---|---|---|
| e& Maroon | `#4B0F1E` | Premium/dark sections, navigation surfaces, hero blocks |
| Soft Neutral | `#E6E6DC` | Secondary backgrounds, cards, quiet sections |
| Black | `#111111` | High-contrast UI text where needed |
| Light Grey | `#F5F5F5` | UI surfaces and application backgrounds |

### Color ratio

Do **not** make the entire product red.

Recommended starting ratio:

- 60–70% White / very light neutrals
- 15–25% Grey / dark text
- 5–10% Maroon or dark surfaces
- 3–8% e& Red accents and actions

The red should function as a **signal of importance**, not as the background for every section.

### Primary UI usage

**e& Red**
- Primary CTA
- Active navigation state
- Important status
- Progress emphasis
- Selected controls
- Small highlights
- Key data points

**Grey**
- Body text
- Secondary actions
- Supporting UI
- Borders/dividers
- Metadata

**White**
- Main page background
- Content areas
- Cards
- Negative space

**Maroon**
- Hero sections
- Dark-mode-like product surfaces
- High-value summary areas
- Premium/strategic sections

---

# 3. Typography

## Typography direction

Use a **modern, clean sans-serif system**.

The visual character should be:

- Geometric or contemporary
- Clean
- Highly legible
- Strong at large sizes
- Appropriate for both English and Arabic
- Professional without feeling overly corporate

### Important note

Do not assume that older Etisalat typography references represent the current e& corporate font system. Public legacy references to fonts such as Gotham Rounded belong to the previous Etisalat-era identity and should not be treated as the definitive current e& type specification.

For an internal prototype, select a contemporary bilingual sans-serif family that provides excellent Arabic and Latin support.

### Suggested prototype font stack

**Primary candidate:**
- English: Inter / Helvetica Neue / Arial
- Arabic: IBM Plex Sans Arabic / Noto Sans Arabic

**Preferred approach:**

Use one bilingual family wherever possible to minimize inconsistencies.

### Weight hierarchy

| Level | Suggested weight |
|---|---|
| Hero | 700–800 |
| H1 | 700–800 |
| H2 | 700 |
| H3 | 600–700 |
| Body | 400–500 |
| Labels | 500–600 |
| Metadata | 400–500 |

Avoid excessive font-weight variation.

---

# 4. Typography Layout

e& visual communication tends to benefit from **large, confident headlines** with generous whitespace.

### Recommended hierarchy

```text
Eyebrow / Label

Large headline
2–4 lines maximum

Short supporting statement

Primary action
Secondary action
```

Example for the interview platform:

> **Go beyond the interview.**

Supporting text:

> Practice with an AI interviewer, understand your performance, and improve before your next opportunity.

CTA:

> Start Interview

The headline should be visually dominant rather than surrounded by many competing components.

---

# 5. Layout Philosophy

## Core principle

**Less visual noise. More hierarchy.**

Use:

- Large whitespace
- Clear alignment
- Strong vertical rhythm
- Large headings
- Short content blocks
- Large visual anchors
- Simple navigation
- Controlled card usage

Avoid turning every section into a collection of equal-sized cards.

### Recommended page composition

```text
┌─────────────────────────────────────────────┐
│ Logo / Product       Navigation       User  │
├─────────────────────────────────────────────┤
│                                             │
│        Small label                         │
│                                             │
│        Large headline                       │
│        2–3 supporting lines                 │
│                                             │
│        [ Primary CTA ]                      │
│                                             │
│                         Product visual      │
│                         / AI interaction    │
│                                             │
└─────────────────────────────────────────────┘
```

---

# 6. Shape Language

The visual language should use a controlled combination of:

- Circles
- Rounded rectangles
- Large solid blocks
- Soft corners
- Thin dividers
- Simple geometric motifs

### Recommended radius system

```text
Small:   8px
Medium:  12px
Large:   20px
Hero:    28–32px
```

Do not make every object excessively rounded. e& should still feel like an enterprise technology brand.

---

# 7. Cards

Cards should be used to organize meaningful information, not as decoration.

### Good card usage

- Interview sessions
- Performance results
- Skill dimensions
- Recommended actions
- Recent activity
- Interview categories

### Avoid

```text
10 cards
10 colors
10 icons
10 gradients
```

Instead, create stronger hierarchy:

```text
Primary result
      ↓
Key insights
      ↓
Recommended improvements
```

---

# 8. Buttons

## Primary button

Use e& Red.

```text
Background: #E00800
Text: #FFFFFF
```

Examples:

- Start Interview
- Continue
- Practice Again
- View Results

## Secondary button

Use:

- White background
- Grey/black text
- Thin border

or a subtle neutral surface.

## Dark CTA

For dark/maroon surfaces:

```text
Background: #FFFFFF
Text: #4B0F1E or #111111
```

Avoid introducing unrelated bright button colors.

---

# 9. Navigation

Keep navigation extremely simple.

### Recommended desktop navigation

```text
[ e& / Product ]

Dashboard
Practice
Interviews
Performance

                         Notifications
                         Profile
```

The current page should use:

- Red indicator
- Red text
- Red underline
- Or a subtle red surface

Do not use multiple competing active states.

---

# 10. AI Interview Screen

This is the most important product screen.

It should feel calm and focused rather than like a generic chatbot.

### Recommended structure

```text
------------------------------------------------
Top bar
Product name              Interview 01   04:21
------------------------------------------------

Question

"Tell me about a project you are most proud of."

                     AI interviewer
                     avatar / simple visual

                 [ microphone / voice ]

------------------------------------------------
Progress: Question 3 of 8

                [ End Interview ]
------------------------------------------------
```

### Design priorities

1. Question clarity
2. Human-readable typography
3. Voice interaction visibility
4. Progress
5. Low distraction
6. Trust

Avoid loading the screen with analytics while the user is speaking.

---

# 11. Results / Assessment Screen

The assessment screen can use stronger e& visual language because it is a data-driven experience.

### Recommended hierarchy

```text
Your Interview Performance

        82
       /100

Strong performance

----------------------------------

Communication       88
Technical Depth     84
Clarity             91
Confidence          76

----------------------------------

What went well

...

What to improve

...

Recommended practice

[ Practice Again ]
```

### Score visualization

Use mostly:

- Grey base
- Red progress
- Maroon for high-level summaries

Avoid rainbow dashboards.

---

# 12. AI Visual Language

Do not use the stereotypical:

- Robot head
- Glowing brain
- Circuit-board AI
- Neon cyberpunk
- Excessive blue/purple gradients

Instead, communicate AI through:

- Conversation
- Intelligence
- Signals
- Data
- Motion
- Voice
- Minimal abstract geometry

### Recommended AI visual concept

A simple circular visual can represent the AI interviewer:

```text
        ◯
    ─────────
     AI Core
    ─────────
```

Use subtle motion around the circle during listening/speaking states.

---

# 13. Photography & Human Imagery

The current e& brand positioning strongly emphasizes people, aspiration, possibilities, and empowerment.

Therefore, when photography is used:

Prefer:

- Professionals
- Diverse people
- Real workplaces
- Human interaction
- Career aspiration
- Technology in context

Avoid:

- Generic corporate handshake photography
- Obvious stock-photo boardrooms
- Isolated robots
- Overly futuristic sci-fi imagery

---

# 14. Iconography

Use:

- Simple
- Geometric
- Consistent stroke width
- Minimal detail
- Rounded where appropriate

Recommended icon categories:

- Interview
- Microphone
- Skills
- Performance
- Career
- Growth
- Feedback
- AI
- Profile
- Opportunity

Do not mix several icon styles.

---

# 15. Motion

Motion should communicate intelligence and progress.

### Good motion

- Voice waveform when speaking
- Smooth progress transition
- Score count-up
- Subtle state changes
- Micro-interactions
- Interview question transitions

### Avoid

- Excessive bouncing
- Random animation
- Decorative particles
- Constant movement
- Gaming-style effects

The product should feel **confident and intelligent**, not playful.

---

# 16. Arabic UX

Because the product may be used by Arabic-speaking candidates, Arabic should be designed as a first-class interface rather than simply translated text.

### Requirements

- Full RTL layout
- RTL navigation
- Mirrored directional icons
- Correct Arabic line height
- Proper Arabic typography
- Arabic numerals where product requirements call for them
- English/Arabic language switch
- Avoid manually forcing Latin alignment into RTL layouts

### Example

Arabic:

> **جاهز للمقابلة؟**

Supporting:

> تدرب مع محاور ذكي، واحصل على تقييم يساعدك على تحسين أدائك.

CTA:

> **ابدأ المقابلة**

---

# 17. Product Naming Direction

For a product name such as **هِمّة**, maintain an e& relationship without making the product look like a separate company.

### Recommended lockup

```text
e&
هِمّة
AI Interview & Career Platform
```

or:

```text
e& | هِمّة
```

Use the e& logo according to the approved brand rules and maintain appropriate clear space. The product name should not visually compete with or alter the corporate logo.

---

# 18. "هِمّة" Product Personality

If the selected name is **هِمّة**, its personality should complement the e& positioning.

### HEMMA attributes

- Ambitious
- Encouraging
- Intelligent
- Human
- Confident
- Professional
- Growth-oriented

### Brand connection

**e&:** Go for More

**هِمّة:** Prepare to Go Further

Potential messaging:

> **هِمّة**  
> Prepare. Perform. Go Further.

Alternative Arabic direction:

> **هِمّة**  
> استعد. أبدع. تقدّم.

Do not copy e& campaign language directly; use it as strategic inspiration.

---

# 19. Recommended Design Tokens

```css
:root {
  --brand-red: #E00800;
  --brand-maroon: #4B0F1E;
  --brand-grey: #636363;
  --brand-white: #FFFFFF;

  --text-primary: #111111;
  --text-secondary: #636363;

  --surface: #FFFFFF;
  --surface-muted: #F5F5F5;
  --surface-warm: #E6E6DC;

  --border: #E5E5E5;

  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 20px;
  --radius-xl: 32px;

  --shadow-sm: 0 2px 8px rgba(0,0,0,.06);
  --shadow-md: 0 8px 24px rgba(0,0,0,.08);
}
```

For production, validate all colors, logo usage, typography, accessibility, and endorsement rules against the latest internal e& brand guidelines.

---

# 20. Recommended Prototype Design System

## Visual formula

```text
e& Brand DNA
    +
Human Potential
    +
AI Intelligence
    +
Career Growth
    =
هِمّة Product Experience
```

### The interface should feel

**80% e&**
- Color
- Confidence
- Typography
- Geometry
- Brand discipline

**20% product personality**
- AI interaction
- Career language
- Interview-specific visuals
- Performance analytics

This is preferable to creating a completely independent visual identity.

---

# 21. Do / Don't

| DO | DON'T |
|---|---|
| Use e& Red as an accent | Make every section red |
| Use strong whitespace | Fill every area |
| Use bold typography | Use tiny dense headings |
| Use simple geometry | Use decorative complexity |
| Use human-centered imagery | Use generic AI robots |
| Use restrained cards | Build card-heavy dashboards |
| Use subtle animation | Over-animate the interface |
| Support RTL properly | Treat Arabic as translated English |
| Keep UI enterprise-grade | Make it feel like a gaming app |
| Build a product identity under e& | Redesign the e& corporate identity |

---

# 22. Prototype Screen Set

For the first internal prototype, prioritize these screens:

### 01 — Welcome
Brand introduction + candidate value proposition.

### 02 — Profile / CV Understanding
Show what the AI understands about the candidate.

### 03 — Interview Setup
Role, interview type, difficulty, language.

### 04 — AI Interview
Main conversational experience.

### 05 — Live Feedback
Only minimal, non-distracting indicators.

### 06 — Interview Results
Overall score + dimensions.

### 07 — AI Feedback
Strengths, weaknesses, evidence.

### 08 — Improvement Plan
Personalized practice recommendations.

### 09 — Interview History
Previous attempts and progress.

### 10 — Career / Role Insights
Potential extension beyond interview practice.

---

# 23. Final Design Direction

The strongest visual direction for an e& internal AI Interview prototype is:

> **Minimal enterprise technology + bold e& red + deep maroon + strong typography + generous whitespace + human-centered AI + career growth.**

The product should look like something **e& could realistically launch**, not like a generic AI startup.

### Core palette

`#E00800`  
`#4B0F1E`  
`#636363`  
`#FFFFFF`  
`#E6E6DC`

### Visual keywords

**Bold · Clean · Human · Intelligent · Ambitious · Premium · Digital · Confident**

---

## Sources

1. e& — New Brand Identity announcement, 24 February 2022.  
   https://www.eand.com/content/dam/eand/en/system/docs/latest-announcements/2022/new-brand-identity-24-feb-2022.pdf

2. e& — “Go for More” global brand positioning, 4 November 2024.  
   https://www.eand.com/en/news/04-nov-24-eand-unveils-new-global-brand-goformore.html

3. e& — Annual Reports / Integrated Reports.  
   https://www.eand.com/en/investors/annual-reports.html

4. e& Integrated Annual Report 2024 — “Go for More” campaign and brand strategy.  
   https://www.eand.com/content/dam/eand/assets/docs/annual-report/2024/eand-integrated-annual-report-en.pdf

5. e& enterprise — Haifin Brand Guidelines, 2023.  
   Publicly available copy: https://uaetradeconnect.ae/wp-content/uploads/2024/02/e-enterprise-Haifin-Guidelines-29.12.2023.pdf

---

## Implementation Note

This document is a **prototype-oriented interpretation**, not an internal e& brand book. Public sources provide enough evidence to reproduce the broad visual character, but final production work should use the latest internal e& brand assets, logo files, typography specifications, accessibility standards, and legal/brand-approval rules available to the project team.
