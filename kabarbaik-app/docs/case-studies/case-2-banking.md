# Case Study 2 — Banking
## "The Teller App Nobody Uses Anymore"

**Assignment:** One BA works this case end-to-end. You are the Business Analyst assigned to this client.
**Industry:** Banking (conventional regional bank)
**Budget approved by client:** Rp 8 billion
**Your deliverable:** Analysis pack + 15-minute consultant presentation + 10-minute Q&A defense

---

## Your Mission

You have been assigned to Bank Bukit Sentosa. The client, Pak Anton (Head of Channel & Branch Operations), has requested a replacement of the legacy teller application. Your job is **not** to document his request. Your job is to apply the consultant mindset from Sessions 1–4:

| Session | You must apply it by... |
|---|---|
| S1 — Iceberg Mindset | Treating his request as a symptom; using the Two Critical Questions and the 5 Whys on every claim in the artifact pack |
| S2 — 7 Levels of Needs | Breaking the real need down into L1–L7, every level backed by evidence from the pack |
| S3 — MHUI | Mapping Masalah, Harapan, Usaha, Ide — and turning every empty cell into a discovery question |
| S4 — Communication Stances | Diagnosing Anton's (and other actors') stances from the written artifacts, and planning your own congruent stance |
| Regulation (new) | Designing the solution direction so it respects Indonesian government regulation (OJK/BI) and international standards (Annex A) |

**You may state assumptions, but label them as assumptions. Do not invent new facts about the bank.** Everything you need is in this pack — including things that contradict each other. Noticing contradictions is the job.

---

## Part 1 — Company Profile

| Fact | Value |
|---|---|
| Bank | Bank Bukit Sentosa (mid-size regional bank) |
| Network | 140 branches, 2,100 staff, ~450 tellers |
| Assets | Rp 45 trillion |
| Strength | SME lending relationships, older customer base |
| Weakness | Digital laggard; mobile app rated 3.1 stars; no instant account opening |
| Key people | Pak Anton — Head of Channel & Branch Operations (your client, 19 yrs at the bank); COO (his boss); CIO; Head of Internal Audit; HR / Union representative; Siti — veteran teller, 15 yrs (quoted in artifacts) |

## Part 2 — The Stated Request

Project intake form, filed by Anton:

> **Project:** Replacement of Legacy Branch Teller Application (22 years old)
> **Requirements:** Modern UI, tablet compatibility, integrated queue management, CRM pop-ups on customer identification, and a customer "next-best-offer" engine.
> **Budget:** Rp 8 billion. **Timeline:** 12 months.
> **Business case (attached):** efficiency gains + improved customer experience. Competitor apps are ahead; we must modernize.

## Part 3 — Artifact Pack

### A1 — Branch Transaction Report (Channel Ops, 3-year trend)

| Transaction type | 3-year change |
|---|---|
| Simple transactions (deposit, transfer, passbook print, bill payment) | **−34%** |
| Advisory conversations (loan origination, investment, insurance) | **+18%** |
| Avg. branch daily footfall | −29% |

Analyst footnote: "Decline is structural, not seasonal: mobile-first competitors and the bank's own USSD/mobile channels absorb simple transactions. Meanwhile the *value* per branch visit keeps rising — customers who still come, come to talk."

*(Note what this does to the business case: the app Anton wants to replace handles precisely the transactions that are disappearing.)*

### A2 — Internal Audit Findings (last audit cycle, partial extract)

> Finding CH-03 (rated High): **7 KYC / account-opening completeness exceptions** identified across 5 branches. Root cause stated by staff: rushing account opening to shorten perceived queue times — steps skipped when the branch is busy.
> Recommendation: process redesign + system-enforced completeness checks. Management response due within 60 days.

### A3 — News Clipping (regional business daily, 3 months ago)

> "Bank [competitor] today launched fully digital account opening — new customers can open an account in under 10 minutes from their phone. Industry watchers ask: is this the end of the branch network as we know it?"

### A4 — Postmortem: Queue Kiosk Pilot (2 years ago, 12 branches)

