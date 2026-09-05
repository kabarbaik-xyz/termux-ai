# Figma Naming Convention (the automation glue)
Frames/pages: `SC-01 Login (US-101)` — screen inventory + traceability become grep-able.
Variables: EXACTLY token names — `color/primary`, `space/4`, `radius/md` (slashes allowed; match tokens.json paths).
Components: match the TSD component inventory names.
Prototype flows: named per UX Spec flow. Violations = figma-tokens/ui-audit report them; don't hand-fix, rename at source.
