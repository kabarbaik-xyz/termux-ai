---
name: ui-audit
description: The triangle audit — design (Figma/tokens) ↔ UX Spec ↔ implementation — plus the traceability matrix (US→SC→component→test). Catches orphan screens, missing states, token violations, doc drift. CI-runnable.
mode: once
---
1. **Orphan screens**: implemented routes without `SC-xx` comment ↔ UX Spec inventory ↔ Figma frames — mismatches listed (extra screen = decoration, missing = gap).
2. **States coverage**: per SC, the 5 states in code (grep variants/slots) vs the UX Spec matrix vs Playwright specs — three-way table, red cells named.
3. **Token violations**: grep hex/px where tokens exist; Figma variables vs tokens.json drift (figma-tokens diff mode).
4. **Traceability matrix** (writes docs/plan/traceability.md): US-xxx → SC-xx → component file → spec file. Any US without a screen/test = loud gap list.
5. **Doc-sync flags**: PRD/TSD sections referencing these SCs/USs that changed since last audit (uses source-registry versions).
Output: pass/fail per section with evidence lines. CI mode: exit non-zero on red.
