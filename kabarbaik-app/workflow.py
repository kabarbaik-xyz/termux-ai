"""KabarBaik workflow — maps each SDLC or Training stage to a team-kit skill + prompt.

Each stage's *recipe* says which ``ai --skill`` to run, what to inject from the
project's docs/ tree, and which artifact(s) to expect after it completes. The
heavy lifting (document structure, citations, QA gates) lives in the team-kit
skills themselves — the web app only orchestrates.

SDLC flow (client feedback arrives via docs/inbox/ uploads, not a stage):
  doc-ingest → discovery → BRD+PRD → UX spec+tokens (ux-design skill)
  → prototype (spec-driven, prototype skill) → proposal
  → final BRD/PRD/TSD/SAD → QA package (qa-spec skill) → task breakdown

Training flow (kbti-elearning platform; stages have unique names so a project
switching flows never collides stage_runs rows):
  training-brief → evidence-research → training-design → lesson-script
  → proposal → ux-design (Course Experience) → elearning (package + install)
  → learning-qa → rollout
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Optional

import ai_runner
import db
import settings
from settings import PROJECTS_ROOT


def refresh_artifact_state(project: dict) -> dict:
    """Infer a project's true stage (SDLC or Training) from the artifacts on
    disk. The DB stage index is a hint; the docs/ tree is the source of truth.
    Returns (stage_index, has-by-folder) — keeps the dashboard honest even if
    files are edited manually.
    """
    flow = project.get("flow", "sdlc")
    return (_refresh_training if flow == "training" else _refresh_sdlc)(project)


def _refresh_sdlc(project: dict) -> dict:
    root = db.project_dir(project)
    docs = root / "docs"
    has = {}
    for folder in ("inbox", "discovery", "brd", "prd", "ux", "prototype",
                   "proposal", "tsd", "sad", "plan", "qa", "reports"):
        has[folder] = _folder_has_files(docs / folder)

    # Advance to the furthest completed stage.
    stage = -1  # -1 = nothing on disk yet
    if has["inbox"]:
        stage = 0
    if has["discovery"]:
        stage = 1
    if has["brd"] and has["prd"]:
        stage = 2
    if (docs / "ux" / "ux-spec.md").is_file() or (docs / "03-ux-spec.md").is_file():
        stage = 3
    if has["prototype"] or _folder_has_files(root / "prototype"):
        stage = 4
    if has["proposal"]:
        stage = 5
    if has["tsd"] and has["sad"]:
        stage = 5
    if (_folder_has_files(docs / "qa")
            or _folder_has_files(docs, "08-test-cases.md")):
        stage = 6
    if has["plan"]:
        stage = 7
    return {"stage": stage, "has": has}


def _refresh_training(project: dict) -> dict:
    root = db.project_dir(project)
    docs = root / "docs"
    folders = ("inbox", "discovery", "research", "curriculum", "modules",
               "preview", "proposal", "spec", "qa", "rollout")
    has = {f: _folder_has_files(docs / "training" / f) for f in folders}

    stage = -1
    if has["discovery"]:
        stage = 0
    if has["research"]:
        stage = 1
    if has["curriculum"]:
        stage = 2
    if has["modules"] and has["preview"]:
        stage = 3
    if has["proposal"]:
        stage = 4
    if has["spec"]:
        stage = 5
    if any((root / "elearning-package").rglob("course.json")):
        stage = 6
    if has["qa"]:
        stage = 7
    if has["rollout"]:
        stage = 8
    return {"stage": stage, "has": has}


def _folder_has_files(folder: Path, marker: str = "") -> bool:
    """True if folder has any artifacts (optionally matching marker in filename)."""
    if not folder.is_dir():
        return False
    for f in folder.iterdir():
        if f.is_file() and not f.name.startswith("."):
            if not marker or marker in f.name:
                return True
    return False


def stage_recipe(stage_index: int, flow: str = "sdlc") -> tuple:
    """Return (stage, skill, tools, prompt_template) for a stage index of a flow."""
    if flow == "training":
        return _TRAINING_RECIPES.get(stage_index)
    return _SDLC_RECIPES.get(stage_index)


_SDLC_RECIPES = {
        0: (
            "doc-ingest",
            "on",
            "Normalize every raw file in docs/inbox/ into structured, citable "
            "markdown. Sources may be md/txt, pdf/docx/pptx/xlsx (read them "
            "with your file tool), *.extracted.md sidecars (pre-extracted text "
            "from rtf/eml/legacy formats — cite the ORIGINAL file name), and "
            "link-*.md / gdoc-*.md link notes (fetch the URL if public, else "
            "record it as a documented assumption). Produce "
            "docs/<phase>/<slug>.md files with SRC-<n> headers, "
            "docs/<phase>/index.md, and an Assumptions & Decisions section "
            "per source (numbered: what was assumed, the decision, rationale). "
            "Then produce docs/discovery/discovery.md (executive summary, "
            "stakeholders, current state, pain points, scope IN/OUT, "
            "ASSUMPTIONS & DECISIONS, glossary) and docs/discovery/index.md "
            "citing each SRC. Do NOT invent content; mark scans [SCAN] and "
            "gaps as documented ASSUMPTIONS — decide, never defer.\n"
            "The client speaks Indonesian or English — match their language.",
        ),
        1: (
            "discovery",
            "on",
            "Generate the INITIAL BRD and PRD. Follow the discovery skill. "
            "Input: docs/discovery/discovery.md plus the SRC files it cites "
            "(docs/<phase>/*.md). Output: docs/brd/brd.md and docs/prd/prd.md — "
            "follow the STRUCTURE of docs/brd/TEMPLATE.md and docs/prd/TEMPLATE.md "
            "exactly (same sections, same order) but with every section FILLED "
            "with real content from the sources — these are finished DOCUMENTS, "
            "not template copies; NONE of the template's placeholder text may "
            "remain. PRD: assign US-xxx IDs with acceptance criteria. BRD: "
            "business objectives BO-x. Both: header version=v1.0 sources=[SRC-n], "
            "scope OUT as binding as IN, numbered ASSUMPTIONS & DECISIONS "
            "(what was assumed, the decision, one-line rationale). Do not "
            "invent content — gaps become documented assumptions.",
        ),
        2: (
            "ux-design",
            "on",
            "Follow the ux-design skill, using the STRUCTURE of "
            "docs/ux/TEMPLATE.md exactly (same sections/order, every "
            "section filled). Inputs: the PRD at docs/prd/prd.md "
            "(required) and discovery notes at docs/discovery/discovery.md. "
            "Produce docs/ux/ux-spec.md with ALL 6 sections of the skill (scope & "
            "assumptions, Mermaid user flows, screen inventory traced to PRD "
            "requirements, per-screen wireframes with states, design tokens, "
            "assumptions & decisions) and design-tokens.json at the project root. "
            "SPEC ONLY — no code. If docs/ux/ux-spec.md already exists, lead "
            "with what changed this round.",
        ),
        3: (
            "prototype",
            "on",
            "Follow the prototype skill — build the clickable demo strictly "
            "FROM the UX Design output: docs/ux/ux-spec.md is your build "
            "spec (screen inventory, per-screen wireframes region-by-region, "
            "user flows, states) and design-tokens.json your ONLY styling "
            "source (never invent tokens). Consider ALL reference documents "
            "for content and functional detail: docs/prd/prd.md (copy, "
            "validation, business rules), docs/brd/brd.md, "
            "docs/discovery/discovery.md — where they conflict, the UX "
            "spec's structure wins and deviations are flagged in the "
            "handoff. Output to prototype/ at "
            "the project root: index.html linking every inventory screen, "
            "one file per screen, shared styles.css from token custom "
            "properties, app.js only if needed — vanilla, self-contained, "
            "no build step, no CDN, realistic content, spec'd states "
            "(empty/loading/error) reachable. Finish with the skill's "
            "self-check + prototype/README.md.",
        ),
        4: (
            "proposal",
            "on",
            "Follow the proposal skill, using the STRUCTURE of "
            "docs/proposal/TEMPLATE.md exactly (same sections/order, every "
            "section filled). From docs/prd/ (latest v), docs/prototype/ "
            "(or prototype/ at the project root), "
            "docs/discovery/ and any RFP [SRC-n], write "
            "docs/proposal/proposal-v1.md following the HOUSE FORMAT "
            "exactly: header block, executive summary + project summary "
            "table (incl. Investment IDR/~USD), background & problems, "
            "proposed solution (foundation + pillars, Mermaid diagram), "
            "scope (in/out/next-phase), plan & phases with deliverables, "
            "FULL Budget kept in separate components (Human Resources; "
            "One-Time Costs; Subscriptions by billing period — Monthly/"
            "Annual; AI operational cost only when applicable) plus Payment "
            "Terms (frequency, termin schedule sized to the work staffed per "
            "period — termins cover the HR component only — tax basis, "
            "update mechanism, payment-due window) and the *** estimate "
            "disclaimer — derive all rates and amounts per project, "
            "market-consistent, each recorded as a numbered assumption. Then "
            "architecture & technology, and an Assumptions & Decisions "
            "appendix capturing every rate, the FX basis, staffing and tax "
            "choices, then the closing. RFP compliance matrix ONLY "
            "if an RFP exists in the inputs. Budget-conformance verdict vs "
            "any stated budget in docs/discovery/. Output in the language "
            "of the source documents (PRD/prototype/discovery) — match the "
            "client's language; do not force English. "
            "If a proposal already exists (proposal-vN.md), write "
            "the next version vN+1 incorporating the client feedback uploaded to docs/inbox/ — the "
            "final agreed proposal will later be uploaded to docs/inbox/ as the "
            "source of truth for the post-approval docs.",
        ),
        5: (
            "tsd-sad",
            "on",
            "Follow the tsd-sad skill, using the STRUCTURES of "
            "docs/tsd/TEMPLATE.md and docs/sad/TEMPLATE.md exactly (same "
            "sections/order, every section filled). Produce the FINAL agreed "
            "documentation from the signed-off proposal. Source of truth: "
            "the FINAL proposal — "
            "look in docs/inbox/ first (the client-approved proposal was uploaded "
            "there — treat it as the newest [SRC-n] and cite it) and "
            "docs/proposal/proposal-vN.md (highest N). Step 1: update "
            "docs/brd/brd.md and docs/prd/prd.md to their FINAL versions — merge "
            "everything the final proposal commits to, bump the version header, "
            "add a CHANGELOG entry. Step 2: produce docs/tsd/tsd.md and "
            "docs/sad/sad.md (ADRs in docs/sad/ADR-xxx.md, one per decision) "
            "plus the doc-sync impact map. If no proposal exists anywhere, stop "
            "and say the proposal stage must be finished first.",
        ),
        6: (
            "qa-spec",
            "on",
            "Follow the qa-spec skill. Inputs (read all before writing): the "
            "final PRD at docs/prd/prd.md, the UX spec at docs/03-ux-spec.md, "
            "the UX spec at docs/ux/ux-spec.md, the prototype in prototype/ "
            "or docs/prototype/ (its README.md or "
            "handoff.md — carry anything marked unresolved into corner cases), "
            "docs/tsd/tsd.md + docs/sad/sad.md (architecture-implied failure "
            "modes), and docs/proposal/proposal-vN.md (highest N — respect "
            "scope boundaries). Produce the three linked docs per the skill: "
            "docs/qa/test-cases.md (TC-xxx grouped by screen/flow, positive "
            "AND negative side by side, PRD refs, P0/P1/P2), "
            "docs/qa/acceptance-criteria.md (Given/When/Then per Epic + "
            "checkable DoD — use the same Epic grouping Task Breakdown will "
            "use next so they line up 1:1), docs/qa/corner-cases.md (risk "
            "heat map + corner-case catalog + known deferred risk). Trace "
            "everything to a source; flag ambiguity, never guess. The AC doc's "
            "Definition of Done references docs/qa/REVIEW-CHECKLIST.md "
            "(the human review gates).",
        ),
        7: (
            "epic-breakdown",
            "on",
            "Follow the epic-breakdown skill, using the STRUCTURE of "
            "docs/plan/TEMPLATE.md exactly (same sections/order, every "
            "section filled). From the FINAL docs/prd/prd.md, "
            "docs/brd/brd.md, TSD and SAD, produce docs/plan/backlog.md with "
            "epics (E-xx), stories (US-xxx with AC, DoD, screens SC-xx, "
            "dependencies, estimate range, suggested role) and the traceability "
            "matrix PRD req → US-xx → SC-xx → component → test file. CONSUME "
            "the QA package: attach TC-xxx IDs to stories from "
            "docs/qa/test-cases.md, use the Given/When/Then AC verbatim from "
            "docs/qa/acceptance-criteria.md (same Epic grouping), and carry "
            "P0/P1 items from docs/qa/corner-cases.md into story DoD / risk "
            "notes — ready for the development phase. Every story follows "
            "the format of docs/plan/PM-TASK-TEMPLATE.md (ID, story "
            "phrasing, testable AC, screens, files hint, out-of-scope, DoD).",
        ),
}


# Stage timeout map — research/authoring stages get a longer budget. Everything
# else keeps the default 900s.
STAGE_TIMEOUT = {"research": 1800, "content": 1800, "elearning_build": 1800}


def stage_timeout(flow: str, stage_name: str) -> float:
    return STAGE_TIMEOUT.get(stage_name, 900.0)


_TRAINING_RECIPES = {
    0: (
        "training-brief",
        "on",
        "Follow the training-brief skill. Turn the training request into a "
        "Training Discovery. First ingest everything in docs/inbox/ following "
        "the doc-ingest conventions (one SRC file per source into "
        "docs/training/discovery/ + index.md, cite [SRC-n]) — only for the "
        "first run; on a re-run improve in place and say what changed. Then "
        "write docs/training/discovery/discovery.md per the skill: request at "
        "a glance, learner profile (roles, routine, background), the "
        "mindset-vs-skill gap with an explicit ratio, desired end state, "
        "constraints & non-goals, and numbered Assumptions & Decisions. "
        "Mindset-first: default toward identity shift unless the sources say "
        "otherwise. The client speaks Indonesian or English — match their "
        "language. No questions, no TBD — a pipeline runs this. Use the "
        "STRUCTURE of docs/training/discovery/TEMPLATE.md exactly.",
    ),
    1: (
        "evidence-research",
        "on",
        "Follow the evidence-research skill. **Hard cap: keep exactly 7 "
        "sources** (at most) that best match the discovery — stop researching "
        "and fetching once you have 7 solid references; log everything else as "
        "Sources rejected. Aim for category diversity (peer-reviewed + report "
        "+ case study when available). Research the web with web_search "
        "+ fetch_url, then write docs/training/research/evidence-base.md ("
        "findings grouped by research question with inline [R-n] citations, "
        "convergent/conflicting evidence, what's adapted to the trainee "
        "profile and how) and docs/training/research/references.md (one full "
        "reference row per [R-n]: title, authors/org, year, venue, type, "
        "strength, URL, DOI/ISSN, accessed date, plus a 'Sources rejected' "
        "section). NEVER invent a source. Adapt findings to the learner "
        "profile + mindset-vs-skill ratio in docs/training/discovery/discovery.md. "
        "Match the source documents' language; reference titles stay as-is.",
    ),
    2: (
        "training-design",
        "on",
        "Follow the training-design skill. Write docs/training/curriculum/"
        "curriculum.md — learning outcomes (measurable, tagged MIND/SKILL "
        "mirroring the ratio), learner-identity model, module map with "
        "content weight, session plan, assessment strategy mapped 1:1 to "
        "outcomes, success criteria (KBIs), numbered Assumptions & Decisions. "
        "Inputs: docs/training/discovery/discovery.md and "
        "docs/training/research/evidence-base.md + references.md (honor its "
        "'Into the curriculum' list). Mindset-first: protect identity-shift "
        "work; tool walkthroughs only where an outcome requires them. Use the "
        "STRUCTURE of docs/training/curriculum/TEMPLATE.md.",
    ),
    3: (
        "lesson-script",
        "on",
        "Follow the lesson-script skill. Write the training material: one "
        "folder per module under docs/training/modules/ with one markdown "
        "file per lesson (Hook → The Shift → How to BE it → Do this now → "
        "Summary & self-check with quiz questions) citing [R-n]/[SRC-n], plus "
        "the modules preview docs/training/preview/modules-preview.md (module "
        "index table, mermaid learning path, total hours + format mix, "
        "curriculum summary). Inputs: curriculum.md, evidence-base.md, "
        "discovery.md. Mindset-first. Use the STRUCTURE of "
        "docs/training/modules/TEMPLATE-LESSON.md and "
        "docs/training/preview/TEMPLATE.md.",
    ),
    4: (
        "training-proposal",
        "on",
        "Follow the training-proposal skill, using the STRUCTURE of "
        "docs/training/proposal/TEMPLATE.md exactly (same sections/order, "
        "every section filled). Write docs/training/proposal/proposal-v1.md "
        "from docs/training/preview/modules-preview.md (the module map "
        "learners will take), docs/training/curriculum/curriculum.md, and "
        "docs/training/discovery/discovery.md (learner profile, end goal, "
        "mindset-vs-skill ratio). This is a TRAINING engagement — no "
        "development fees, no infrastructure costs, no tech stack section. "
        "Include: executive summary with delivery model (live sessions at "
        "venue + self-paced homework: case study + presentation next session), "
        "training pillars mapped to modules, scope in/out (explicit: no "
        "software build), schedule with per-session homework, FULL Budget in "
        "three components — Trainer (~80%, role × sessions × rate), Training "
        "Materials (~5%), KBTI Handle Fee (~15%) — plus Payment Terms (termin "
        "schedule) and the *** estimate disclaimer. Derive all rates per "
        "engagement, each recorded as a numbered assumption, market-consistent. "
        "Numbered Assumptions & Decisions appendix. Language of the source "
        "documents. If a proposal already exists, write proposal-vN+1 "
        "incorporating feedback from docs/inbox/.",
    ),
    5: (
        "ux-design",
        "on",
        "Follow the ux-design skill in the KBTI Course Experience mode: "
        "design the course's learner-facing experience for the fixed "
        "kbti-elearning platform chrome (navy + red #a11c1c) using the KBTI "
        "brand preset in the skill — the platform palette is FIXED, never "
        "rebrand. Source of truth: the APPROVED training proposal — "
        "look in docs/inbox/ first (a signed proposal uploaded there is the "
        "newest authority) or docs/training/proposal/proposal-vN.md (highest "
        "N); cross-check docs/training/curriculum/curriculum.md and "
        "docs/training/preview/modules-preview.md. Use the STRUCTURE of "
        "docs/training/spec/TEMPLATE.md and write "
        "docs/training/spec/course-spec.md (scope & assumptions, learner "
        "journey mermaid, lesson inventory as outcome-traced table, quiz & "
        "feedback strategy, visual system, KBTI-preset design tokens, "
        "assumptions & decisions). If course-spec.md exists, lead with what "
        "changed this round. SPEC ONLY — no code.",
    ),
    6: (
        "elearning",
        "on",
        "Follow the elearning skill. Author the course package INSIDE this "
        "project only — elearning-package/<course-id>/ with course.json, "
        "lessons/<slug>.md files, cover.md — from docs/training/spec/"
        "course-spec.md (design authority), docs/training/modules/ (lesson "
        "scripts), and docs/training/qa/assessments.md if present. READ "
        "docs/training/spec/COURSE-PACKAGE-SCHEMA.md and VALIDATE course.json "
        "against it (a package that fails validation will NOT install). "
        "Course-id = project slug, unique across the platform. Never touch "
        "the kbti-elearning repo or any manifest — you AUTHOR, the app "
        "installs. Re-read and self-check your course.json before finishing.",
    ),
    7: (
        "learning-qa",
        "on",
        "Follow the learning-qa skill. QA the packaged course before release: "
        "verify every curriculum outcome has a teaching lesson AND an "
        "assessment, claims trace to docs/training/research/references.md, "
        "the package matches the schema, quizzes are correct. Fix what is "
        "safe to fix in place (mark FIXED with evidence). Output "
        "docs/training/qa/assessments.md (outcome→lesson→assessment matrix + "
        "every quiz question with verified answer) and "
        "docs/training/qa/review-checklist.md (pass/fail checklist, blockers "
        "vs warnings). Deliver the FULL matrix/checklist even when clean — "
        "the rollout gate needs the proof.",
    ),
    8: (
        "rollout",
        "on",
        "Follow the rollout skill. Write docs/training/rollout/rollout.md — "
        "go decision (QA gate status + the live course id), cohorts & "
        "schedule, facilitation needs, comms & prep, materials & platform "
        "checklist, success metrics as checkable KBIs per cohort, risk "
        "register, and the iteration loop (learner/assessment data → learning-qa "
        "re-run → package update → reinstall, with cadence). Inputs: "
        "docs/training/qa/review-checklist.md + assessments.md, "
        "docs/training/curriculum/curriculum.md, course-spec.md + "
        "elearning-package/<course-id>/. Use the STRUCTURE of "
        "docs/training/rollout/TEMPLATE.md. Decide everything — no TBD.",
    ),
}


# What each stage must leave on disk — a run that produces none of these
# is marked FAILED even if the AI exited 0 (guards against the model
# "chatting done" while its file writes were declined).
STAGE_ARTIFACTS = {
    "discovery": ["docs/discovery/discovery.md"],
    "brd_prd": ["docs/brd/brd.md", "docs/prd/prd.md"],
    "ux_design": ["docs/ux/ux-spec.md", "design-tokens.json"],
    # prototype: new skill writes prototype/ at root; legacy runs wrote docs/prototype/
    "prototype": ["prototype/", "docs/prototype/"],
    "proposal": ["docs/proposal/"],
    "post_approval": ["docs/tsd/tsd.md", "docs/sad/sad.md"],
    "qa_spec": ["docs/qa/test-cases.md", "docs/qa/acceptance-criteria.md",
                "docs/qa/corner-cases.md"],
    "task_breakdown": ["docs/plan/backlog.md"],
}


# Same contract for the Training flow's stages.
TRAINING_STAGE_ARTIFACTS = {
    "training_brief": ["docs/training/discovery/discovery.md"],
    "research": ["docs/training/research/evidence-base.md"],
    "curriculum": ["docs/training/curriculum/curriculum.md"],
    "content": ["docs/training/preview/modules-preview.md", "docs/training/modules/"],
    "training_proposal": ["docs/training/proposal/"],
    "elearning_design": ["docs/training/spec/course-spec.md"],
    "elearning_build": ["elearning-package/"],
    "training_qa": ["docs/training/qa/review-checklist.md",
                    "docs/training/qa/assessments.md"],
    "rollout": ["docs/training/rollout/rollout.md"],
}


def _stage_artifacts(flow: str, stage_name: str) -> list:
    return (TRAINING_STAGE_ARTIFACTS if flow == "training" else STAGE_ARTIFACTS).get(stage_name, [])


def _artifact_sig(root: Path, stage_name: str, flow: str = "sdlc") -> set:
    """(path, mtime, size) fingerprints of the stage's expected artifacts."""
    sig = set()
    for rel in _stage_artifacts(flow, stage_name):
        target = root / rel
        if rel.endswith("/"):                      # whole folder
            if target.is_dir():
                for f in target.rglob("*"):
                    if f.is_file():
                        sig.add((str(f), f.stat().st_mtime, f.stat().st_size))
        elif target.is_file():
            sig.add((str(target), target.stat().st_mtime, target.stat().st_size))
    return sig


