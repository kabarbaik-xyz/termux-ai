<!-- DOC: ux-spec | version=v1.0 | date=2026-09-10 | scope=kabarbaik-app web UI -->
# UX Redesign Spec — KabarBaik SDLC app

## 1. Scope & assumptions
Built from an audit of all 7 templates + CSS + JS. Assumption: local single-user
tool (delivery lead), desktop-first but must work on a phone (client demos on the
go). No auth flows to design (token gate is ambient).

## 2. User flows (primary)
- **Run a stage**: Project → Flow → press Run → (long wait, 1–15 min) → see output
  + artifacts. Must never feel frozen: sticky running banner + elapsed timer +
  spinner on the step. Completion = success toast + output panel.
- **First project**: Dashboard empty state → Add client → New project → upload a
  brief → run Discovery. Each step's next action is one click away.
- **Feed the inbox**: Project → Inputs → upload / paste link / type note → toast.
- **Adjust structure**: Templates → edit → save → next stage run uses it.
- **Reset everything**: Dashboard → Danger zone → typed confirm (mirrors API).

## 3. Screen inventory
| Screen | Purpose | Key components | Priority |
|---|---|---|---|
| Dashboard | orientation + totals | stats strip, projects table, backend card, danger zone | must |
| Clients | manage clients | add form, table | must |
| Client detail | client + its projects | new project form, projects table | must |
| Project detail | THE work surface | progress bar, flow steps, token card, inputs, docs viewer, feedback | must |
| Templates list | structure management | table w/ stage mapping | should |
| Template editor | edit structure | textarea + preview | should |

## 4. Per-screen wireframe notes
- **Global**: top bar (brand / nav w/ ACTIVE state / backend chip green↔red by
  availability). Toasts top-right, auto-dismiss, ?msg= driven.
- **Dashboard**: stats strip (clients · projects · stages done · total tokens)
  above the fold; projects table with stage chip + progress micro-bar per row;
  danger zone at bottom, collapsed.
- **Project**: page-head keeps the stage pill; add a thin progress bar
  (done/total). Flow steps: number bubble, label, status chip, run/re-run button
  right-aligned, tokens as a subtle line; current step visually elevated.
  Inputs: 3 cards → upload / link / note. Docs & feedback unchanged structurally.
- **Stage run**: on submit, JS locks all stage buttons, marks the step running
  (pulse), pins a banner "Running <stage> — <elapsed>"; page reloads on finish.

## 5. Design tokens
`design-tokens.json` at app root (indigo primary, warm neutrals, semantic
ok/fail/run, spacing 4-based, radius scale). CSS consumes them as custom
properties; no ad-hoc colors in components.

## 6. Open questions
- Background stage jobs + live polling (needs server change) — deferred.
- Dark mode — deferred.