- Kiosks installed for self-service ticketing and simple payments; abandoned after 9 months.
- Kiosk uptime: 61%. No branch staff assigned ownership; seniors found them confusing.
- Field observation noted verbatim: *"tellers actively referred customers back to the counter."*
- Conclusion in the postmortem: "Technology deployment without staff engagement and ownership will fail regardless of the technology chosen."

### A5 — HR / Union Memo (shared with you by HR)

> Branch staff morale survey: anxiety index at highest level in 5 years. Top-coded concern: "job security in digitalization programs."
> Siti, teller, 15 years, quoted at town hall: *"Every 'digital' project here has meant fewer friends at the branch. Where did the last three go?"*

### A6 — Email: Anton → CIO (2 months ago) and reply

> **Anton:** Pak, following up on the teller app replacement intake — this is now urgent, branch staff are suffering with the old system and the board is asking about modernization.
> **CIO:** Your intake is currently #14 on the portfolio priority list. FYI the core banking replacement program consumes all delivery bandwidth until at least next year. Any channel app touching the core will queue behind it. Suggest you revisit whether a *new app* is really the answer to your problem.

*(Anton has not shared this reply with anyone. His proposal to the board still assumes a 12-month app build.)*

### A7 — Anton's Board Deck (last quarter)

Pure numbers: transaction cost per branch visit, queue times, competitor feature comparison table, screenshots of modern teller UIs, Gartner-style maturity chart. **Zero mention of:** staff, the kiosk postmortem, audit finding CH-03, or the CIO email. Final slide: "Requesting approval: Rp 8B, 12 months."

### A8 — Transcript: Your 30-Minute Intro Call with Anton

Key moments, verbatim:

- **On the kiosk failure:** "That failed because the vendor was weak and IT support was non-existent. They installed the things and walked away. You can't get good vendors in this city." *(finger-pointing cadence even in tone of voice)*
- **When you asked "do staff worry these projects mean fewer jobs?":** *(laughs)* "Ha — that's way above my pay grade, friend. Anyway, have you seen the new tablets? They'll look fantastic in our newer flagship branches. Beautiful stands." *(topic dropped)*
- **On his relationship with the union rep:** "I told him straight: 'no worries, nothing will change for your members.' We're all family here." *(a promise the CIO email suggests he cannot keep)*
- **Near the end, quieter:** "I've spent 19 years in these branches. I opened my first teller drawer at 24. If they become empty showrooms — that's on me. That's my name on the door."

### A9 — Letter: OJK Correspondence (received last month, via Compliance)

> **Re: Follow-up on examination findings — remediation plan required**
>
> In connection with recent examination activities, OJK notes the audit findings relating to **KYC/account-opening completeness** (see also obligations under POJK on AML/CFT program implementation for banks, and consumer-protection obligations under POJK 22/2023).
> The bank is requested to submit a **remediation plan within 60 days**, including system and process measures ensuring completeness checks cannot be bypassed.
> Separately, Compliance notes for your planning:
> - Any new channel application touching the core is subject to **IT governance and incident-reporting obligations (POJK 11/2022)** — including the 3x24-hour incident reporting clock and outsourcing notification for critical vendors.
> - **Digital onboarding with biometric e-KYC is permitted** under the digital banking regulation (POJK 12/2021) — the compliance path exists if the bank chooses it.
> - Any agent/branchless service model falls under **branchless banking rules (POJK 19/2014, Laku Pandai regime)**.

## Part 4 — Annex A: Regulatory & Standards Context

You are not expected to be a lawyer. You are expected to show, in your solution design, that you considered these. Verify current versions before final design — regulations evolve.

### Government of Indonesia / OJK / Bank Indonesia

