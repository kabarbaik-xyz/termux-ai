# Case Study 3 — Insurance
## "The Agent App That Watches Everyone"

**Assignment:** One BA works this case end-to-end. You are the Business Analyst assigned to this client.
**Industry:** Insurance (conventional life insurer)
**Budget approved by client:** Rp 3 billion
**Your deliverable:** Analysis pack + 15-minute consultant presentation + 10-minute Q&A defense

---

## Your Mission

You have been assigned to PT Asuransi Sejahtera. The client, Ibu Dewi (Head of Agency Distribution), has requested a mobile "Agent Command Center" app. Your job is **not** to document her request. Your job is to apply the consultant mindset from Sessions 1–4:

| Session | You must apply it by... |
|---|---|
| S1 — Iceberg Mindset | Treating her request as a symptom; using the Two Critical Questions and the 5 Whys on every claim in the artifact pack |
| S2 — 7 Levels of Needs | Breaking the real need down into L1–L7, every level backed by evidence from the pack |
| S3 — MHUI | Mapping Masalah, Harapan, Usaha, Ide — and turning every empty cell into a discovery question |
| S4 — Communication Stances | Diagnosing Dewi's (and other actors') stances from the written artifacts, and planning your own congruent stance |
| Regulation (new) | Designing the solution direction so it respects Indonesian government regulation (OJK) and international standards (Annex A) |

**You may state assumptions, but label them as assumptions. Do not invent new facts about the company.** Everything you need is in this pack — including things that contradict each other. Noticing contradictions is the job.

---

## Part 1 — Company Profile

