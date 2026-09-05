---
name: deploy-checklist
description: Pre-deploy gate run by AI + confirmed by DevOps — env vars, migrations, gates, rollback, secrets, health. Nothing reaches a client env without this list green.
mode: once
---
- [ ] CI green on the release commit (all gates, both repos)
- [ ] Migrations: listed, ordered, reversible-flag known; backup verified
- [ ] Env vars/secrets: present in target, rotated per policy, NO secrets in repo/artifacts
- [ ] Config: feature flags default-safe; client-code-to-cloud policy respected (local tier where mandated)
- [ ] Health: smoke path (login → core flow → API ping) green on staging
- [ ] Rollback: commit + migration-down path documented; who executes, when
- [ ] Client comms: changelog + known gaps sent (PM)
Produce the filled checklist as `docs/plan/deploy-<date>.md` — claims without the artifact don't count.
