# Source Registry
- Every ingested doc gets `SRC-<n>` at ingest (doc-ingest maintains the counter in docs/<phase>/index.md).
- Every AI-produced doc MUST cite: requirements → `[SRC-n]`; upstream docs → `prd.md v2 §3`; decisions → `ADR-xxx`.
- No paraphrase of a client statement without an SRC. No requirement in a proposal/backlog that traces to nothing.
- Audit question this enables: "show me every place CR-014 touched" — answerable by grep.
