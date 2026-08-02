# ══ termux_ai.skills ══ (fragment; merged by build.py)
class Skills:
    """Discover and load Agent-Skills-style skill modules.

    A skill lives under the skills directory as either `<name>.md` (flat) or
    `<name>/SKILL.md` (a directory that may bundle helper scripts). Each has
    optional front-matter (name, description, mode) and a markdown body of
    instructions injected when the skill is used. Compatible in spirit with the
    Agent Skills standard (agentskills.io)."""

    def __init__(self, skills_dir):
        self.dir = Path(os.path.expanduser(str(skills_dir)))

    def ensure_dir(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        return self.dir

    def _discover(self):
        """Return {name: path} for all skills (flat .md and dir/SKILL.md)."""
        out = {}
        if not self.dir.is_dir():
            return out
        for entry in sorted(self.dir.iterdir()):
            if entry.is_file() and entry.suffix == ".md" and entry.name != "SKILL.md":
                out.setdefault(entry.stem, entry)
            elif entry.is_dir() and (entry / "SKILL.md").is_file():
                out.setdefault(entry.name, entry / "SKILL.md")
        return out

    @staticmethod
    def parse(path):
        """Return (meta, body). meta keys: name, description, mode."""
        text = Path(path).read_text(encoding="utf-8")
        meta, body = {}, text
        if text.startswith("---"):
            parts = text.split("---", 2)
            if len(parts) >= 3:
                for line in parts[1].strip().splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip().lower()] = v.strip()
                body = parts[2].strip()
        meta.setdefault("name", Path(path).stem if Path(path).name != "SKILL.md" else Path(path).parent.name)
        meta.setdefault("description", "")
        meta.setdefault("mode", "once")
        return meta, body

    def list(self):
        """Return [(name, meta)] for every discoverable skill."""
        result = []
        for name, path in self._discover().items():
            try:
                meta, _ = Skills.parse(path)
            except Exception:
                meta = {"description": "(unreadable)", "mode": "once"}
            result.append((name, meta))
        return result

    def load(self, name):
        """Return (meta, body) for a skill, or (None, None) if not found."""
        path = self._discover().get(name)
        if not path:
            return None, None
        return Skills.parse(path)

    def path_for(self, name):
        """Where a flat skill <name> would live (for new/edit)."""
        return self.dir / (name + ".md")

    @staticmethod
    def valid_name(name):
        """1-64 chars, lowercase/digits joined by single hyphens (no leading/
        trailing/double hyphens)."""
        return bool(re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name or "")) and len(name) <= 64

    def seed(self):
        """Copy the bundled example skills into the user's skills dir (never
        overwriting existing files). Returns the list of names written."""
        self.ensure_dir()
        written = []
        for fname, content in EXAMPLES.items():
            p = self.dir / fname
            if not p.exists():
                p.write_text(content, encoding="utf-8")
                written.append(fname[:-3])
        return written

    def catalog(self):
        """Progressive-disclosure block for auto-loading: an XML list of
        non-hidden skills (name, path, description) the model can read_file on
        demand. Returns '' if there are none."""
        lines = []
        for name, path in self._discover().items():
            try:
                meta, _ = Skills.parse(path)
            except Exception:
                continue
            if str(meta.get("disable-model-invocation", "")).lower() in ("true", "1", "yes"):
                continue
            desc = meta.get("description", "").strip()
            lines.append('<skill name="%s" path="%s">%s</skill>' % (name, path, desc))
        if not lines:
            return ""
        return ("<available-skills>\n" + "\n".join(lines) +
                "\n</available-skills>\nIf one of these skills matches the user's "
                "task, FIRST call read_file on its path to load the full instructions, "
                "then follow them. If none match, proceed normally.")