def _stage_gate(stage_name: str, root: Path, flow: str = "sdlc") -> str | None:
    """Return a blocking message when a stage's inputs don't exist yet.

    SDLC: post-approval docs must derive from the FINAL proposal (signed copy
    in docs/inbox/ or generated docs/proposal/proposal-vN.md). Training: the
    Course Experience must derive from the APPROVED training proposal the same
    way — keeps each flow's order honest instead of letting the model improvise.
    """
    if flow == "training":
        return _training_gate(stage_name, root)
    return _sdlc_gate(stage_name, root)


def _sdlc_gate(stage_name: str, root: Path) -> str | None:
    docs = root / "docs"
    if stage_name == "ux_design":
        if not (docs / "prd" / "prd.md").is_file():
            return ("Blocked: no PRD yet — run 'Draft the BRD & PRD' first "
                    "(the UX spec must trace every screen to PRD requirements).")
        return None
    if stage_name == "prototype":
        if not ((docs / "ux" / "ux-spec.md").is_file()
                or (docs / "03-ux-spec.md").is_file()):
            return ("Blocked: no UX spec — run 'Design Screens & Style (UX)' first. It produces "
                    "docs/ux/ux-spec.md + design-tokens.json, which the "
                    "prototype skill requires (it will not invent a design).")
        return None
    if stage_name == "qa_spec":
        if not ((docs / "tsd" / "tsd.md").is_file()
                and (docs / "sad" / "sad.md").is_file()):
            return ("Blocked: no TSD/SAD yet — run 'Finalize Docs After "
                    "Approval' first. The QA package must sweep architecture-"
                    "implied failure modes, not just PRD requirements.")
        return None
    if stage_name != "post_approval":
        return None
    has_proposal = any((docs / "proposal").glob("proposal-v*.md"))
    if not has_proposal:
        inbox = docs / "inbox"
        has_proposal = inbox.is_dir() and any(
            "proposal" in f.name.lower() for f in inbox.iterdir()
            if f.is_file() and not f.name.startswith("."))
    if not has_proposal:
        return ("Blocked: no proposal found. Run the Proposal stage first (or "
                "upload the client-approved final proposal into docs/inbox/) — "
                "the final BRD/PRD/TSD/SAD must derive from the agreed proposal.")
    return None


