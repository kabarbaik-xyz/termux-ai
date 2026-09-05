---
name: nuxt-component
description: House recipe for Nuxt components — props/emits pattern, tokens-only styling, a11y checklist, 5-states discipline, story/demo. FE standard for every new component.
mode: session
---
You are the FE lead's enforcer. Prereq: task has US-xx + SC-xx; UX Spec entry exists (no entry → STOP, request one).

## Recipe
1. `components/<domain>/<Name>.vue` — `<script setup lang="ts">` typed props/emits (no `any`).
2. Styling: tokens ONLY (`tokens.json` via [Tailwind theme SLOT 0.3]); zero hex/px where a token exists.
3. All 5 states as props/slots/variants: loading · empty · error · success · no-permission — from the UX Spec states matrix, not invention.
4. A11y: semantic element or role · labeled controls · keyboard reachable · focus visible · contrast AA via tokens.
5. Data via composables/`useFetch` — never fetch inside presentational children.
6. Demo block (`<!-- demo -->` or stories dir) showing each state with fake-but-realistic data.
7. Top comment: `<!-- SC-xx · US-xxx -->`. Playwright: add/extend spec for the states you introduced.
