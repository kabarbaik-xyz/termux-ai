<!-- TEMPLATE: copy to FE repo root as AGENTS.md · fill [SLOTS] after Phase 0 -->
# AGENTS.md — Frontend (Nuxt/Vite)
## Stack (locked)
Nuxt [3/4] · Vite · [Tailwind + headless lib — SLOT 0.3] · state: [Pinia — confirm] · tokens: `design/tokens.json` — TOKENS ONLY, zero hard-coded hex/spacing.

## Rules that ride with EVERY task
1. Consume the task's US-xx + SC-xx; implement ALL 5 states (loading/empty/error/success/no-permission) — from the UX Spec states matrix.
2. Components follow the `nuxt-component` / `nuxt-page` skills (house recipes, a11y checklist).
3. Every screen: `<!-- SC-xx · US-xxx -->` comment at top. Every component maps to the TSD inventory — new component = UX Spec entry first.
4. API calls: unified envelope from AGENTS.be; never parse ad-hoc.
5. Tests: Playwright per `frontend-tester` skill — states matrix IS the test matrix.
6. PRs ≤400 lines; commit `feat(US-101): …` (SLOT 0.5).

## Definition of Done (this repo)
lint ✓ types ✓ unit ✓ Playwright states ✓ a11y basics ✓ tokens-only audit ✓ screenshot for review ✓
