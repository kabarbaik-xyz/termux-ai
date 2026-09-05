<!-- TEMPLATE: copy to BE repo root as AGENTS.md · fill [SLOTS] after Phase 0 -->
# AGENTS.md — Backend (Go + Python)
## Stacks (locked)
Go: [chi/echo/gin — SLOT 0.1] · Python: [FastAPI/Django — SLOT 0.2] · DB: [PostgreSQL — confirm] · migrations: forward-only, one change per file.

## The unified contract (Go and Python are INDISTINGUISHABLE to the FE)
- Response envelope: `{"data":…,"error":{"code":"machine_code","message":"human"},"meta":…}` — exact shape in TSD §API.
- Error codes: one registry, shared by both stacks.
- AuthN/Z: [JWT/session — confirm] middleware identical semantics per stack.
- Validation at the boundary (pydantic / [go validator]); internal trust after.

## Rules that ride with EVERY task
1. Endpoint work follows `go-api-endpoint` / `py-api-endpoint` skills — handler pattern, table-driven tests.
2. Schema change → `db-migration` skill → reversible migration + model update in same PR.
3. Logs: structured, request-ID; never log secrets/PII.
4. Tests: table-driven; integration test against real PG (docker) for endpoints.
5. PRs ≤400 lines; commit `feat(US-101): …`.

## DoD (this repo)
lint ✓ vet/mypy ✓ unit ✓ integration ✓ envelope-conformance test ✓ migration reversible ✓
