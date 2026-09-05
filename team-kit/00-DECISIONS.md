# Phase 0 — Decisions Sheet (send to leads today)

Each decision blocks specific kit artifacts. Answer inline; recommend = our default if you have no strong opinion.

## 0.1 Go framework — *BE lead* — blocks `go-api-endpoint`, `AGENTS.be`
Options: stdlib+chi (lean, idiomatic) · echo (batteries) · gin (most tutorials)
Recommend: **chi** — smallest surface, stdlib-shaped, easiest AI-generated code to review.
Answer: ______

## 0.2 Python framework — *BE lead* — blocks `py-api-endpoint`
Options: FastAPI (async, pydantic) · Django+DRF (batteries, admin)
Recommend: **FastAPI** — pydantic contracts match the Go error envelope, better for AI generation + review.
Answer: ______

## 0.3 FE styling/component base — *FE lead* — blocks `nuxt-component`, tokens
Options: Tailwind only · Tailwind + headless lib (Radix/Reka) · component lib (Naive/Element)
Recommend: **Tailwind + headless** — tokens map cleanly, a11y handled, no visual lock-in.
Answer: ______

## 0.4 Repo shape — *DevOps* — blocks AGENTS.md placement, CI
Options: monorepo (FE+BE) · split repos
Recommend: **split repos** — smaller AGENTS.md each, cleaner gates; monorepo fine too if tooling prefers.
Answer: ______

## 0.5 ID scheme + commit/PR conventions — *PM + leads* — blocks everything traceable
Recommend: `US-xxx` stories, `SC-xx` screens, `CR-xxx` change requests, `ADR-xxx` decisions; commits `feat(US-101): ...`; PRs ≤400 lines.
Answer: ______

## 0.6 Standards owner — *You*
One name. Approves all changes to AGENTS.md / skills / templates via PR.
Answer: ______

## 0.7 Docs tooling per machine — *DevOps* — blocks `doc-ingest`
Options: pdftotext+pandoc binaries · pure-Python (pypdf, python-docx, openpyxl)
Recommend: **pure-Python** — same on every OS, zero installs beyond pip.
Answer: ______
