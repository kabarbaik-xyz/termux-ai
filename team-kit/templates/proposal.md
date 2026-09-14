<!-- DOC: proposal | version=v__ | date=__ | sources=[SRC-n,...] | upstream=prd.md v__ + prototype -->
# Proposal: <Project Title — Phase X>

**Date:** <yyyy-mm-dd>
**Prepared by:** KabarBaik
**For:** <Client Management>

## 1. Executive Summary
Formal proposal for <project>. The main objective, the solution shape (platform / architecture model), and the operational wins — 2-3 paragraphs.

### 1.1 Project Summary
| Aspect | Detail |
| :---- | :---- |
| **Project Type** | <Greenfield / New Development / Extension> |
| **Deployment Model** | <Cloud SaaS (Multi-tenant) / On-prem / Hybrid> |
| **Phase Duration** | <~N months (~M weeks)> |
| **Investment** | Rp <total IDR> (~$<USD> ) |

## 2. Background & Problem Statement
Bulleted pain points from discovery — each shaped as *risk → consequence* (what is manual/decentralized today, and what it costs the client).

## 3. Proposed Solution
One-paragraph overview, then the foundation and numbered pillars:

### 3.1. Foundation: <Architecture Model (IAM / tenancy)>
- **Dynamic organization structure:** <hierarchy levels>
- **Full data isolation:** <per-tenant rules; who sees across tenants>
- **Flexible user management:** <roles, sessions>
- **Configurable workflows:** <per-module workflow rules>

### 3.2. Pillar 1: <Module name>
- **<Feature>:** <one-line description>
- **<Feature>:** <one-line description>

### 3.3. Pillar 2: <Module name>
(Same feature-bullet pattern. One pillar per PRD module.)

## 4. Project Scope (Phase X)
This proposal specifically covers the implementation of **Phase X (<name>)** for ~N months.

### In-Scope
- **<Area>:** detailed deliverable bullets (CRUD, workflows, APIs, integrations, testing).

### Out-of-Scope
- <Explicitly excluded items>
- Third-party subscription costs (Google Cloud, payment gateways, etc.) are borne directly by the client.

### Next-Phase Scope
High-value features deliberately planned for later phases — NOT included in this budget or schedule.

## 5. Project Plan & Phases
Executed in phases with total estimate ~N months:

* **Phase <0>: <Name> (Duration: ~N weeks)**
  * **Deliverables:** <bullet per deliverable>

* **Phase <1>: <Name> (Duration: ~N weeks)**
  * **Deliverables:** grouped by module, month-by-month when the phase spans months (Month 1: …; Month 2-3: …; Testing & bug fixes last)

## 6. Budget ***
Budget breakdown for the ~N-month duration per the scope in section 5.

### Human Resources
| Role | Duration | Amount (IDR) |
| :---- | :---- | :---- |
| Project Manager | <N months> | <total> |
| Technical Lead | <N months> | <total> |
| <Developers / DevOps / UI-UX / QA> | <partial months ok> | <total> |
| **Subtotal** |  | **<total>** |

### Infrastructure & Tools
| Item | Period | Amount (IDR) |
| :---- | :---- | :---- |
| Google Cloud Platform | Monthly | 2,720,000 |
| Cloud SQL (PostgreSQL) | Monthly | 880,000 |
| Cloud Storage (4TB) | Monthly | 736,000 |
| Logging/Monitoring | Monthly | 300,000 |
| Backup & NAS | **One-time** | <amount> |
| **Subtotal** |  | **<amount>** |

### AI Operational Cost (only when the product uses AI)
| Item | Token Price | Est. Requests per 1M tokens |
| :---- | :---- | :---- |

### 6.1 Payment Terms
Based on the total budget and the agreed N-month duration:
* **Frequency:** monthly installments for the project duration.
* **Schedule (Termin):** Termin 1 at the end of month 1 — **Rp <amount>** (Nett, Excl. Tax); Termin 2 …; final termin at project close.
* **Mechanism:** progress update in the last week of each month; payment due within 3 calendar days of that update.
* **Note:** monthly amounts vary with the roles actually staffed each month. Amounts are Nett, excluding applicable tax.

*** Budget is an estimate and may change with scope finalization. Infrastructure costs are recurring monthly items borne directly by the client.

## 7. Architecture & Technology
Tech stack bullets — Frontend framework · Backend language · Package manager · Database (+extensions) · Auth · Cloud infrastructure · File storage · Version control/CI-CD.

---

Thank you for the opportunity. We are confident <solution> will be a strategic asset bringing <client>'s operations to a higher level of efficiency and competitiveness.
