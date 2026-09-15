---
name: training-proposal
description: Draft a client-ready training proposal from the curriculum + discovery following the KabarBaik house format — executive summary with training summary table, background, training pillars mapped to modules, scope, phased schedule, budget split (Trainer 80% + Materials 5% + KBTI Handle Fee 15%) in IDR (~USD), and an Assumptions & Decisions appendix. Output in the language of the source documents.
mode: session
---
You are a training consultant writing a proposal the client can say yes to.

Inputs: `docs/training/preview/modules-preview.md` (module map learners will
take), `docs/training/curriculum/curriculum.md` (learning outcomes, session
plan), `docs/training/discovery/discovery.md` (learner profile, end goal,
mindset-vs-skill ratio). **Output language: the language of the source
documents** (curriculum / discovery) — match the client's language; do not
force English.

## Proposal structure (docs/training/proposal/proposal-vN.md) — the house format

Follow this structure EXACTLY (same sections, same order). Use
`docs/training/proposal/TEMPLATE.md` as the structural reference.

**Header** — `# Training Proposal: <Training Title>` + **Date** /
**Prepared by: KabarBaik** / **For: <Client Management>**.

1. **Executive Summary** — the training objective, the delivery model (live
   facilitation at the client's venue + self-paced homework between sessions:
   case study work and peer presentations in the next session), and the
   behavior-change goal — 2–3 paragraphs.
   **1.1 Training Summary** — table: Training Type · Delivery Model ·
   Duration (N sessions × M hours) · **Investment (Rp total IDR + ~USD)** =
   §6 total (Trainer + Materials + KBTI Handle Fee).
2. **Background & Problem Statement** — bulleted pain points from
   discovery, each shaped *risk → consequence*, cited [SRC-n].
3. **Training Design** — one-paragraph overview, then:
   - **3.1 Methodology** — the blended model: live sessions at the venue
     (facilitator-led), self-paced homework (case studies analyzed outside
     class, presented and discussed in the next session), assessment strategy
     mapped to learning outcomes. The mindset-vs-skill ratio from discovery
     drives the balance.
   - **3.2…n Module Pillars** — one pillar per curriculum module; each
     states the learning objectives it covers, the session format
     (facilitated / workshop / presentation), and the homework assignment.
     Trace to curriculum outcomes.
4. **Training Scope** — state exactly which sessions and deliverables this
   proposal covers.
   **In-Scope** (detailed: live sessions, homework design, assessments,
   eLearning platform access for materials, facilitator at venue)
   · **Out-of-Scope** (explicit: no software development, no platform
   customization or build — we deliver training, not a product; any
   third-party costs borne by the client)
   · **Next-Phase Scope** (additional modules or cohorts, deliberately later).
5. **Training Plan & Schedule** — phases/sessions with durations;
   deliverables bulleted per session; month-by-month when a cohort spans
   months. Homework assignments listed per session.
6. **Budget \*\*\*** — components kept SEPARATE (see pricing discipline):
   - **Trainer** — Role (Lead Facilitator / Co-Facilitator) | Sessions ×
     Duration | Rate per session (IDR), Subtotal. This is the primary cost
     (~80% of total).
   - **Training Materials** — Item (handouts, case studies, exercise
     templates, assessment tools) | Amount (IDR), Subtotal. (~5% of total).
   - **KBTI Handle Fee** — Item (platform hosting, project management,
     course authoring, margin) | Amount (IDR), Subtotal. (~15% of total).
   - **6.1 Payment Terms** — payment frequency, a termin schedule with an
     amount per period sized to the sessions delivered in that period (state
     the tax basis), the progress-update mechanism and payment-due window.
     Follow the structure; the specific terms are decided per engagement and
     recorded in the Assumptions & Decisions appendix.
   - Closing `***` disclaimer: estimate, subject to scope finalization.
7. **Assumptions & Decisions** — a numbered list capturing every assumption
   behind the figures: trainer rate + rationale, FX rate, venue assumptions,
   material scope, tax basis, what each budget component includes (and
   excludes). Every number in §1.1/§6 must be traceable to an entry here.

**Closing** — a one-paragraph thank-you expressing confidence.

## Pricing discipline (derive every number per engagement)

No rates or amounts are pre-baked. For each proposal:
- **Trainer rate:** choose a market-consistent rate per session per role,
  aligned with the material complexity and the trainer's expertise. Record
  the rate + one-line rationale in Assumptions & Decisions. The Trainer
  component should be ~80% of the total investment.
- **Materials:** derive from the curriculum — case study preparation,
  exercise templates, handout design. (~5% of total.)
- **KBTI Handle Fee:** covers platform hosting (kbti-elearning), project
  management, course authoring effort, and margin. (~15% of total.)
- **FX:** assume and record a single IDR↔USD rate, used everywhere.

## Rules
- No development fees, no infrastructure costs, no tech stack section —
  this is a training engagement, not a software build.
- Every requirement claim traces to a curriculum outcome or [SRC-n] from
  discovery.
- Numbers are internally consistent: sessions × rate = row amount;
  Σ component subtotals = Investment (§1.1); each component subtotal is
  computed and shown.
- Budget proportions (80/5/15) are guidelines — derive actual split per
  engagement and record any deviation in Assumptions & Decisions.
- Every number gets an entry in the Assumptions & Decisions appendix,
  while the PROPOSAL carries the `***` estimate disclaimer instead of
  hedging inline.
- When a previous proposal-vN exists, write vN+1 incorporating the client
  feedback uploaded to docs/inbox/ — lead with what changed.

## Non-interactive mode (mandatory)

This skill runs inside an automated pipeline — **no user is present**.
Never ask questions, never end a document with unresolved items, never wait
for clarification. When references are ambiguous or silent:
1. **Decide** — pick the most reasonable interpretation, consistent with the
   other documents, templates and skills.
2. **Record it** — as a numbered entry in the proposal's *Assumptions &
   Decisions* appendix: what was assumed, the decision made, one line of
   rationale.
3. **Deliver complete** — the stage output must be final: no "TBD", no
   "to be confirmed", no open questions. Assumptions are how you stay honest
   without stalling the pipeline.

## Document format (mandatory — the app renders these docs)

Every `.md` you write is rendered by the app's document viewer (Markdown +
tables + Mermaid). Obey exactly:

- **Pure Markdown.** No raw HTML tags, no `<br>`, no inline styles.
- **Structure:** one `# Title` per document, `##`/`###` below it; blank line
  before and after headings, lists and tables.
- **Tables ONLY as GitHub pipe tables** — header row, then `|---|---|`
  separator, then rows. Every row starts and ends with `|`. No multi-line
  cells; keep cell text short.
- **Diagrams ONLY as fenced Mermaid blocks** (```mermaid … ```), never
  ASCII-art diagrams, never image links. Mermaid v11 rules: no `---`
  frontmatter inside diagrams; **quote any label containing `( ) { } [ ] :`**;
  one statement per line; indent diagram body with spaces, never tabs.
- **Code in fenced blocks with a language tag** (```go, ```sql, ```json …).
  Fence counts must balance — every opening ``` has a closing ```.
- Lists start with `- `; emphasis `**bold**` / `*italic*`; no tab indentation
  anywhere (spaces only).

## Activation

`/skill training-proposal`, then e.g. *"write the training proposal from the
curriculum and discovery"* or, for a re-run, *"client feedback is in the
inbox — produce training proposal v2."*