def _training_gate(stage_name: str, root: Path) -> str | None:
    docs = root / "docs"
    has = _folder_has_files
    if stage_name == "research":
        if not (docs / "training" / "discovery" / "discovery.md").is_file():
            return ("Blocked: no Training Discovery — run 'Understand the "
                    "Training Request' first. The evidence base must adapt "
                    "findings to the learner profile + mindset ratio.")
        return None
    if stage_name == "curriculum":
        if not (has(docs / "training" / "research")
                and (docs / "training" / "research" / "evidence-base.md").is_file()):
            return ("Blocked: no evidence base — run 'Research the Evidence "
                    "Base' first. The curriculum must honor its adapted "
                    "findings, not improvise methods.")
        return None
    if stage_name == "content":
        if not (docs / "training" / "curriculum" / "curriculum.md").is_file():
            return ("Blocked: no curriculum — run 'Design the Curriculum' "
                    "first. Modules and lessons must trace to its outcomes.")
        return None
    if stage_name == "training_proposal":
        if not (docs / "training" / "preview" / "modules-preview.md").is_file():
            return ("Blocked: no modules preview — run 'Write the Modules & "
                    "Lessons' first. The proposal must sell the actual "
                    "module map learners will take.")
        return None
    if stage_name == "elearning_design":
        if not _has_training_proposal(docs):
            return ("Blocked: no training proposal approved. Run 'Write the "
                    "Training Proposal' first (or upload the client-approved, "
                    "SIGNED proposal into docs/inbox/) — the Course "
                    "Experience must derive from the agreed engagement.")
        return None
    if stage_name == "elearning_build":
        if not (docs / "training" / "spec" / "course-spec.md").is_file():
            return ("Blocked: no course spec — run 'Design the Course "
                    "Experience (UX)' first. The package maps lessons "
                    "straight from it.")
        return None
    if stage_name == "training_qa":
        # The package layout is elearning-package/<course-id>/course.json —
        # one level deeper than _folder_has_files looks (non-recursive), so a
        # COMPLETE package used to read as "no package". Detect course.json
        # anywhere under elearning-package/ (same contract as install_course).
        if not any((root / "elearning-package").rglob("course.json")):
            return ("Blocked: no packaged course — run 'Author & Validate the "
                    "Course Package' first. QA checks the packaged lessons "
                    "and quizzes, not just the design docs.")
        return None
    if stage_name == "rollout":
        if not (has(docs / "training" / "qa")
                and (docs / "training" / "qa" / "review-checklist.md").is_file()):
            return ("Blocked: no QA pack — run 'QA the Course (Outcome "
                    "Check)' first. Rollout releases off a clean review "
                    "checklist.")
        return None
    return None