| Instrument | What it means for this project |
|---|---|
| **Banking Law (UU 7/1992 as amended by UU 10/1998) & UU 4/2023 (P2SK)** | Umbrella obligations: prudential operation, customer protection, accountability of channel systems |
| **POJK 12/POJK.03/2021 — Digital Banking** | Board oversight of digital products; permits **biometric e-KYC / digital account opening** — the compliance path for the competitor-style onboarding in A3 |
| **POJK 11/2022 — IT Implementation for Commercial Banks** | IT governance, cyber resilience, **incident reporting (3x24 hours)**, outsourcing rules & notification for critical vendors (affects the teller-app build) |
| **POJK 19/POJK.03/2019 — AML/CFT for banks; UU 8/2010 (TPPU); PPATK reporting** | KYC completeness is a legal obligation, not a process nicety — audit finding CH-03 has regulatory weight |
| **POJK 22/2023 — Consumer & Public Protection** | Fair treatment, complaint handling, transparency — queue-pressure workarounds that harm customers cut across this |
| **POJK 19/POJK.03/2014 — Branchless banking (Laku Pandai)** | If simple transactions deflect to agents/self-service, this regime applies |
| **UU 27/2022 — PDP Law** | Customer data processing in any new app: lawful basis, DPO involvement, breach notification |

### International standards (benchmark / contractual)

| Standard | Why it matters here |
|---|---|
| **Basel III/IV (BCBS) + BCBS Principles for Operational Resilience** | Operational risk & resilience expectations frame how regulators read channel-outage and process-failure stories |
| **ISO/IEC 27001:2022** | ISMS baseline for the bank and any critical vendor |
| **ISO 20022** | Payments messaging standard — relevant if the new app touches payment flows |
| **PCI DSS v4.0** | Card data in scope wherever card-present/absent flows are touched |
| **NIST CSF (benchmark)** | Cyber posture reference increasingly expected in OJK dialogue |

## Part 5 — Your Deliverables

1. **Iceberg clue map** — surface facts vs. what lies beneath; explicitly list the contradictions you found (there are at least two).
2. **7 Levels ladder** (L1→L7) — every level with the artifact/quote that proves it, plus the transition question you would use. Then the **reverse map** (L7→L1): from vision down to the minimum feature set.
3. **MHUI canvas** — Masalah (Environmental / Systemic / Personal), Harapan (wants vs. needs), Usaha (every past attempt, outcome, lesson), Ide (at least 3 co-created solution directions + MVP). Empty cells become your discovery questions.
4. **Discovery question plan** — the questions for your first real working session with Anton, each tagged with target level and MHUI quadrant.
5. **Stance log** — Anton's stance per artifact/moment (with the cue that gave it away), plus your own planned congruent stance with the switching technique you will practice.
6. **Regulatory impact note** — which instruments from Annex A touch your recommended direction (the OJK 60-day clock in A9 is not optional), and how the design answers them.

## Part 6 — Presentation & Defense (15 + 10 minutes)

**Present as a consultant, in this order:**
1. The real need and the evidence for it
2. The 7 Levels ladder
3. MHUI summary
4. Your stance read of this client organization
5. Recommended solution direction, MVP, and **what you deliberately will NOT build**
6. Regulatory & compliance considerations (including the 60-day remediation clock)
7. Your discovery plan for the first working sessions

**Q&A includes the Stance Hot-Seat (~5 min):** the reviewer will play Pak Anton in a specific stance. Respond congruently — that is being assessed, not just your slides.

**One challenge you must be ready for:** *"The board already approved Rp 8 billion for the app — you're telling us to spend it on people and process instead?"*

## Part 7 — Assessment Rubric (100%)

| Criterion | Weight |
|---|---|
| 7 Levels mapping — complete, evidence-based, reaches L5+ | 20% |
| MHUI canvas — all quadrants, root causes classified, all past attempts found | 20% |
| Solution direction — co-created, outcome-driven, **regulatory aligned** | 20% |
| Stance analysis of client + your own congruent stance plan | 20% |
| Presentation & defense, including hot-seat response | 20% |

**Automatic red flags:** scoping a 12-month app build while the CIO email says it cannot be delivered; ignoring audit finding CH-03 or the OJK letter; designing for tellers *at* staff rather than *with* them; presenting the kiosk postmortem as "vendor's fault, won't happen to us"; levels with no evidence.
