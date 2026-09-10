# Case Study 1 — E-Commerce / Marketplace
## "The Seller Loyalty Program Nobody Asked For"

**Assignment:** One BA works this case end-to-end. You are the Business Analyst assigned to this client.
**Industry:** E-commerce / marketplace
**Budget approved by client:** Rp 3.5 billion
**Your deliverable:** Analysis pack + 15-minute consultant presentation + 10-minute Q&A defense

---

## Your Mission

You have been assigned to TokoLaju. The client, Ibu Ratna (Head of Seller Operations), has requested a Seller Loyalty Program platform. Your job is **not** to document her request. Your job is to apply the consultant mindset from Sessions 1–4:

| Session | You must apply it by... |
|---|---|
| S1 — Iceberg Mindset | Treating her request as a symptom; using the Two Critical Questions and the 5 Whys on every claim in the artifact pack |
| S2 — 7 Levels of Needs | Breaking the real need down into L1–L7, every level backed by evidence from the pack |
| S3 — MHUI | Mapping Masalah, Harapan, Usaha, Ide — and turning every empty cell into a discovery question |
| S4 — Communication Stances | Diagnosing Ratna's (and other actors') stances from the written artifacts, and planning your own congruent stance |
| Regulation (new) | Designing the solution direction so it respects Indonesian government regulation and international standards (Annex A) |

**You may state assumptions, but label them as assumptions. Do not invent new facts about the company.** Everything you need is in this pack — including things that contradict each other. Noticing contradictions is the job.

---

## Part 1 — Company Profile

| Fact | Value |
|---|---|
| Company | TokoLaju (marketplace, Indonesian mid-market) |
| GMV | Rp 2.1 trillion / year |
| Active sellers | 18,000 (top decile labeled "Gold": 1,800 sellers, ~40% of GMV) |
| Employees | 320 |
| Stage | Post-Series B; investors pushing profitability |
| Payments | Disbursement runs through a licensed payment partner (PJP); gateway was migrated 5 months ago |
| Key people | Ibu Ratna — Head of Seller Operations (your client, 6 yrs in role, former TokoLaju seller herself); COO (her boss); CFO; Head of Payments Engineering; Head of CX; DPO / Legal & Compliance |

## Part 2 — The Stated Request

Kickoff email from Ratna, in full:

> **From:** Ratna — Head of Seller Operations
> **Subject:** Seller Loyalty Program — approved, kickoff Monday?
>
> Hi! Great news — the COO approved my proposal. We're building a **Seller Loyalty Program platform**: tier badges (Bronze → Silver → Gold → Diamond), points for GMV milestones, a rewards dashboard, and push notifications for promotions. Competitor *Cipera* launched one and our top sellers are leaving.
>
> Budget is **Rp 3.5 billion**, vendor shortlist attached, timeline 6 months. I want to demo the tier dashboard at the quarterly business review in 3 months — leadership loves a good visual.
>
> Can we start requirements Monday? The vendors are ready.

## Part 3 — Artifact Pack

### A1 — Seller Churn Report (Seller Ops, last month)

| Segment | Churn (this year) | Churn (last year) |
|---|---|---|
| Gold (top decile) | **22%** | 8% |
| Silver | 9% | 7% |
| Bronze | 6% | 6% |

Analyst footnote: "Churn is heavily concentrated in high-GMV sellers. Note: 9 of the top 20 sellers by GMV have churned or given notice this year."

### A2 — Seller NPS Verbatims (CX team, quarterly survey, unedited)

- "Funds take more than a week to clear. On Cipera it's next day."
- "I've been selling here 4 years. My money was stuck for 9 days. No explanation, just 'please wait.'"
- "Customer service is polite but useless. Everyone says 'please wait, the team is processing.'"
- "The app is fine. Getting paid is the problem."
- One verbatim mentions the loyalty program: "Badges? Are they joking? Pay me on time."

### A3 — Payout SLA Dashboard (Payments Engineering, monthly)

| Metric | Before migration | Now |
|---|---|---|
| Avg. disbursement time | 1.2 days | **5.8 days** |
| % payouts > 7 days | 2% | **19%** |
| Seller support tickets re: payouts | 140/month | 1,900/month |