def _has_training_proposal(docs: Path) -> bool:
    has_proposal = any((docs / "training" / "proposal").glob("proposal-v*.md"))
    if not has_proposal:
        inbox = docs / "inbox"
        has_proposal = inbox.is_dir() and any(
            "proposal" in f.name.lower() for f in inbox.iterdir()
            if f.is_file() and not f.name.startswith("."))
    return has_proposal


# Run registry: one live run per project, DECOUPLED from any browser
# connection. The runner is a background task; SSE clients attach to the
# event buffer (replay + live poll), so browser disconnects / EventSource
# auto-reconnects never kill a run or start duplicates.
_RUN_STATE: dict[int, dict] = {}   # pid -> {"events": [ev…], "done": bool, "task"}


def get_run_state(pid: int) -> dict | None:
    """Peek at the project's run state without starting anything."""
    return _RUN_STATE.get(pid)


def running_stage(pid: int) -> str | None:
    """Stage name currently running for a project (or None)."""
    st = _RUN_STATE.get(pid)
    return None if not st or st["done"] else st.get("stage")


def running_stage_index(pid: int) -> int | None:
    """Index of the currently running stage (or None) — for templates."""
    st = _RUN_STATE.get(pid)
    return None if not st or st["done"] else st.get("stage_index")


def start_stage_run(project: dict, stage_index: int,
                    timeout: Optional[float] = None) -> dict:
    """Get (or start) the live run state for a project.

    - No active run → start one as a background task, return its state.
    - Active run for the SAME stage → return it (reconnect/replay).
    - Active run for a DIFFERENT stage → return the active one with a
      note appended (the pressed stage did not start — one run at a time).
    """
    flow = project.get("flow", "sdlc")
    stages = db.get_stages(flow)
    pid = project["id"]
    st = _RUN_STATE.get(pid)
    if st and not st["done"]:
        if st.get("stage_index") != stage_index:
            st["events"].append({"type": "status",
                                 "text": f"ℹ {st.get('stage')} is currently "
                                         "running — showing its live output. "
                                         "(One stage at a time; your stage did "
                                         "not start.)"})
        return st
    # finished (or crashed) run state is replaced: the next press = a fresh
    # run. Live replay happens naturally while !done; the client reloads
    # after `done`, so nothing needs the stale buffer afterward.
    stage_name = stages[stage_index][0]
    if timeout is None:
        timeout = stage_timeout(flow, stage_name)
    st = {"events": [], "done": False, "stage": stage_name,
          "stage_index": stage_index, "task": None}

    async def _runner():
        try:
            async for ev in run_stage_stream(project, stage_index, timeout):
                st["events"].append(ev)
        except Exception as e:   # runner-level crash: still conclude the run
            st["events"].append({"type": "done", "ok": False,
                                 "message": f"run error: {e}"})
        finally:
            st["done"] = True

    import asyncio as _aio
    st["task"] = _aio.create_task(_runner())
    _RUN_STATE[pid] = st
    return st


