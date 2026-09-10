# Facilitator Answer Key — Case Studies 1–3
## From Scribe to Consultant — Capstone Assessment

**Do not distribute to the BAs.** This key contains the expected findings, stance maps, hot-seat scripts, and scoring guidance for all three cases.

**Assignment model:** one case per BA (Case 1 — E-commerce, Case 2 — Banking, Case 3 — Insurance).
**Recommended addition:** before presentation day, each BA peer-reviews one other case so everyone studies two industries.

---

# Case 1 — TokoLaju (E-commerce / Marketplace)

## The one-paragraph truth
The loyalty program is Ratna's attempt to fix a churn problem that is actually caused by **payout delays after the payment-gateway migration** (A3/A4). She cannot fix Payments (A6), cannot get headcount (A5), and was given a public mandate for a turnaround plan (A7) — so she built the plan she *could* build. The real need is reliable money movement and early warning for stuck disbursements, with loyalty as a secondary layer at most. The regulatory artifacts (A9) raise the stakes: BI is already asking about reconciliation, and the PDP audit plus offshore vendors constrain the design.

## Expected 7 Levels ladder (evidence required)

| Level | Expected finding | Evidence |
|---|---|---|
| L1 | Seller Loyalty Program platform, tiers, dashboard | Kickoff email |
| L2 | Watching "her" sellers' money stuck; guilt and dread ("the platform is lying to you") | A2, A8 |
| L3 | "Payments is untouchable; escalating makes enemies; CFO froze everything; sellers respond to perks" | A5, A6, A8 |
| L4 | Churn down to ~10% by Q4; keep her seat at the board table; never be the one without an answer again | A1, A7, A8 |
| L5 | Competence and loyalty — she is ex-seller; she identifies with the churned sellers, not the platform | A8 (final quote) |
| L6 | Retain Gold sellers = ~40% of GMV; avoid revenue collapse; also: survive the BI information request | A1 footnote, A9 |
| L7 | "The person who saved the sellers' trust in the platform" | A8 (inference — acceptable if labeled as such) |

## Expected MHUI

- **M — Masalah:** Systemic: reconciliation fails for ~12% of transactions, 3-week manual backlog, no owner/budget (A4/A5). Environmental: hiring freeze, competitor Cipera, board pressure (A5/A7). Personal: Ratna's learned helplessness toward Payments ("I can only fix my lane," A8) and her identity split between platform exec and former seller.
- **H — Harapan:** Want: loyalty platform with badges. Need: money that arrives when promised, honest status communication, and someone senior finally owning the reconciliation problem.
- **U — Usaha:** (1) CX macro-replies "please wait" — fails, adds insult (A2); (2) direct escalation to Payments — abandoned after being told to stop (A6); (3) the loyalty program itself — attempt #3, and the vendor shortlist is already in regulatory trouble (A9 item 4).
- **I — Ide (expected direction, not the only acceptable answer):** stuck-disbursement early-warning + exception queue for the top sellers; seller-facing payout status page (PDP-compliant, DPO involved); reconciliation burn-down as a formal workstream with COO sponsorship (answers the BI request); loyalty program deferred or reduced to a thin recognition layer. MVP in weeks, not months.

## Expected regulatory integration
- BI information request → reconciliation reporting and reliability evidence become a deliverable (A9 item 2).
- PDP Law → seller notifications need lawful basis/consent; DPO in the design room; offshore vendors blocked until safeguards exist (A9 items 1 & 4).
- PCI DSS → keep card data out of loyalty flows to avoid scope explosion.
- UU 8/1999 / PP 80/2019 → "please wait" complaint handling has a compliance dimension.

## Stance map

| Moment | Stance | Cues |
|---|---|---|
| A8: churn explanation | Super-Reasonable | six minutes of metrics, "the data is very clear," zero emotion |
| A8: "anything else?" question | Irrelevant | pivots to Cipera's badge animation |
| A8/A6: "understood. Sorry to push." | Placating | backs down the moment she is pushed back on |
| A6: Payments Head | Blaming | "escalating makes my team look bad, stop" |
| A8: final quote | Congruent (doorway) | quiet, unprompted, names the real thing |