The degradation curve starts **exactly the month of the payment gateway migration** (5 months ago).

### A4 — Incident Review: Payment Gateway Migration (Payments Engineering, 3 months ago)

- Post-migration, automated reconciliation fails for **~12% of transactions** — these fall into a manual matching queue.
- Manual queue handled by 4 engineers; backlog currently ~3 weeks deep.
- Recommendation in the doc: "Prioritize reconciliation automation; add 2 FTE to backlog burn-down." Status: **Not started — no headcount.**

### A5 — Email: CFO → All Department Heads (4 months ago)

> Effective immediately we are freezing new headcount and pausing all non-committed projects through year end. Growth at all costs is over; we are in profitability mode. Any exception requires my sign-off and a clear revenue-defense case.

*(Note: the Rp 3.5B loyalty program was approved under "revenue defense." The reconciliation fix has no owner and no budget line.)*

### A6 — Chat Log: Ratna ↔ Head of Payments Engineering (2 months ago)

> **Ratna:** Hi — seller ops again. Payout tickets passed 1,500 this month. My top sellers are literally leaving. Can we get the reconciliation fix prioritized?
> **Payments:** We know. It's in the backlog. Everything is in the backlog.
> **Ratna:** This is 40% of GMV we're talking about.
> **Payments:** And I have one team and a hiring freeze. Escalating this over my head makes my team look bad, Ratna. Please stop.
> **Ratna:** …understood. Sorry to push.

### A7 — Meeting Minutes: Monthly GMV Review (2 months ago)

- COO: "Seller churn is now a board topic. Ratna, I need your turnaround plan in Q3."
- Ratna presented: churn numbers, Cipera's loyalty program screenshots, tier mechanics. Applause.
- **The word "payout" does not appear anywhere in the minutes.**
- CFO asked one question: "What does this cost?" — answered "Rp 3.5B over 6 months."

### A8 — Transcript: Your 30-Minute Intro Call with Ratna

Key moments, verbatim:

