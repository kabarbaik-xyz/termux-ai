---
name: figma-to-component
description: Generate a Nuxt component from a Figma frame via FREE REST (file JSON — layout, styles, variants), rendered through the house recipe (nuxt-component + tokens only). No MCP seats.
mode: once
---
1. REST `GET /v1/files/:key/nodes?ids=<frame>` (frame id from the `SC-xx` named frame).
2. Extract: layout structure (auto-layout→flex), variants (→ props), text styles (→ typography tokens), fills/strokes (→ color tokens via naming convention).
3. Generate `<Name>.vue` per the `nuxt-component` skill: typed props from variants, tokens ONLY, all 5 states scaffolded (states from the UX Spec — Figma shows happy path; the matrix is the truth).
4. Map every Figma variable name → token; an unmatched name = STOP and report (naming violation at source).
5. Playwright spec stub for the component's states; demo block with realistic fake data.
Rules: structure comes from Figma; states/semantics come from the UX Spec; style comes from tokens. Conflicts → UX Spec wins, noted in PR.