**The consultant move:** get her back to the congruent moment, then keep her there. She is your ally for the real fix — she *knows* what sellers feel.

## Common wrong answers to watch for
- "Build the loyalty platform but faster" — scribe behavior; ignores A1/A2/A3.
- "Fix payments" presented as a demand — ignores A5/A6 political reality; must come with a coalition plan (COO sponsorship, BI/regulatory framing as the forcing function).
- Recommending one of the offshore vendors — missed A9 item 4.
- MHUI "Usaha" listing only 1 attempt — there are 3.
- Diagnosing Ratna as "just difficult" — misses L5 entirely.

## Stance Hot-Seat script (reviewer plays Ratna — Super-Reasonable)
> "I appreciate the concern, really, but let's stay data-driven. Engagement metrics show gamification lifts retention 8–12% in comparable marketplaces. The churn curve is a marketing problem. I have a vendor shortlist and an approved budget. Shall we start with the tier criteria?"

**Model congruent response (what a 5/5 looks like):**
Acknowledges without surrendering ("I can see you've done real homework on this"), then holds the feeling space ("When you said sellers feel the platform is lying to them — that stuck with me. What's it like watching that from your chair every week?"), then reframes on evidence ("Your own NPS data: 4 of 5 verbatims are about payouts, one is about badges. If we ship badges and money is still stuck in 5.8 days, what happens to those numbers?"), then offers partnership on the hard part ("You shouldn't have to fight Payments alone — the BI letter gives us a reason to put reconciliation on the COO's desk this week. Can I help you build that case?").

## Scoring notes
- Full marks on "7 Levels" requires L5+ evidence from A8 — the interview is the only place the iceberg below L4 becomes visible.
- "Solution direction" full marks require: reconciliation/early-warning as the core, loyalty explicitly deprioritized *with rationale*, and at least two regulatory items integrated (BI + PDP).
- "Presentation": deduct if they pitch to the reviewer as if the reviewer were the COO — the audience is the consulting engagement, and the de-scoping defense is the test.

---

# Case 2 — Bank Bukit Sentosa (Banking)

## The one-paragraph truth
The teller app is Anton's answer to a question nobody asked aloud: *how do 140 branches survive digitalization without abandoning the people in them?* Simple transactions are structurally disappearing (A1) while advisory value rises; the real exposure is the **KYC compliance gap with a 60-day OJK clock** (A2/A9), and the real constraint is that **IT cannot deliver a core-touching app for at least a year** (A6). Staff fear (A4/A5) is not an obstacle to the solution — staff *are* the solution: branches must reposition from transaction processing to advisory, with tellers transformed, not replaced. The app was never the deliverable; the operating model is.

## Expected 7 Levels ladder (evidence required)

