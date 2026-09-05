<!-- DOC: prd | version=v1 | sources=[SRC-1] | upstream=brd.md v1 -->
# PRD — KirimKilat Parcel Portal
## 2. User Stories
| ID | As a… | I want… | So that… | Priority | Screens |
|----|-------|---------|----------|----------|---------|
| US-101 | customer | track my parcel by resi | I don't call | P0 | SC-01, SC-02 |
| US-102 | customer | email on status change | I stay informed | P1 | — |
| US-103 | agent | log in and update status fast | ops keep moving | P0 | SC-03, SC-04 |
| US-104 | manager | monthly summary | report to owner | P2 | SC-05 |
## 3. Acceptance Criteria
### US-101
- Given a valid resi When I submit on SC-01 Then SC-02 shows current status + last 3 history entries + timestamp
- Given an unknown resi When submitted Then inline error "Resi tidak ditemukan" with retry (no page loss)
- Given no input When Track pressed Then validation message, no request sent
## 5. Scope delta vs BRD
WA notification pending Q3 → email in v1.
## CHANGELOG
2026-08-26 · CR-001 · accepted (email-first confirmed) — see 06.