| Fact | Value |
|---|---|
| Company | PT Asuransi Sejahtera (conventional life insurer) |
| Annual premium | Rp 1.2 trillion |
| Agents | 4,500 licensed agents; agency channel = **70% of new business** |
| Persistency rate (renewals) | **68% and falling** (industry benchmark ~84%) |
| Back office | Policy administration & underwriting largely manual; commissions reconciled in spreadsheets |
| Key people | Ibu Dewi — Head of Agency Distribution (your client, 11 yrs in role, **former #1 agent 5 years running**); COO (her boss); Head of Policy Operations (back office); Head of IT; agency leaders (report to Dewi) |

## Part 2 — The Stated Request

Steering committee proposal, filed by Dewi:

> **Project:** Mobile Agent Command Center
> **Features:** commission calculator, agent leaderboard, digital product catalog, e-policy sharing to WhatsApp, and an **activity tracking dashboard so HQ can monitor agent productivity**.
> **Rationale:** competitor's agent app is why we are losing recruiters and top agents.
> **Budget:** Rp 3 billion. **Timeline:** 6 months.

## Part 3 — Artifact Pack

### A1 — Agency Attrition Report (Agency Distribution, last quarter)

| Segment | Attrition vs. baseline |
|---|---|
| Top-quartile producers | **2.4× baseline** |
| Mid producers | 1.1× baseline |
| New recruits (<1 yr) | 1.3× baseline |

Exit-interview quotes:
- "Commission disputes took 3 months to resolve. Three months. Twice."
- "The policy for my client took 3 weeks. I was embarrassed in front of her. She asked if we were a real company."
- "At the new company, the app shows my commission the day the policy is approved. Here I keep a notebook and pray."

### A2 — Commission Error Log (Policy Operations, last quarter)

- **214 commission disputes** logged last quarter; average resolution **47 days**.
- Resolution process: agents email a coordinator; coordinator reconciles manually **in Excel via email chains** across 3 departments.
- Root-cause note: "No single source of truth for commission data; policy admin system and agency reports disagree ~9% of the time."

### A3 — Policy Issuance TAT Report (Operations)

| Metric | Value |
|---|---|
| Average new-policy issuance | **16 days** (industry benchmark: 5) |
| Underwriting | Manual; medical-check scheduling done by phone |
| % policies requiring rework after agent submission | 31% |

### A4 — Viral Social Media Post (departed top agent, redacted, 2 months ago)

> "3 months chasing MY OWN commission at [company]. I brought the client, I did the work, I got excuses. To every agent out there: you are not a cost center. Treat your agents like partners, not costs. #knowyourworth"

40,000 likes. Picked up by two insurance-industry media accounts. The steering committee's urgency about "an agent app" dates from **the week this post went viral**.

### A5 — WhatsApp Log: Dewi ↔ Senior Agency Leader (last month)

> **Leader:** Bu, two things my leaders are asking. One: if HQ tracks our every move in the app, my team will walk. You know how they talk. Two — and please keep this between us — you know we all keep client data in our own notebooks. That's our security. If the company takes the data, what is ours?
> **Dewi:** I hear you. Let me think about how to frame this to the committee.

*(Two bombs in one message: surveillance fear kills adoption, and the company's client data lives in 4,500 personal notebooks — and walks out the door with every departing agent.)*

### A6 — Memo: Head of IT (last week)

> Re: Agent Command Center v1 feasibility.
> The feature set is feasible **except** commission display: commission data integration with the policy admin system is impossible before the core system upgrade (earliest 2027). Interim option: **manual weekly file upload** — meaning the app would show commissions that are up to a week old and only as accurate as the manual reconciliation that produces them.
> Also flag: activity tracking requires location/usage data collection from agents' personal phones — please involve Legal before we promise this.

### A7 — Town Hall Transcript: Dewi addressing agency leaders (last month)

- To the room: "You're right about everything — commissions, issuance, support — we'll fix it all. No tracking, I promise. Whatever you need." *(cheering)*
- Forty minutes later, same room, about the back office: "The back office has never respected agents. They sit in their air-conditioned room while we hunt in the streets. I've fought them for 11 years." *(louder cheering)*

### A8 — Transcript: Your 30-Minute Intro Call with Dewi

Key moments, verbatim:

- **On the viral post:** *(tone goes flat)* "Persistency is at 68. Attrition in top quartile is 2.4x. The app feature list addresses each driver. Here are the numbers." *(five minutes of statistics; the post is never named)*
- **On "why do agents keep client data in notebooks?":** *(laughs)* "Haha, agents are artists, you know how we are, we don't do spreadsheets… anyway — the leaderboard, I want it to have badges, three colors, Bronze-Silver-Gold like Cipera's seller tiers…"
- **On whether agents will accept activity tracking:** "The committee approved it, so it will be fine."
- **Near the end, unprompted, quieter:** "I was them. Five years #1. Every client I ever had, I could recite by heart — birthday, kids' names, everything. When I see agents leaving with their notebooks… I know we didn't just lose the sales. We lost the family."

### A9 — Memo: Compliance (this week)

> **Re: OJK market-conduct follow-up — items for any agent-channel initiative**
>
> Following media attention (see A4), OJK has initiated a **market-conduct review** of our agency channel. For your solution design, Compliance flags:
> 1. **Commission transparency & disclosure** obligations apply to agency distribution (product-distribution regulation, POJK 23/2015). The 47-day dispute resolution in A2 will be reviewed unfavorably.
> 2. **Client data in agents' personal notebooks is a PDP Law (UU 27/2022) exposure**: the company is the data controller, cannot demonstrate consent records, security, or breach-notification capability for data it does not hold. Any new app must improve this position, not worsen it.
> 3. **Activity tracking of agents** (location/usage on personal devices) requires a lawful basis, notice, and proportionality under the PDP Law — "the committee approved it" is not a lawful basis.
> 4. Any customer-facing or agent-facing application carries **IT implementation & incident-reporting obligations for insurers (POJK 11/2023)** — include the compliance workstream in timeline and budget.
> 5. Commission payment flows are subject to **AML/CTF controls (UU 8/2010, PPATK)** — verify beneficiary identity in any faster-payout design.
> 6. Finance notes: **IFRS 17** contract-data quality requirements land on exactly the commission/policy data this initiative would finally digitize — an alignment opportunity.

## Part 4 — Annex A: Regulatory & Standards Context

You are not expected to be a lawyer. You are expected to show, in your solution design, that you considered these. Verify current versions before final design — regulations evolve.

### Government of Indonesia / OJK

| Instrument | What it means for this project |
|---|---|
| **Insurance Business Law (UU 2/1992 as amended by UU 40/2014)** | Policyholder protection is paramount; company accountability for distribution conduct; sanctions up to license measures |
| **POJK 23/2015 — Insurance Product Distribution** | Agent conduct, commission arrangement transparency and disclosure — A2's 47-day disputes and A7's promises both cut across this |
| **Agent licensing regime (OJK licensing; industry certification)** | Agents must be properly licensed; app features touching advice/solicitation sit inside the licensed activity |
| **POJK 11/POJK.05/2023 — IT Implementation for Insurance Companies** | IT governance, incident reporting, outsourcing oversight for the app build (A9 item 4) |
| **UU 27/2022 — PDP Law** | Client data: lawful basis, consent records, security, breach notification — the notebooks (A5) are the headline exposure; agent tracking needs its own lawful basis |
| **UU 8/2010 (TPPU) / PPATK reporting** | Commission payouts are regulated flows — faster payouts still need AML-clean beneficiary verification |

### International standards (benchmark / contractual)

| Standard | Why it matters here |
|---|---|
| **IFRS 17 — Insurance Contracts** | Contract-level data quality for premium/commission recognition — digitizing commission data serves this (A9 item 6) |
| **IAIS Insurance Core Principles (ICPs)** | Global supervisory benchmark: conduct, outsourcing, operational resilience |
| **Solvency II (EU reference)** | Data governance and outsourcing expectations regulators increasingly reference |
| **ISO/IEC 27001:2022** | ISMS baseline for the app and any vendor |
| **FATF standards** | AML benchmark behind PPATK obligations on commission flows |

## Part 5 — Your Deliverables

1. **Iceberg clue map** — surface facts vs. what lies beneath; explicitly list the contradictions you found (there are at least two).
2. **7 Levels ladder** (L1→L7) — every level with the artifact/quote that proves it, plus the transition question you would use. Then the **reverse map** (L7→L1): from vision down to the minimum feature set.
3. **MHUI canvas** — Masalah (Environmental / Systemic / Personal), Harapan (wants vs. needs), Usaha (every past attempt, outcome, lesson), Ide (at least 3 co-created solution directions + MVP). Empty cells become your discovery questions.
4. **Discovery question plan** — the questions for your first real working session with Dewi, each tagged with target level and MHUI quadrant.
5. **Stance log** — Dewi's stance per artifact/moment (with the cue that gave it away), the agency leader's stance/concerns, and your own planned congruent stance with the switching technique you will practice.
6. **Regulatory impact note** — which instruments from Annex A touch your recommended direction (the OJK market-conduct review in A9 is live), and how the design answers them.

## Part 6 — Presentation & Defense (15 + 10 minutes)

**Present as a consultant, in this order:**
1. The real need and the evidence for it
2. The 7 Levels ladder
3. MHUI summary
4. Your stance read of this client organization
5. Recommended solution direction, MVP, and **what you deliberately will NOT build**
6. Regulatory & compliance considerations (including the OJK review)
7. Your discovery plan for the first working sessions

**Q&A includes the Stance Hot-Seat (~5 min):** the reviewer will play Ibu Dewi in a specific stance. Respond congruently — that is being assessed, not just your slides.

**One challenge you must be ready for:** *"The steering committee approved the activity tracking dashboard — HQ wants accountability. You're telling us to remove it?"*

## Part 7 — Assessment Rubric (100%)

| Criterion | Weight |
|---|---|
| 7 Levels mapping — complete, evidence-based, reaches L5+ | 20% |
| MHUI canvas — all quadrants, root causes classified, all past attempts found | 20% |
| Solution direction — co-created, outcome-driven, **regulatory aligned** | 20% |
| Stance analysis of client + your own congruent stance plan | 20% |
| Presentation & defense, including hot-seat response | 20% |

**Automatic red flags:** building a leaderboard while commissions are wrong and data lives in notebooks; shipping tracking "because the committee approved it"; treating the IT memo (A6) as a footnote; designing agent-facing tools without the agency leaders from A5 in the room; levels with no evidence.