- **On churn:** "It's purely a retention-marketing issue. Look at the numbers — engagement drivers, GMV milestones, gamification. The data is very clear." *(flat, fast, factual — 6 straight minutes of metrics, no mention of sellers' complaints)*
- **When you asked "have sellers complained about anything else?":** "Haha, sellers complain about everything, that's the job — oh! Have you seen Cipera's badge animation? Really slick. Anyway, where were we — tiers." *(topic dropped)*
- **When you asked "how do sellers feel about payout times?":** *(pause)* "…Payment times are a Payments team topic. It's being handled."
- **Near the end, unprompted, quieter:** "I was a seller before this job. When your money is stuck, the platform is lying to you. I know exactly what they're feeling. But I can't fix payments — I can only fix my lane."

### A9 — Memo: Legal & Compliance / DPO (last week)

> **To:** Seller Ops, Payments Eng. **Cc:** COO
> **Re: Upcoming reviews — action needed**
>
> 1. **PDP Law audit (UU 27/2022):** Our scheduled data-protection review lands next quarter. Seller payout data (bank details, transaction records) is in scope. Notification flows to sellers currently have no consent/lawful-basis record. DPO must be involved in any new seller-facing feature.
> 2. **Bank Indonesia examination:** BI has sent an information request about our disbursement service via our partner PJP — specifically **reliability evidence and reconciliation reporting** for seller fund transfers. Payments Eng to respond within 30 days. This is now a regulatory item, not just an ops item.
> 3. **PSE registration renewal** (electronic system operator filing) is due; no impact expected, noted for completeness.
> 4. **Vendor shortlist caution:** two of the three loyalty-platform vendors on the shortlist would process seller personal data offshore. Under the PDP Law, cross-border transfer requires our safeguards to be in place first. Please involve Legal **before** contracting, not after.

## Part 4 — Annex A: Regulatory & Standards Context

You are not expected to be a lawyer. You are expected to show, in your solution design, that you considered these. Verify current versions before final design — regulations evolve.

### Government of Indonesia

| Instrument | What it means for this project |
|---|---|
| **UU ITE (Law 11/2008 as amended, most recently 2024)** | Electronic contracts & records validity; platform accountability for systems it operates |
| **PP 80/2019 — Trade Through Electronic Systems** | Marketplace operator obligations: business/registration compliance, transparency, complaint handling, accountability for the trading system |
| **Permendag 31/2023** | Licensing & supervision of e-commerce business actors; fair-competition conduct |
| **UU 8/1999 — Consumer Protection** | Consumer/seller rights, complaint resolution duties (the "please wait" responses have a compliance dimension) |
| **UU 27/2022 — Personal Data Protection (PDP)** | Lawful basis & consent for seller data processing; DPO involvement; breach notification; penalties up to 2% of annual revenue; cross-border transfer safeguards (directly hits A9 item 4) |
| **Bank Indonesia payment system framework (PBI 23/6/2021 & implementing regulations)** | Disbursement must run through licensed Payment Service Providers (PJP); fund segregation, reliability, and reporting obligations — the BI information request in A9 is this framework in action |
| **PSE registration (Permenkominfo 5/2020 regime)** | Platform must be registered as an electronic system operator |

### International standards (benchmark / contractual)

| Standard | Why it matters here |
|---|---|
| **PCI DSS v4.0** | If any loyalty/rewards flow touches cardholder data, scope explodes — good design keeps card data out |
| **ISO/IEC 27001:2022** | Baseline ISMS expectations for any vendor handling seller data |
| **GDPR (as international benchmark)** | Even without EU users, it is the de-facto bar for offshore-data vendors (A9 item 4) |
| **OECD / UN consumer-protection guidelines for e-commerce** | Soft-law benchmark for complaint handling and transparency |

## Part 5 — Your Deliverables

1. **Iceberg clue map** — surface facts vs. what lies beneath; explicitly list the contradictions you found (there are at least two).
2. **7 Levels ladder** (L1→L7) — every level with the artifact/quote that proves it, plus the transition question you would use. Then the **reverse map** (L7→L1): from vision down to the minimum feature set.
3. **MHUI canvas** — Masalah (Environmental / Systemic / Personal), Harapan (wants vs. needs), Usaha (every past attempt, outcome, lesson), Ide (at least 3 co-created solution directions + MVP). Empty cells become your discovery questions.
4. **Discovery question plan** — the questions for your first real working session with Ratna, each tagged with target level and MHUI quadrant.
5. **Stance log** — Ratna's stance per artifact/moment (with the cue that gave it away), Payments Head's stance, and your own planned congruent stance with the switching technique you will practice.
6. **Regulatory impact note** — which regulations from Annex A touch your recommended direction, and how the design answers them.

## Part 6 — Presentation & Defense (15 + 10 minutes)

**Present as a consultant, in this order:**
1. The real need and the evidence for it
2. The 7 Levels ladder
3. MHUI summary
4. Your stance read of this client organization
5. Recommended solution direction, MVP, and **what you deliberately will NOT build**
6. Regulatory & compliance considerations
7. Your discovery plan for the first working sessions

**Q&A includes the Stance Hot-Seat (~5 min):** the reviewer will play Ibu Ratna in a specific stance. Respond congruently — that is being assessed, not just your slides.

**One challenge you must be ready for:** *"Cipera's loyalty program is working and the COO already approved Rp 3.5B. Why shouldn't we just build it fast?"*

## Part 7 — Assessment Rubric (100%)

| Criterion | Weight |
|---|---|
| 7 Levels mapping — complete, evidence-based, reaches L5+ | 20% |
| MHUI canvas — all quadrants, root causes classified, all past attempts found | 20% |
| Solution direction — co-created, outcome-driven, **regulatory aligned** | 20% |
| Stance analysis of client + your own congruent stance plan | 20% |
| Presentation & defense, including hot-seat response | 20% |

**Automatic red flags:** accepting the vendor shortlist as scope; presenting tiers/badges as the core fix; ignoring A9; letting a deflection stand without naming it; levels with no evidence.