async def run_stage_stream(project: dict, stage_index: int, timeout: float = 900.0):
    """Execute one stage (SDLC or Training), YIELDING live events for the console."""
    flow = project.get("flow", "sdlc")
    stages = db.get_stages(flow)
    recipe = stage_recipe(stage_index, flow)
    if recipe is None or recipe[0] is None:
        concluded = True
        yield {"type": "done", "ok": False,
               "message": "Stage has no automated recipe (tracked externally)."}
        return

    skill, tools, prompt_template = recipe[0], recipe[1], recipe[2]
    stage_name = stages[stage_index][0]
    pid = project["id"]

    if running_stage(pid) not in (None, stage_name):
        yield {"type": "done", "ok": False,
               "message": f"Another stage ({running_stage(pid)}) is already "
                          "running for this project."}
        return
    console: list[str] = []
    concluded = False   # did this generator record a finish (ok or failed)?
    started_run = False
    try:
        root = db.project_dir(project)
        root.mkdir(parents=True, exist_ok=True)
        _scaffold_docs(root)
        if stage_name in _stage_templates(flow):
            _seed_templates(root, stage_name, flow)

        gate = _stage_gate(stage_name, root, flow)
        if gate:
            db.start_stage(pid, stage_name)
            db.finish_stage(pid, stage_name, False, gate)
            yield {"type": "status", "text": "⛔ " + gate}
            concluded = True
            yield {"type": "done", "ok": False, "message": gate}
            return

        db.start_stage(pid, stage_name)
        started_run = True
        sig_before = _artifact_sig(root, stage_name, flow)
        usage_cp = ai_runner.max_usage_id()
        yield {"type": "status", "text": f"▶ {stage_name} started — skill: {skill}"}

        output_lines: list[str] = []
        last_err = None
        for attempt in (1, 2):   # one transparent retry: gateways 429
            try:
                async for line in ai_runner.run_stream(
                    prompt_template, project_dir=root, skill=skill,
                    tools=tools, timeout=timeout,
                ):
                    output_lines.append(line)
                    console.append(line)
                    yield {"type": "line", "text": line}
                break
            except ai_runner.AiError as e:
                last_err = e
                if attempt == 1:
                    yield {"type": "status",
                           "text": f"⚠ {e} — retrying once in 30s (rate-limit window)…"}
                    console.append(f"[retry] {e}")
                    import asyncio as _aio
                    await _aio.sleep(30)

        tok_in, tok_out = ai_runner.usage_after(usage_cp)

        def log_text():
            tail_txt = "\n".join(console[-120:])[-8000:]
            return tail_txt if tail_txt else "(no output)"

        if not output_lines:
            db.finish_stage(pid, stage_name, False, f"{last_err}\n{log_text()}",
                            tok_in, tok_out)
            concluded = True
            yield {"type": "done", "ok": False, "message": str(last_err)}
            return

        sig_after = _artifact_sig(root, stage_name, flow)
        artifacts = _stage_artifacts(flow, stage_name)
        if stage_name in artifacts and sig_after == sig_before:
            if sig_before:
                msg = ("No changes — artifacts were already present and "
                       "complete. Delete them first to force a rebuild.")
                db.finish_stage(pid, stage_name, True, msg + "\n" + log_text(),
                                tok_in, tok_out)
                concluded = True
                yield {"type": "done", "ok": True, "message": msg}
                return
            msg = ("Stage reported success but produced NO artifacts "
                   f"({', '.join(artifacts)}). The AI likely "
                   "could not write files — re-run the stage.")
            db.finish_stage(pid, stage_name, False, msg + "\n" + log_text(),
                            tok_in, tok_out)
            concluded = True
            yield {"type": "done", "ok": False, "message": msg}
            return

        unfilled = _unfilled_outputs(root, stage_name, flow)
        if unfilled:
            msg = (f"{', '.join(unfilled)} came out as an unfilled template "
                   "copy — a skill or template likely wasn't available to the "
                   "AI. Re-run the stage (skills auto-seed at app start).")
            db.finish_stage(pid, stage_name, False, msg + "\n" + log_text(),
                            tok_in, tok_out)
            concluded = True
            yield {"type": "done", "ok": False, "message": msg}
            return

        health = _render_health(root, stage_name, flow)
        db.finish_stage(pid, stage_name, True,
                        (health + "\n" + log_text()) if health else log_text(),
                        tok_in, tok_out)
        yield {"type": "status",
               "text": f"✓ artifacts verified · {health} · tokens {tok_in + tok_out:,} "
                       f"(in {tok_in:,} · out {tok_out:,})"}
        finalize = _stage_finalize(project, root, stage_name, flow)
        if finalize:
            if finalize.startswith("ERR:"):
                msg = finalize[4:]
                db.finish_stage(pid, stage_name, False, msg + "\n" + log_text(),
                                tok_in, tok_out)
                concluded = True
                yield {"type": "done", "ok": False, "message": msg}
                return
            yield {"type": "status", "text": finalize}
        refreshed = refresh_artifact_state(project)
        if refreshed["stage"] > project["stage"]:
            db.set_stage(pid, min(refreshed["stage"], len(stages) - 1))
        concluded = True
        yield {"type": "done", "ok": True, "message": "Stage completed."}
    finally:
        if started_run and not concluded:
            # generator cancelled (browser/tab closed, server stopped) — the
            # ai subprocess was terminated in run_stream's handler; never
            # leave the badge stuck on 'running'.
            try:
                db.finish_stage(pid, stage_name, False,
                                "run interrupted — connection closed or "
                                "server stopped. Re-run the stage.")
            except Exception:
                pass


