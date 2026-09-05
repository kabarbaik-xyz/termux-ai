---
name: db-migration
description: House database migration standard — forward-only, one logical change per file, reversible or explicitly not, tested. Blocks silent schema drift between Go/Python stacks.
mode: once
---
1. One migration file per logical change: `NNNN_short_name.(up|down).sql` (or tool equivalent [SLOT]).
2. Forward-only in prod; down-migration REQUIRED unless impossible (data loss) — then `-- NOT REVERSIBLE: <reason>` + PM sign-off noted in PR.
3. Never rename/drop in the same release that stops using a column — two-step (deprecate → remove next release).
4. Migration + model updates (Go AND Python if shared schema) + tests in ONE PR.
5. Integration test runs all migrations up, then down where reversible, on real PG.
6. Data migrations ≠ schema migrations: separate file, idempotent, batched.
