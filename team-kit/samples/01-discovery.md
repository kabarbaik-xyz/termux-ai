<!-- DOC: discovery | sources=[SRC-1] | version=v1 -->
# Discovery — KirimKilat Parcel Portal
## Executive summary
Courier (20 agents, 3 cities) running on Excel; customers phone for status. Want: customer tracking web (P0), notifications, agent status dashboard, simple monthly reports. Hard deadline: live before Lebaran [SRC-1]. Budget-limited: "yang penting fitur 1 dulu jalan".
## Stakeholders
| Role | Who | Concern |
|---|---|---|
| Owner/sponsor | Budi Santoso | budget, Lebaran deadline |
| Agents (20) | ops staff | fast status updates |
| Customers | end users | self-service tracking |
## Current state & pains
Excel-based ops [SRC-1] → no customer self-service → phone-call load (pain P1, blocks BO-1); manual status → late updates (P2, blocks BO-2).
## Scope
IN: tracking page · notifications · agent dashboard · monthly report (basic).
OUT (client's words): mobile apps · payment integration · multi-language.
## Assumptions (confirm in meeting)
A1: agents use Android phones (browser-based dashboard ok) — ASSUMED
A2: parcel data model exists (resi number unique) — ASSUMED
A3: email addresses available for notifications — ASSUMED
## OPEN QUESTIONS
| # | Question | Ask | Why it matters |
|---|---|---|---|
| Q1 | Berapa rata-rata paket/hari? | Budi | sizing: DB + dashboard UX |
| Q2 | Resi format? siapa generate? | ops | data model + tracking input UX |
| Q3 | WhatsApp via provider resmi ok budget-wise? | Budi | CR-worthy scope; email fallback stated |
| Q4 | Report "sederhana" = CSV cukup? | manajemen | could cut a whole epic |
## Glossary
resi = waybill/tracking number · agen = courier agent
