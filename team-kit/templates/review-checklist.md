# PR Review Checklist (humans review what AI can't judge)
- [ ] Traceability: PR names US-xx; diff maps to its AC — no drive-by scope
- [ ] Security: no secrets, injection surfaces, unsafe deserialization, client data to unauthorized sinks
- [ ] Contract: API changes match TSD envelope; FE parsing matches BE
- [ ] Architecture: no new component/endpoint outside inventory; ADR needed? → requested before merge
- [ ] States: all 5 present on touched screens (screenshot in PR)
- [ ] Tokens: no hard-coded hex/px (grep)
- [ ] Tests: states matrix covered; table tests for endpoints; migration reversible
- [ ] Size: ≤400 lines — bigger = task decomposition failed, bounce with reason
- [ ] Claims vs evidence: diff and CI show it works; the AI's summary is NOT evidence
