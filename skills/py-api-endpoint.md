---
name: py-api-endpoint
description: House recipe for FastAPI endpoints — pydantic contracts, unified envelope identical to Go, pytest table tests + integration. BE-Python standard.
mode: session
---
Prereq: US-xx; endpoint ID from TSD §API.
1. Router thin; pydantic request/response models typed (mirror TSD schema); service layer holds logic.
2. SAME envelope as Go — byte-compatible `data/error{code,message}/meta`; error codes from the shared registry. If Go and Python differ, ONE of them is wrong — fix before merge.
3. Validation: pydantic constraints; 422 + registry code.
4. pytest: parametrized unit + integration (real PG) — happy/validation/auth/not-found/envelope-conformance.
5. Async where IO-bound; no blocking calls in handlers.
6. mypy clean; no `Any` at boundaries.
