---
name: go-api-endpoint
description: House recipe for Go API endpoints — [chi/echo/gin SLOT 0.1] handler pattern, unified envelope, table-driven tests incl. integration against real PG. BE-Go standard.
mode: session
---
Prereq: US-xx; endpoint ID from TSD §API.
1. Handler: thin — parse+validate → service call → envelope write. Business logic in service, never handler.
2. Request validation at boundary ([validator SLOT]); reject with registry error code + 422.
3. Response: EXACT envelope from AGENTS.be (`data/error{code,message}/meta`) — conformance test asserts the shape.
4. Errors: registry codes only; `fmt.Errorf("%w")` wrapping; no leaked internals in messages.
5. Tests: table-driven unit (handler+service) + integration (real PG via docker): happy, validation-fail, auth-fail, not-found, envelope shape.
6. Structured log with request-ID at entry; no PII.
7. Commit `feat(US-xxx): endpoint <ID>`.