async def run_stage(project: dict, stage_index: int, timeout: float = 900.0) -> str:
    """Synchronous-POST path: consume the run state, return the AI output text."""
    st = start_stage_run(project, stage_index, timeout)
    await st["task"]
    output = []
    for ev in st["events"]:
        if ev["type"] == "line":
            output.append(ev["text"])
        elif ev["type"] == "done" and not ev.get("ok", False):
            output.append(f"\n[{ev.get('message', 'failed')}]")
    return "\n".join(output)


_KIT = Path(__file__).resolve().parent.parent / "team-kit"

def _scaffold_docs(root: Path) -> None:
    """Create the team-kit docs/ folder tree if missing (both flows). ONLY
    folder creation — document templates are seeded by the stage that consumes
    them (see _seed_templates), so e.g. running Discovery never drops BRD/PRD
    files that look like an auto-triggered stage 2."""
    for folder in ("inbox", "discovery", "brd", "prd", "ux", "prototype",
                   "proposal", "tsd", "sad", "plan", "qa", "reports"):
        (root / "docs" / folder).mkdir(parents=True, exist_ok=True)
    for folder in ("discovery", "research", "curriculum", "modules",
                   "preview", "proposal", "spec", "qa", "rollout"):
        (root / "docs" / "training" / folder).mkdir(parents=True, exist_ok=True)


# kit template filename → where it lands inside a project. Managed via the
# /templates page (edits go to team-kit/templates/, seeding is non-destructive:
# a project keeps whatever it already has).
STAGE_TEMPLATES = {
    "brd_prd": [("brd.md", "docs/brd/TEMPLATE.md"),
                ("prd.md", "docs/prd/TEMPLATE.md")],
    "ux_design": [("ux-spec.md", "docs/ux/TEMPLATE.md")],
    "proposal": [("proposal.md", "docs/proposal/TEMPLATE.md")],
    "post_approval": [("tsd.md", "docs/tsd/TEMPLATE.md"),
                      ("sad.md", "docs/sad/TEMPLATE.md")],
    "qa_spec": [("review-checklist.md", "docs/qa/REVIEW-CHECKLIST.md")],
    "task_breakdown": [("backlog.md", "docs/plan/TEMPLATE.md"),
                       ("pm-task-template.md", "docs/plan/PM-TASK-TEMPLATE.md")],
}

# Same contract for the Training flow (reuses proposal.md / review-checklist.md).
TRAINING_STAGE_TEMPLATES = {
    "training_brief": [("training-brief.md", "docs/training/discovery/TEMPLATE.md")],
    "research": [("evidence-base.md", "docs/training/research/TEMPLATE.md"),
                 ("references.md", "docs/training/research/REFERENCES-TEMPLATE.md")],
    "curriculum": [("curriculum.md", "docs/training/curriculum/TEMPLATE.md")],
    "content": [("lesson-structure.md", "docs/training/modules/TEMPLATE-LESSON.md"),
                ("modules-preview.md", "docs/training/preview/TEMPLATE.md")],
    "training_proposal": [("training-proposal.md", "docs/training/proposal/TEMPLATE.md")],
    "elearning_design": [("course-spec.md", "docs/training/spec/TEMPLATE.md"),
                         ("course-package.schema.json",
                          "docs/training/spec/COURSE-PACKAGE-SCHEMA.md")],
    "training_qa": [("review-checklist.md", "docs/training/qa/REVIEW-CHECKLIST.md")],
    "rollout": [("rollout.md", "docs/training/rollout/TEMPLATE.md")],
}