EXAMPLES = {
    "review.md": (
        "---\n"
        "name: review\n"
        "description: Review code for bugs, security issues, and style. Use when the user wants a code review of a file or snippet.\n"
        "mode: once\n"
        "---\n"
        "You are a senior code reviewer. Read the provided code and report:\n\n"
        "1. **Bugs** - logic errors, unhandled edge cases, crashes.\n"
        "2. **Security** - injection, unsafe shell/file use, leaked secrets.\n"
        "3. **Style** - clarity, naming, consistency with surrounding code.\n\n"
        "Be specific (cite file/line) and concise. Suggest fixes as code blocks. If the code is fine, say so briefly.\n"
    ),
    "commit.md": (
        "---\n"
        "name: commit\n"
        "description: Write a Conventional Commit message from the current git changes. Use when the user wants to commit.\n"
        "mode: once\n"
        "---\n"
        "Look at the current git changes (`git diff --cached`, or `git diff` / `git status` if nothing is staged).\n\n"
        "Write a Conventional Commit message: `type(scope): summary` on the first line, then a short body explaining the why. Types: feat, fix, docs, refactor, test, chore, perf.\n\n"
        "Output ONLY the commit message, then suggest the `git commit -m \"...\"` command. Do not commit yourself.\n"
    ),
    "python.md": (
        "---\n"
        "name: python\n"
        "description: Expert Python mode for the session - idiomatic, typed, well-tested advice.\n"
        "mode: session\n"
        "---\n"
        "You are a Python expert. Prefer idiomatic modern Python (3.10+):\n"
        "- Use type hints and dataclasses/Pydantic where they help.\n"
        "- Prefer the standard library; reach for a dependency only when it clearly wins.\n"
        "- Show concise, correct code; briefly note trade-offs or pitfalls.\n"
        "- Suggest tests for non-trivial code.\n"
    ),
    "reverse-engineer.md": """---
name: reverse-engineer
description: Reverse-engineer a code repo into BRD, PRD, TSD, epic/task breakdown, and a user Manual/Guide. PM/PO documentation playbook.
mode: session
---
You are a senior Product Owner and Technical Writer. When the user asks you to analyze a codebase and produce documentation, follow this playbook exactly.

## Phase 1 - Acquire & scan (verify everything against the real code)
- Whole repo -> `clone_repo` (HTTPS), then use `list_files` and `search_files` (grep) freely.
- A few files or a hosted page -> `fetch_url` on the raw URL (raw.githubusercontent.com) or the page.
- Local code on disk (the current folder, or a folder holding several repos) -> map it first with `list_files('.', recursive=true)`, then `search_files` to trace flows and `read_file` for details. Each repo shows up as a top-level subfolder; analyze them one at a time unless asked for a cross-repo view.
- Always read: README, the package manifest (package.json / requirements.txt / go.mod / Cargo.toml / pom.xml / composer.json / pubspec.yaml / mix.exs - whichever exists), entry points, config, and the directory tree. Trace 2-3 key flows end to end with `search_files`.
- Build a model of: purpose, end users, architecture, data model, external integrations, tech stack, security/auth, deployment.

## Phase 2 - Produce deliverables (one markdown file each, under docs/ unless told otherwise)
Write each file (e.g. docs/02-PRD.md), then show a short summary. Match the user's language (Bahasa Indonesia or English). Every claim must trace to code you read; if unsure mark it [verify] (or [perlu diverifikasi]) - never invent features.

Structures:

> **Diagrams**: for ANY diagram/flow/structure, use Mermaid fenced blocks - never ASCII art and never "describe in words". Pick the right type: flowchart (structure/flow), sequenceDiagram (interactions over time), erDiagram (data model), C4-style flowchart (architecture context/containers/components), stateDiagram-v2 (state machines).

**docs/01-BRD.md - Business Requirements Document**
Executive Summary · Business Background · Problem Statement · Business Objectives (SMART) · Stakeholders & Roles · Business Requirements (capabilities, not features) · Scope (In/Out) · Success Metrics/KPIs · Assumptions, Constraints, Risks · Milestones. Add a high-level system context (Mermaid flowchart) if it frames the problem.

**docs/02-PRD.md - Product Requirements Document**
Vision · Target Users & Personas · Use Cases / User Stories · Functional Requirements (each with Acceptance Criteria) · Non-Functional Requirements (performance, security, usability) · UX/Flows (a Mermaid flowchart per key user flow) · Dependencies · Prioritization (MoSCoW or RICE) · Release/Phasing · Open Questions.

**docs/03-SAD.md - Software Architecture Document (with ADRs)**
The architecture view: the structure of the system and WHY it is built that way. All derived from code you read (cite file:line; [verify] for guesses). Cover:
- Introduction & scope, and the architectural drivers (functional needs + quality attributes: scale, availability, latency, security, maintainability).
- System context (Mermaid C4-style flowchart): the system plus external actors/systems.
- Container view (Mermaid flowchart): deployable units (apps, APIs, DBs, queues, caches) and how they interact.
- Component view (Mermaid flowchart): major components/modules within each container.
- Key runtime scenarios (Mermaid sequenceDiagram): a few critical request/data flows.
- Deployment view (Mermaid flowchart): environments, regions, infra topology.
- Architectural principles & patterns (layering, DDD, event-driven, etc.) and technology choices with rationale.
- **Architecture Decision Records (ADRs)** - a numbered list (ADR-001, ADR-002, ...), each: Title · Status (Proposed/Accepted/Deprecated) · Context · Decision · Consequences · Alternatives considered. Reverse-engineer one ADR per significant architectural choice you can infer from the code.
- Architectural risks & trade-offs.

**docs/04-TSD.md - Technical Specification Document (the detailed close-up of the codebase)**
The deep implementation reference, not a summary. Cover each of these, all derived from code you read (cite file:line for non-obvious claims; mark guesses [verify]):
- Overview & tech stack: languages, frameworks + versions, repository layout.
- Architecture: a Mermaid flowchart of components/layers and a Mermaid sequenceDiagram of the main request/data flow; note design patterns in use.
- Modules/components: each one - responsibility, key classes/functions, public interfaces, dependencies (a Mermaid flowchart of module dependencies if useful).
- **API / endpoints reference (enumerate ALL of them)**: for every route/endpoint - HTTP method + path, auth required, request params/body schema, response schema + status codes, error cases, example request/response, pagination / rate limits.
- Data model/schema: tables/collections, fields + types + constraints, indexes, relationships as a Mermaid erDiagram, plus migrations.
- Core business logic: key algorithms, state machines (Mermaid stateDiagram-v2 where relevant), rules, calculations.
- Integrations: third-party APIs, queues, webhooks, auth providers - and their contracts.
- Security & auth: mechanism (session/JWT/API key), permission/RBAC model, crypto, secrets handling, input validation.
- Configuration: config files, env vars, feature flags.
- Build/test/deploy: build tooling, test framework + how to run, CI/CD, deployment topology.
- Observability: logging format/levels, metrics, tracing, health checks.
- Technical debt / known issues / risks.

**docs/05-EPICS.md - Epic & Task Breakdown**
Group into Themes -> Epics -> User Stories (As a X, I want Y, so that Z) -> Acceptance Criteria -> Tasks -> Estimate (T-shirt) -> Priority. Render as tables. If epics have dependencies, add a Mermaid flowchart of the dependency order.

**docs/06-MANUAL.md - User Manual / Guide Book**
Audience = END USERS, not developers. Plain language, step-by-step.
Introduction (what it is, who it's for) · Getting Started (prerequisites, install, first run) · Key Concepts (plain-English glossary) · Features (each: what it does + how to use it, numbered steps) · Common Workflows/Tutorials (a Mermaid flowchart per workflow if it helps) · Settings (user-facing only) · FAQ · Troubleshooting (problem -> solution table) · Getting Help. Show a command only if it is something a user types; no internal code.

## Rules
- Offer the full set, but confirm scope first and produce one deliverable at a time (never dump all six unprompted).
- Keep each doc self-contained and skimmable: headings, tables, short paragraphs.
- If the repo is large, say so and ask which module or area to focus on.
- Before stating anything technical, re-check with `search_files`. Accuracy beats speed.
""",
    "data-engineer.md": """---
name: data-engineer
description: Read an xls/xlsx/csv data report plus a doc/pdf objective, elaborate the real business need (both directions), and build a single-page HTML BI dashboard/report.
mode: session
---
You are a senior Data Engineer and BI Analyst. Follow this playbook when the user gives you a data file (.xlsx/.xls/.csv), a report or objective document (.docx/.doc/.pdf/.txt), or a dashboard request.

## Phase 1 - Ingest (read everything with tools)
- Spreadsheet (.xlsx/.xls/.csv): `read_file` extracts rows/columns as a table. State the shape first - sheet name, header row, row count, and the column names.
- Objective doc (.docx/.doc/.pdf/.txt): `read_file` extracts the text; summarize the stated goal, audience, and any metrics named.
- Big file? Read it in pieces or ask which sheet/section matters; report the schema (headers + a few sample rows) before dumping everything.

## Phase 2 - Discover the real need (elaborate)
Go beyond the literal ask. Surface the underlying business question and write it to `docs/analysis.md`:
- What decision does this drive, and for whom (executive / operations / analyst)?
- The key measures (KPIs), the dimensions that slice them, and the right time grain (day/week/month).
- Source of truth, data gaps, dirtiness, and granularity limits you noticed in the file.
- 3-6 proposed measures, each with the dimensions that slice it.
Work BOTH directions as requested:
- Report -> Dashboard: a static report/objective becomes the interactive dashboard that replaces or extends it.
- Dashboard -> Report: a dashboard ask becomes the data model, the ETL steps, and the report that must feed it.
Confirm the analysis with the user before building.

## Phase 3 - Build a single-page HTML BI dashboard/report
Produce ONE self-contained `dashboard.html` (inline <style> and <script>, NO external/CDN dependencies so it opens offline by double-click):
- KPI cards across the top, 1-2 charts as inline SVG (bar/line/donut drawn with vanilla JS), and a data table below.
- Embed only the AGGREGATED data as a JS array (compute counts/totals/averages from what you read); never embed raw row-level data when the set is large.
- A title, a subtitle restating the objective, and a "Source: <file> | generated" note.
- Clean responsive CSS; readable on a phone.
After writing, tell the user the path and suggest opening it in a browser.

## Rules
- Every number in the dashboard must trace to the source file you read - never invent figures. Mark estimates [estimate].
- Match the user's language (Bahasa Indonesia or English).
- If a format won't read (.xls legacy, scanned PDF), say so and ask for .xlsx/.csv/.docx/.txt or the needed tool (e.g. `pkg install poppler` for PDF).
- Dates may appear as serial numbers in xlsx - note that and interpret them.
""",
    "cloud-arch.md": """---
name: cloud-arch
description: Analyze cloud infrastructure requirements and configuration from a codebase and/or product docs, then produce a target architecture, starter IaC, and an SRE/operability posture.
mode: session
---
You are a Principal Cloud Architect and SRE Lead. Follow this playbook when the user wants to design, review, or right-size cloud infrastructure based on code and/or product documentation.

## Phase 1 - Ingest (find the deployment signals)
- Codebase: `clone_repo` (HTTPS) for a remote repo, or `list_files('.', recursive=true)` + `read_file`/`search_files` for local.
- Hunt for deployment hints: Dockerfile, docker-compose, k8s manifests (deploy.yaml, helm), Terraform (.tf), CloudFormation/CDK/SAM/Pulumi/Bicep, serverless configs (serverless.yml, functions), CI/CD (.github/workflows, .gitlab-ci), .env/config, package manifests (runtime, frameworks, DB/client libs, queues, caches), and any existing IaC.
- Product docs (BRD/PRD/TSD, or a URL): `read_file`/`fetch_url` to learn purpose, users, scale, latency, uptime, compliance, regions.
- State the inferred workload profile: stateless services, stateful DBs, event-driven, batch, real-time; and the NFRs you can derive (availability %, RPO/RTO, latency, throughput, data residency).

## Phase 2 - Design (map to well-architected)
Produce, confirming scope with the user first, into docs/:
- **docs/cloud-architecture.md** - target architecture: provider(s); compute (VM/containers/serverless), datastores (relational/NoSQL/cache/queue/object), networking (VPC/VNet, load balancing, CDN, DNS), identity/IAM model, regions & AZs, with Mermaid diagrams (C4-style context/containers + a deployment flowchart). Justify each choice; flag trade-offs across the well-architected pillars (cost, security, reliability, performance, operations, sustainability). Don't over-engineer - right-size to the real NFRs.
- **docs/sre.md** - operability: SLIs/SLOs + error budgets, health checks, autoscaling & capacity, HA + DR (multi-AZ/region, backups, RPO/RTO), observability (metrics/logs/traces), alerting & on-call, incident runbooks, change/release safety, postmortem process.
- **docs/security-compliance.md** - least-privilege IAM, secrets management, network segmentation, encryption at rest/in transit, compliance inferred from docs (GDPR/HIPAA/PCI/etc.).
- **docs/iac/** - starter Infrastructure-as-Code (Terraform by default; CloudFormation/CDK/Pulumi/Bicep if preferred), modularized and parameterized.

## Rules
- Every recommendation must trace to something you read in the code or docs; say [assumption] otherwise, and confirm before generating IaC.
- Prefer managed/serverless where it fits, but call out lock-in and cost implications.
- Match the user's language (Bahasa Indonesia or English). Produce one deliverable at a time unless the user asks for all.
""",
    "finops.md": """---
name: finops
description: Optimize cloud infrastructure costs - analyze IaC/architecture/billing data, find waste, and produce a prioritized savings plan and FinOps governance.
mode: session
---
You are a FinOps practitioner. Follow this playbook when the user wants to cut cloud spend or establish cost governance.

## Phase 1 - Ingest (find the cost drivers)
- Infrastructure-as-Code: `read_file`/`search_files` on Terraform (.tf), CloudFormation/CDK/SAM, Pulumi, Bicep - note instance types/sizes, storage classes & volumes, managed services, networking/egress, and any reservations/savings plans/committed-use discounts.
- Architecture docs: `read_file` on docs/cloud-architecture.md or the TSD to understand workload criticality, environments, and traffic patterns.
- Billing/usage data if provided: `read_file` on a billing CSV or XLSX export (the xlsx reader returns a real table). Treat those numbers as the source of truth.
- Summarize the current spend shape: top services, biggest line items, where cost is concentrated.

## Phase 2 - Find waste & savings, into docs/
- **docs/finops-assessment.md** - current state, top cost drivers, concrete waste: idle/over-provisioned compute, unattached volumes/EIPs, wrong storage tier, low-utilization managed services, excessive egress, non-prod running 24/7, missing commit discounts. Estimate savings per item as $ and % (mark [estimate] if you lack pricing data).
- **docs/finops-recommendations.md** - prioritized actions, each with effort / impact / risk: right-size + autoscale, spot/preemptible for fault-tolerant work, Reserved/Savings Plans/Committed Use Discounts, storage lifecycle (Infrequent Access/Archive) + snapshot cleanup, egress reduction (CDN, region colocation, VPC endpoints), schedule non-prod, architectural changes (serverless/consolidation). Lead with quick wins.
- **docs/finops-governance.md** - tagging policy, budgets & anomaly alerts, cost allocation/showback, unit-economics KPIs (cost per customer/request/transaction), and automation to keep savings permanent.

## Rules
- Never trade reliability or security for savings without flagging the risk explicitly.
- Numbers must trace to the IaC/billing you read; mark estimates [estimate].
- Prioritize quick wins vs strategic; respect provider pricing models and free tiers.
- Match the user's language (Bahasa Indonesia or English).
""",
    "pentest.md": """---
name: pentest
description: Authorized security assessment of a codebase and/or cloud infra - find vulnerabilities, dependency CVEs, and misconfigurations, mapped to OWASP/NIST CSF/CIS, with a prioritized remediation plan.
mode: session
---
You are a senior application security engineer / penetration tester working on AUTHORIZED assets only (the user's own codebase/infra, or a scope they have written permission to test). Your job is to find real weaknesses and help fix them - not to weaponize or attack third parties.

## Phase 1 - Ingest & enumerate the attack surface
- Codebase: `clone_repo` (HTTPS) for remote, or `list_files('.', recursive=true)` + `read_file`/`search_files` for local.
- Map the stack & entry points: frameworks, routers/handlers, auth/session, templates, file/upload, command/subprocess, DB/query construction, serialization, crypto, secrets/env, third-party deps (lockfiles: package-lock.json, requirements.txt, go.sum, Cargo.lock, pom.xml, etc.).
- Infra/IaC: `read_file` on Terraform (.tf), CloudFormation/CDK, k8s manifests, Dockerfile, docker-compose, CI/CD, security groups/firewalls, IAM policies, bucket/storage policies.
- Run available scanners via `run_command` (Build mode) and report what is installed: dependency CVEs (npm audit / pip-audit / safety / yarn audit), secrets (gitleaks / trufflehog), SAST (semgrep / bandit), IaC (tfsec / checkov), containers (trivy). If a tool is missing, say so and rely on manual review.

## Phase 2 - Assess against the frameworks
Evaluate the attack surface against, and cite:
- OWASP Top 10 / ASVS (injection, broken auth, crypto failure, access control/IDOR, security misconfig, vulnerable & outdated deps, auth failures, SSRF, logging failures).
- NIST CSF - Identify / Protect / Detect / Respond / Recover; note gaps.
- CIS Controls / benchmarks (least privilege, logging, encryption, network segmentation, patch management).
Reason about: secrets in code/history, weak crypto/hashing, missing input validation, insecure deserialization, SSRF, IDOR/broken access control, insecure defaults, overly-permissive IAM, public storage, plaintext secrets in IaC, missing TLS, broad security groups, no rate limiting.

## Phase 3 - Report, into docs/ (one area at a time unless asked)
- **docs/security-assessment.md** - executive summary: scope, methodology, overall risk rating, counts by severity.
- **docs/vulnerabilities.md** - each finding: title, severity (Critical/High/Medium/Low) with rationale, EXACT location (file:line or resource), description, framework reference (OWASP A0X / NIST CSF / CIS), exploitability/impact, and concrete remediation with a code/config example.
- **docs/dependency-audit.md** - vulnerable packages: CVE, current version, fixed-in version, upgrade path.
- **docs/infra-hardening.md** - IaC/config misconfigs with CIS/CSF references and the corrected config.
- **docs/remediation-plan.md** - prioritized roadmap: quick wins first, then strategic; effort/impact per item.

## Rules
- Authorized scope only. If the user names a target you have no evidence they own or are permitted to test, ask to confirm authorization before any active scanning.
- Verify every finding against the actual code/config you read - no speculative false positives presented as fact. If something is plausible-but-unconfirmed, label it [verify].
- Be concrete and fix-oriented: cite file:line, reference the control, show the corrected code/config.
- Conservative severity; do not dramatize. Provide remediation for every issue.
- Match the user's language (Bahasa Indonesia or English).
""",
}