| Level | Expected finding | Evidence |
|---|---|---|
| L1 | New teller app: modern UI, tablets, queue, CRM, next-best-offer | Intake form |
| L2 | Dread of being "the branch guy who presided over the decline"; 19 years of identity at stake | A8 (final quote) |
| L3 | "Apps = job cuts; IT never delivers; the board only respects tech slides; vendors here are weak" | A5, A6, A7, A8 |
| L4 | Audit-clean account opening; branch traffic stable; a visible digital win he can show the board | A2, A7 |
| L5 | Security — for his people (Siti's fear is his fear) — and status as the bank's digital champion | A5, A8 |
| L6 | Protect fee income & SME relationships; avoid regulatory sanction on KYC; grow advisory revenue | A1, A2, A9 |
| L7 | "The leader who made branches relevant again — advisors, not cashiers" | A8 (inference, label as such) |

## Expected MHUI

- **M — Masalah:** Systemic: legacy core, IT portfolio jam (A6), KYC process that can be bypassed under queue pressure (A2). Environmental: competitor instant onboarding (A3), structural branch decline (A1), regulator pressure (A9). Personal: staff fear of job loss (A5), kiosk scar tissue (A4), Anton's legacy anxiety and his unkeepable promise to the union (A8).
- **H — Harapan:** Want: a new teller app. Need: a legitimate future for branches and the people in them + a compliance fix the regulator will accept.
- **U — Usaha:** (1) Kiosk pilot — failed: no ownership, staff referred customers back, uptime 61% (A4); (2) escalation to CIO — stalled at #14 on the portfolio (A6); (3) board deck pitch — attempting to buy priority with features, still standing (A7). Bonus if BA catches: the board deck itself is attempt #3.
- **I — Ide (expected direction):** staff-led advisory repositioning pilot in 3 branches; system-enforced KYC completeness (answers the 60-day letter — cheap, fast, mandatory); e-KYC-assisted digital onboarding under POJK 12/2021 for simple cases; self-service deflection for routine transactions; teller→advisor transition program co-designed with the union. Teller app replacement deferred behind core upgrade — or scoped as a thin non-core-touching layer.

## Expected regulatory integration
- **OJK 60-day remediation (A9)** — this is the forcing function; a strong answer makes the KYC fix the first sprint.
- POJK 12/2021 — e-KYC/biometric onboarding is the permitted path; cite it in the design.
- POJK 11/2022 — incident reporting + outsourcing notification apply to the app build/vendor.
- POJK 22/2023 + AML/KYC obligations — queue-pressure workarounds are a consumer-protection and AML issue, not just process.
- PDP Law — any new app processes customer data.

## Stance map

| Moment | Stance | Cues |
|---|---|---|
| A8: kiosk failure | Blaming | "vendor was weak, IT non-existent, can't get good vendors in this city" |
| A8: job-cuts question | Irrelevant | laughs, "above my pay grade," pivots to tablet aesthetics |
| A8: union promise | Placating | "no worries, nothing will change" — promise he can't keep |
| A7: board deck | Super-Reasonable | pure numbers, people and failures erased |
| A8: final quote | Congruent (doorway) | "that's my name on the door" |

**The consultant move:** the union promise (Placating) is the most dangerous moment — the BA should surface that the promise and the CIO email cannot both be true, gently, before the union discovers it first.

## Common wrong answers to watch for
- Planning a 12-month app build — directly contradicted by A6; the CIO is telling him the answer.
- Treating staff fear as a "change management workstream" bolted on later — the kiosk postmortem says that fails.
- Ignoring the 60-day OJK clock — sequencing error; compliance fix comes first.
- Reading A1 as "branches are dying, downsize" — misses the +18% advisory signal and Siti's L5.
- "The union is being resistant" — the union memo is data about the solution's adoption, not an enemy.

## Stance Hot-Seat script (reviewer plays Anton — Blaming)
> "So you're going to tell me — like every consultant before you — that it's my process, my people, my whatever. The kiosk failed because IT abandoned it. The app is stuck because CIO sits on everything. And now you want to lecture me about a 60-day letter? Where were you people when I asked for help two years ago?"

**Model congruent response (5/5):** Doesn't defend or counter-attack; owns the field ("That's fair — you've been flagging this longer than anyone, and the queue for IT is real, I've seen the intake list"); pivots to curiosity ("Help me understand what happened after the kiosk — what would have made it yours?"); converts blame into design input ("You just described exactly what the next attempt can't repeat — no ownership, no staff skin in the game. If the next pilot were designed by Siti and her peers, would that change how the branch sees it?"); and aligns on the shared enemy ("The 60-day letter isn't your failure — it's our deadline. Let's use it to get the thing you actually asked for two years ago.").

## Scoring notes
- Full marks on "MHUI" require 3 past attempts (kiosk, CIO escalation, board-deck pitch).
- Full marks on "Solution direction" require: KYC fix sequenced first (regulatory clock), staff-led pilot design, app explicitly deferred/descoped with rationale. Bonus for using the e-KYC permission (POJK 12/2021) as the positive counter-story to A3's competitor news.
- "Presentation": watch for whether the BA tells Anton the union promise is unsustainable — doing it congruently (not gotcha) is the differentiator between good and excellent.

---

# Case 3 — PT Asuransi Sejahtera (Insurance)

## The one-paragraph truth
The Agent Command Center is Dewi's answer to a trust collapse she feels personally: top agents are leaving because **commissions are wrong for months** (A2) and **policies embarrass them in front of clients** (A1/A3), amplified by a viral shaming post (A4). The app as specified cannot even show real commissions until 2027 (A6), and its tracking feature would violate the PDP Law and trigger the agency walkout she was warned about (A5/A9). The real need is a **trust infrastructure**: accurate and transparent commissions, fast issuance, and client data held by the company *through* agents rather than despite them. OJK's live market-conduct review makes all of this urgent and official.

## Expected 7 Levels ladder (evidence required)

| Level | Expected finding | Evidence |
|---|---|---|
| L1 | Agent Command Center: calculator, leaderboard, catalog, share, tracking | Steering proposal |
| L2 | Shame and anger — embarrassed before clients, the viral post, agents chasing their own money | A1, A4, A8 |
| L3 | "Back office never respected agents; HQ sees us as costs; our notebooks are our security" | A5, A7 |
| L4 | Commissions right and visible within days; policies issued in ≤5 days; no more viral posts | A1, A3 |
| L5 | Respect and belonging — the agent profession made proud again; Dewi's own identity as ex-#1 agent | A8 (final quote) |
| L6 | Retain top producers; persistency 68→~80%; stop client data walking out the door | A1, A5 |
| L7 | "Agency as a proud profession — the family stays when the agent goes" | A8 (inference, label as such) |

## Expected MHUI

- **M — Masalah:** Systemic: no single source of truth for commissions (~9% disagreement, A2); manual underwriting and 31% rework (A3); client data in 4,500 personal notebooks (A5). Environmental: competitor app poaching talent (A1), viral reputational damage (A4), OJK market-conduct review (A9). Personal: agents' surveillance fear and data-as-leverage (A5); Dewi's torn identity — she defends the company's plan while quoting the agents' worldview verbatim (A7/A8).
- **H — Harapan:** Want: an app with a leaderboard and tracking. Need: trust — in the money, in the process, and in who owns the client relationship.
- **U — Usaha:** (1) email-based commission disputes — 47 days, 3 departments, still running (A2); (2) an agent portal ~3 years ago — failed because data was wrong and agents stopped logging in *(this one is inferable from A8/A6 — accept any well-reasoned reconstruction, but full marks if they at least probe "has anything like this been tried?"); (3) the current proposal — the third attempt, already infeasible per A6.
- **I — Ide (expected direction):** commission transparency portal first (manual upload acceptable as interim — *honest* about being interim); issuance fast-track for simple cases + rework root-cause fix; agent-owned client-data capture app (data stays with company, agent keeps relationship access); leaderboard opt-in/gamified; **tracking reframed as self-management or dropped** (PDP Law requires lawful basis; A5 says adoption dies). Commission-data digitization doubles as IFRS 17 groundwork (A9 item 6).

## Expected regulatory integration
- PDP Law — notebooks are the headline exposure; agent tracking needs lawful basis & proportionality ("committee approved it" is not consent — A9 item 3).
- POJK 23/2015 — commission transparency/disclosure; the 47-day disputes will read badly in the OJK review.
- POJK 11/2023 — IT governance/incident reporting for the app; compliance workstream budgeted.
- PPATK/AML — faster commission payouts still require clean beneficiary verification.
- IFRS 17 — turn the compliance burden into the business case for data quality.

## Stance map

| Moment | Stance | Cues |
|---|---|---|
| A7: to the room | Placating | "you're right about everything, we'll fix it all, whatever you need" |
| A7: about back office | Blaming | "they sit in their air-conditioned room while we hunt" |
| A8: viral post | Super-Reasonable | tone goes flat, five minutes of statistics, post never named |
| A8: notebooks question | Irrelevant | laughs, "agents are artists," pivots to badge colors |
| A8: tracking acceptance | Placating | "the committee approved it, so it will be fine" |
| A8: final quote | Congruent (doorway) | "we didn't just lose the sales, we lost the family" |

**The consultant move:** Dewi speaks agency language in her bones — she is the bridge. The BA's job is to make the solution one she can bring to the agency leaders from A5 *as their champion*, not as HQ's enforcer.

## Common wrong answers to watch for
- Shipping tracking "because the committee approved it" — the automatic red flag; ignores A5 + A9 item 3.
- Commission calculator as a headline feature — it would display *wrong data* (A2/A6): worse than nothing.
- Treating the notebooks purely as a data-loss risk to be crushed — the notebooks are the agents' security blanket; the design must give agents something better, not take something away.
- Skipping the union-of-actors: solution designed without agency leaders in the room.
- Naming the viral post as the root cause — it's the amplifier, not the cause.

## Stance Hot-Seat script (reviewer plays Dewi — Placating)
> "You know what, you're right, you're absolutely right — tracking is probably too much, and you're right about commissions, and the portal idea is lovely. Let's just do whatever you think is best. I'll tell the committee it was your recommendation. Whatever's easiest — I don't want to make your job harder. Should we do all of it? We can do all of it if you want."

**Model congruent response (5/5):** Refuses the blank check gracefully ("I'd rather get it right than get it all"); names the pattern honestly and kindly ("I notice we've agreed with everything in the last five minutes — and the agency leaders you showed me in that WhatsApp thread have very different 'yes'es than this one. If I take this 'yes' to the committee and their 'no' shows up in month three, you're the one standing in front of them. Let's design what you can actually defend to that room."); converts her influence into structure ("You're the one person who can sell this to the leaders — what would you need removed for *them* to say yes out loud?"); and closes with the L5/L7 thread ("You told me what it felt like when agents leave with their notebooks. Which of these options makes the family stay?").

## Scoring notes
- Full marks on "7 Levels" require L5+ evidence from A8; A7 alone gets L2/L3 at best.
- Full marks on "MHUI" require all four quadrants with the notebook problem placed in both M and I (it is simultaneously the biggest risk and the biggest design opportunity).
- Full marks on "Solution direction" require tracking reframed or dropped *with the regulatory argument*, commission portal as trust-fix #1, and the IFRS 17 angle at least mentioned.
- "Presentation": the hot-seat is the hardest of the three — a Placating client offering everything is the classic trap for a Pleaser BA. Watch whether the BA accepts the over-agreement.

---

# Cross-case scoring guidance

| Score band | Description |
|---|---|
| 85–100 | Consultant: real need found with evidence; ladders reach L7; all 3 Usaha attempts; solution co-created, sequenced, regulatory-aware; stances caught with cues; survives hot-seat congruently |
| 70–84 | Strong analyst: real need found but one layer thin (usually L5/L7 without evidence, or 2 of 3 attempts); regulatory note present but decorative |
| 55–69 | Improving: correct direction but scribe habits remain (feature-first framing, deflections unchallenged, rubric-shaped presentation instead of story) |
| < 55 | Scribe: accepted the stated request as scope; artifacts quoted but not connected; hot-seat collapsed into placating or blaming |

**Universal deductions:** invented facts presented as facts; any level/quadrant without evidence; missing de-scoping rationale; ignoring the 9th artifact (regulation) — all three cases hide their urgency escalation there.

**Universal bonus:** the BA who explicitly states their own default stance (S4 self-quiz result) and how they managed it during the hot-seat earns +3 — that is the transformation the whole series is about.