def _stage_templates(flow: str) -> dict:
    return TRAINING_STAGE_TEMPLATES if flow == "training" else STAGE_TEMPLATES


def _seed_templates(root: Path, stage_name: str = "", flow: str = "sdlc") -> None:
    """Seed this stage's kit templates into the project — called right
    before the stage's run, so the recipe's 'follow the structure of
    docs/<x>/TEMPLATE.md' refers to files the model can actually read."""
    pairs = _stage_templates(flow).get(stage_name, [])
    for kit_name, dst in pairs:
        kit_src = _KIT / "templates" / kit_name
        if not kit_src.is_file():
            kit_src = _KIT / "elearning" / kit_name
        target = root / dst
        if kit_src.is_file() and not target.exists():
            target.write_text(kit_src.read_text())


def _unfilled_outputs(root: Path, stage_name: str, flow: str = "sdlc") -> list:
    """Artifact paths for the stage whose content still smells like the
    template (placeholder markers survived). proposals check their newest vN."""
    if flow == "training":
        return _unfilled_outputs_training(root, stage_name)
    checks = {
        "brd_prd": ["docs/brd/brd.md", "docs/prd/prd.md"],
        "ux_design": ["docs/ux/ux-spec.md"],
        "proposal": [],   # filled below: newest proposal-v*.md
        "post_approval": ["docs/tsd/tsd.md", "docs/sad/sad.md"],
        "task_breakdown": ["docs/plan/backlog.md"],
    }
    if stage_name == "proposal":
        versions = sorted((root / "docs" / "proposal").glob("proposal-v*.md"))
        checks["proposal"] = [f"docs/proposal/{v.name}" for v in versions[-1:]]
    return [rel for rel in checks.get(stage_name, [])
            if _looks_unfilled(root / rel)]


def _unfilled_outputs_training(root: Path, stage_name: str) -> list:
    checks = {
        "training_brief": ["docs/training/discovery/discovery.md"],
        "research": ["docs/training/research/evidence-base.md",
                     "docs/training/research/references.md"],
        "curriculum": ["docs/training/curriculum/curriculum.md"],
        "content": ["docs/training/preview/modules-preview.md"],
        "training_proposal": [],   # newest proposal-v*.md
        "elearning_design": ["docs/training/spec/course-spec.md"],
        "elearning_build": [],     # checked via package validation below
        "training_qa": ["docs/training/qa/review-checklist.md",
                        "docs/training/qa/assessments.md"],
        "rollout": ["docs/training/rollout/rollout.md"],
    }
    if stage_name == "training_proposal":
        versions = sorted((root / "docs" / "training" / "proposal").glob("proposal-v*.md"))
        checks["training_proposal"] = [f"docs/training/proposal/{v.name}"
                                       for v in versions[-1:]]
    if stage_name == "elearning_build":
        # validate the packaged course against the seeded schema — an invalid
        # package is treated the same as an unfilled template (re-run).
        return [] if _validate_packaged_root(root) == "" \
            else ["elearning-package/<course-id>/ (fails schema validation)"]
    return [rel for rel in checks.get(stage_name, [])
            if _looks_unfilled(root / rel)]


def _render_health(root: Path, stage_name: str, flow: str = "sdlc") -> str:
    """Quick render-sanity for the stage's .md artifacts: balanced code
    fences, no tabs, mermaid block count. Returns a one-line report for the
    run log (viewer renders these docs — catch format drift early)."""
    rels = _stage_artifacts(flow, stage_name)
    files = []
    for rel in rels:
        target = root / rel
        if rel.endswith("/"):
            files.extend(target.rglob("*.md"))
        elif target.suffix == ".md":
            files.append(target)
    fences_bad, tabs_bad, mermaid, n = [], [], 0, 0
    for f in files:
        try:
            text = f.read_text(errors="ignore")
        except OSError:
            continue
        n += 1
        if text.count("```") % 2 != 0:
            fences_bad.append(f.name)
        if "\t" in text:
            tabs_bad.append(f.name)
        mermaid += text.count("```mermaid")
    parts = [f"{n} docs"]
    parts.append(f"{mermaid} mermaid ✓" if mermaid else "no diagrams")
    if fences_bad:
        parts.append(f"⚠ unbalanced code fences: {', '.join(fences_bad)}")
    if tabs_bad:
        parts.append(f"⚠ tab indentation (viewer-unsafe): {', '.join(tabs_bad)}")
    if flow == "training" and stage_name == "research":
        refs_path = root / "docs" / "training" / "research" / "references.md"
        try:
            refs_text = refs_path.read_text(errors="ignore")
            ref_count = sum(1 for line in refs_text.splitlines()
                            if re.match(r"\s*\|\s*R-\d+", line))
        except OSError:
            ref_count = 0
        parts.append(f"{ref_count}/7 refs")
        if ref_count > 7:
            parts.append("⚠ ref cap exceeded")
    return " · ".join(parts)


def _looks_unfilled(path: Path) -> bool:
    """True when a 'generated' BRD/PRD is really just the template. The kit
    templates carry placeholder markers in their header/title
    (version=v__, date=__, <Client / Project>, <EN/ID…>) — a real document
    has a concrete version and title, so any surviving marker means the
    stage copied instead of generated."""
    if not path.is_file():
        return True
    lines = [l for l in path.read_text(errors="ignore").splitlines() if l.strip()]
    if not lines:
        return True
    head = "\n".join(lines[:3])
    return any(marker in head for marker in
               ("v__", "date=___", "date=__", "<Client", "<Project>",
                "<EN/ID", "<yyyy"))


# ---------------------------------------------------------------------------
# Training flow: package -> platform install
# ---------------------------------------------------------------------------

# One lock per process: two elearning_build runs must never race a manifest
# merge. The platform repo (kbti-elearning) is shared state across projects.
_INSTALL_LOCK = threading.Lock()


