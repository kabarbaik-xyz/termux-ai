<!-- DOC: backlog | version=v1 | upstream=prd v1.1, tsd/sad v1 -->
# Backlog — KirimKilat
## E-01 Customer Tracking (P0 — proposal Phase 1)
### US-101 Track parcel by resi
- **AC:** (as PRD §3-US-101, 3 criteria)
- **Screens:** SC-01, SC-02 · **Components:** TrackingLookup, StatusTimeline · **API:** API-001
- **DoD:** house + Playwright covers all SC-02 states · **Dep:** — · **Est:** M · **Role:** FE+BE
### US-103 Agent status update — SC-03/04, AgentTable/StatusUpdater, API-002/003 · Est: M
## E-02 Notifications (Phase 2) — US-102 … · E-03 Reporting — US-104 (CSV per CR-002) …
## Traceability matrix
| PRD req | US | SC | Component | Test |
|---|---|---|---|---|
| track [SRC-1] | US-101 | SC-01/02 | TrackingLookup.vue | tracking.spec.ts |
| notify [SRC-1] | US-102 | — | notifier (BE) | notify.int.test |
| report [SRC-1] | US-104 | SC-05 | ReportCsv | report.spec.ts |
Gaps: none (Q4 resolved by CR-002).
