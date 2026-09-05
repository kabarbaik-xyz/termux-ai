# CI Gate List (DevOps owns; same gates for AI and human code)
FE repo: install → lint → type-check → unit → Playwright (states) → tokens-audit (grep hex) → build → preview deploy (PR)
BE repo: install → lint/vet+mypy → unit → integration (real PG in docker) → envelope-conformance → migration-reverse check → build
Coverage floor: [SLOT — start 60%, ratchet up] · Gate behavior: red = not done, no exceptions, no overrides without standards owner.
The judge is CI. Chat transcripts (human or AI) prove nothing.