def _find_package(root: Path):
    """Return (course_id, pkg_dir, course) for root/elearning-package/<id>/, or None."""
    pkg_root = root / "elearning-package"
    if not pkg_root.is_dir():
        return None
    for entry in sorted(pkg_root.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        course_file = entry / "course.json"
        if not course_file.is_file():
            continue
        try:
            course = json.loads(course_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        return entry.name, entry, course
    return None


def _validate_course(course: dict, pkg_dir: Path) -> str:
    """Lightweight dependency-free course.json validation mirroring
    team-kit/elearning/course-package.schema.json. Returns '' when valid."""
    if not isinstance(course, dict):
        return "course.json is not an object"
    cid = course.get("id")
    if not isinstance(cid, str) or len(cid) < 2 or not __import__("re").match(r"^[a-z0-9][a-z0-9-]*$", cid):
        return f"course.id invalid: {cid!r} (need ≥2 chars, [a-z0-9][a-z0-9-]*)"
    for key in ("title", "language"):
        val = course.get(key)
        if not isinstance(val, str) or len(val.strip()) < 1:
            return f"course.{key} missing or empty"
    aud = course.get("audience")
    roles = aud.get("roles") if isinstance(aud, dict) else None
    if not roles or not all(isinstance(r, str) and r.strip() for r in roles):
        return "course.audience.roles must be a non-empty list of strings"
    lessons = course.get("lessons")
    if not isinstance(lessons, list) or not lessons:
        return "course.lessons must be a non-empty array"
    seen = set()
    lesson_types = {"reading", "story", "drill", "roleplay", "reflection",
                    "case", "assessment", "video", "other"}
    for i, lesson in enumerate(lessons):
        if not isinstance(lesson, dict):
            return f"lessons[{i}] is not an object"
        lid = lesson.get("id")
        if not isinstance(lid, str) or not __import__("re").match(r"^[a-z0-9-]+$", lid or ""):
            return f"lessons[{i}].id invalid: {lid!r}"
        if lid in seen:
            return f"lessons[{i}].id duplicates {lid!r}"
        seen.add(lid)
        if not isinstance(lesson.get("title"), str) or not lesson["title"].strip():
            return f"lessons[{i}].title missing"
        fname = lesson.get("file")
        if not isinstance(fname, str):
            return f"lessons[{i}].file missing"
        rel = Path(fname)
        if rel.is_absolute() or ".." in rel.parts or len(rel.parts) == 0:
            return f"lessons[{i}].file must be a relative path inside the course: {fname!r}"
        if not (pkg_dir / rel).is_file():
            return f"lessons[{i}].file not found inside package: {fname}"
        if lesson.get("type") is not None and lesson["type"] not in lesson_types:
            return f"lessons[{i}].type unknown: {lesson['type']!r}"
        if lesson.get("duration_min") is not None:
            dur = lesson["duration_min"]
            if not isinstance(dur, (int, float)) or isinstance(dur, bool) or dur < 1:
                return f"lessons[{i}].duration_min must be an integer ≥ 1"
        quiz = lesson.get("quiz")
        if quiz is not None:
            if not isinstance(quiz, dict):
                return f"lessons[{i}].quiz must be an object"
            qs = quiz.get("questions")
            if not isinstance(qs, list) or not qs:
                return f"lessons[{i}].quiz.questions must be a non-empty array"
            for j, q in enumerate(qs):
                if not isinstance(q, dict):
                    return f"lessons[{i}].quiz.questions[{j}] not an object"
                if not isinstance(q.get("q"), str) or not q["q"].strip():
                    return f"lessons[{i}].quiz.questions[{j}].q missing"
                opts = q.get("options")
                if not isinstance(opts, list) or len(opts) < 2 or not all(o for o in opts):
                    return f"lessons[{i}].quiz.questions[{j}].options needs ≥2 non-empty options"
                ans = q.get("answer")
                if not isinstance(ans, int) or isinstance(ans, bool) or not (0 <= ans < len(opts)):
                    return f"lessons[{i}].quiz.questions[{j}].answer must index options"
    return ""


def _validate_packaged_root(root: Path) -> str:
    """Validate the whole elearning-package/ tree. Returns '' when a valid
    package exists (used by _unfilled_outputs_training to gate the stage)."""
    found = _find_package(root)
    if found is None:
        return "no course package found in elearning-package/"
    _cid, pkg_dir, course = found
    return _validate_course(course, pkg_dir)


def install_course(root: Path) -> str:
    """Install the authored package into the kbti-elearning platform repo.

    Validates course.json against the kit schema contract, then copies the
    package into <ELEARNING_DIR>/courses/<course-id>/ and atomically merges its
    id into courses/manifest.json. Only writes inside the course dir + the
    manifest — other courses are never touched. Returns a one-line status, or
    raises ValueError with a human message on failure.
    """
    found = _find_package(root)
    if found is None:
        raise ValueError("No course package found in elearning-package/ "
                         "(expected <id>/course.json + lessons/).")
    course_id, pkg_dir, course = found
    err = _validate_course(course, pkg_dir)
    if err:
        raise ValueError(f"elearning-package/{course_id}/ is invalid: {err}")

    courses_dir = settings.ELEARNING_DIR / "courses"
    manifest_file = courses_dir / "manifest.json"
    target = courses_dir / course_id
    if not courses_dir.is_dir():
        raise ValueError(f"Platform not ready — no courses dir at "
                         f"{courses_dir}. Set KABARBAIK_ELEARNING_DIR to the "
                         "kbti-elearning repo (or run its scaffold).")

    with _INSTALL_LOCK:
        # Copy the package into the platform (upsert the course dir only).
        target.mkdir(parents=True, exist_ok=True)
        for f in pkg_dir.rglob("*"):
            if f.is_file():
                rel = f.relative_to(pkg_dir)
                dest = target / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                import shutil as _sh
                _sh.copy2(f, dest)

        # Atomic manifest merge: temp file + os.replace. Never reprocess other
        # entries and never touch other course folders.
        manifest = {"version": 1, "course_ids": []}
        if manifest_file.is_file():
            try:
                loaded = json.loads(manifest_file.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and isinstance(loaded.get("course_ids"), list):
                    manifest = loaded
            except Exception:
                pass
        ids = [c for c in manifest["course_ids"] if isinstance(c, str)]
        if course_id not in ids:
            ids = sorted(set(ids) | {course_id})
        manifest["course_ids"] = ids
        manifest.setdefault("version", 1)
        tmp = manifest_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        import os as _os
        _os.replace(tmp, manifest_file)

    pre = course["title"]
    return (f"📦 installed {course_id} on kbti-elearning ({pre}) — "
            f"{len(course['lessons'])} lessons · manifest has {len(ids)} courses")


def _stage_finalize(project: dict, root: Path, stage_name: str, flow: str) -> str | None:
    """Post-stage hook. Currently installs the packaged course to the platform
    after a successful elearning_build run. Returns a console status line, or
    'ERR: …' when the install failed (which fails the stage)."""
    if flow != "training" or stage_name != "elearning_build":
        return None
    try:
        return install_course(root)
    except ValueError as e:
        return f"ERR: {e}"
    except Exception as e:   # filesystem errors etc.
        return f"ERR: install failed — {e}"
