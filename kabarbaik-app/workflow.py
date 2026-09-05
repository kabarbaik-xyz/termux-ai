"""KabarBaik SDLC workflow — maps each stage to a team-kit skill + prompt.

Each stage's *recipe* says which ``ai --skill`` to run, what to inject from the
project's docs/ tree, and which artifact(s) to expect after it completes. The
heavy lifting (document structure, citations, QA gates) lives in the team-kit
skills themselves — the web app only orchestrates.

Flow (matches team-kit samples 00→10):
  doc-ingest → discovery → BRD+PRD → webapp(prototype) → client-feedback
  → proposal → tsd-sad → epic-breakdown → development → monthly report
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import ai_runner
import db


def refresh_artifact_state(project: dict) -> dict:
    """Infer a project's true SDLC stage from the artifacts on disk.

    The DB stage index is a hint; the docs/ tree is the source of truth. This
    walks the docs folders and returns (stage_index, status) — used to keep the
    dashboard honest even if files are edited manually.
    """
    root = db.project_dir(project)
    docs = root / "docs"
    has = {}
    for folder in ("inbox", "discovery", "brd", "prd", "prototype",
                   "proposal", "tsd", "sad", "plan", "reports"):
        has[folder] = _folder_has_files(docs / folder)

    # Advance to the furthest completed stage.
    if has["inbox"]:
        stage = 0
    if has["discovery"]:
        stage = 1
    if has["brd"] and has["prd"]:
        stage = 2
    if has["prototype"]:
        stage = 3
    if (has["prd"]) and _folder_has_files(docs / "prd", "change-requests"):
        stage = 4
    if has["proposal"]:
        stage = 5
    if has["tsd"] and has["sad"]:
        stage = 6
    if has["plan"]:
        stage = 7
    if has["reports"]:
        stage = 9
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


def stage_recipe(stage_index: int) -> tuple:
    """Return (stage, skill, tools, prompt_template) for a stage index."""
    recipes = {
        0: (
            "doc-ingest",
            "on",
            "Normalize every raw file in docs/inbox/ into structured, citable "
            "markdown. Produce docs/<phase>/<slug>.md files with SRC-<n> headers, "
            "docs/<phase>/index.md, and an Open Questions section per source. "
            "Then produce docs/discovery/discovery.md (executive summary, "
            "stakeholders, current state, pain points, scope IN/OUT, assumptions, "
            "OPEN QUESTIONS, glossary) and docs/discovery/index.md citing each SRC. "
            "Do NOT invent content; mark scans [SCAN] and gaps as open questions.\n"
            "The client speaks Indonesian or English — match their language.",
        ),
        1: (
            "discovery",
            "on",
            "Follow the discovery skill. From the sources already in docs/inbox/ "
            "and docs/discovery/, produce docs/discovery/discovery.md if missing, "
            "then write docs/brd/brd.md and docs/prd/prd.md using the BRD and PRD "
            "templates in the team-kit (docs/brd/ and docs/prd/ folders). Every "
            "claim cites [SRC-n]; scope OUT is as binding as IN; number OPEN "
            "QUESTIONS that drive the next client meeting.",
        ),
        2: (
            "webapp",
            "on",
            "Follow the webapp skill in PROTOTYPE mode. Read docs/prd/ (latest) "
            "and the UX Spec, then build a clickable prototype in docs/prototype/ "
            "(or a prototype/ subfolder) using the house stack. Record the preview "
            "URL in docs/prototype/ and a handoff note: what's fake, what's real, "
            "known gaps. Mobile-responsive from the start.",
        ),
        3: (
            "client-feedback",
            "on",
            "Follow the client-feedback skill. Convert the client meeting notes in "
            "docs/inbox/ and the demo reactions into structured change requests "
            "(CR-xxx) with impact analysis in docs/prd/change-requests.md, a PRD "
            "redline appendix, and update docs/prd/CHANGELOG.md.",
        ),
        4: (
            "proposal",
            "on",
            "Follow the proposal skill. From docs/prd/ (v2+), docs/prototype/, "
            "docs/discovery/ and any RFP [SRC-n], write docs/proposal/proposal-v1.md "
            "with the full structure (executive summary, understanding, solution "
            "overview with Mermaid, RFP compliance matrix, scope, delivery phases, "
            "team & allocation, risks, why-us). Keep pricing as a "
            "[PRICING — HUMAN OWNED] placeholder.",
        ),
        5: (
            "tsd-sad",
            "on",
            "Follow the tsd-sad skill. From the agreed proposal, PRD v2 and "
            "prototype, produce docs/tsd/tsd.md and docs/sad/sad.md (with ADRs in "
            "docs/sad/ADR-xxx.md, one per decision) plus the doc-sync impact map.",
        ),
        6: (
            "epic-breakdown",
            "on",
            "Follow the epic-breakdown skill. From PRD v2, TSD and SAD, produce "
            "docs/plan/backlog.md with epics (E-xx), stories (US-xxx with AC, DoD, "
            "screens SC-xx, dependencies, estimate range, suggested role) and the "
            "traceability matrix PRD req → US-xx → SC-xx → component → test file.",
        ),
        7: (
            None,
            "on",
            "Development is tracked here. Use the docs/plan/backlog.md stories as "
            "the source of truth for ongoing work; wire this stage to the team's "
            "PM/CI later.",
        ),
        8: (
            "deploy-checklist",
            "on",
            "Produce the monthly report for the client: docs/reports/monthly-<yyyy-mm>.md "
            "summarizing work delivered (stories done from docs/plan/backlog.md), "
            "demoable results, risks, and next-month plan. Cite US-xx IDs. Match the "
            "client's language.",
        ),
    }
    return recipes.get(stage_index)


SCHEDULE_PROMPT = """You are the KabarBaik delivery lead. Client: {client} · Project: {project}.

Plan the full build out of the agreed docs (PRD v2, TSD, SAD, backlog). Produce a
monthly schedule (month-by-month, {months} months) mapping epics/stories from
docs/plan/backlog.md onto sprints/months, marking dependencies, and the demoable
milestone that ends each month. Write it as docs/reports/schedule.md."""


async def run_stage(project: dict, stage_index: int) -> str:
    """Execute one SDLC stage for a project; returns the full AI output.

    Creates the docs/ scaffold if missing, records the stage run, streams the
    `ai` output into the run log, and flips the project's stage on success.
    """
    recipe = stage_recipe(stage_index)
    if recipe is None or recipe[0] is None:
        return f"Stage {stage_index} has no automated recipe (development is tracked externally)."

    skill, tools, prompt_template = recipe[0], recipe[1], recipe[2]
    stage_name = db.STAGES[stage_index][0]
    root = db.project_dir(project)
    root.mkdir(parents=True, exist_ok=True)
    _scaffold_docs(root)

    # Assemble the context prompt from the project's identity.
    prompt = prompt_template

    db.start_stage(project["id"], stage_name)
    buf: list[str] = []
    try:
        async for line in ai_runner.run(
            prompt,
            project_dir=root,
            skill=skill,
            tools=tools,
        ):
            buf.append(line)
    except ai_runner.AiError as e:
        db.finish_stage(project["id"], stage_name, False, str(e))
        raise
    db.finish_stage(project["id"], stage_name, True)
    # The project advances to the next stage once artifacts exist.
    refreshed = refresh_artifact_state(project)
    if refreshed["stage"] > project["stage"]:
        db.set_stage(project["id"], min(refreshed["stage"], len(db.STAGES) - 1))
    return "\n".join(buf)


def _scaffold_docs(root: Path) -> None:
    """Create the team-kit docs/ folder tree if missing."""
    for folder in ("inbox", "discovery", "brd", "prd", "prototype",
                   "proposal", "tsd", "sad", "plan", "reports"):
        (root / "docs" / folder).mkdir(parents=True, exist_ok=True)


async def generate_monthly_report(project: dict) -> str:
    """Generate the current month's client report into docs/reports/."""
    from datetime import date

    stamp = date.today().isoformat()[:7]
    root = db.project_dir(project)
    _scaffold_docs(root)
    prompt = (
        "Produce the monthly report for the client: docs/reports/"
        f"monthly-{stamp}.md summarizing work delivered (stories done from "
        "docs/plan/backlog.md), demoable results, risks, next-month plan. "
        "Cite US-xx IDs. Match the client's language."
    )
    buf: list[str] = []
    async for line in ai_runner.run(
        prompt, project_dir=root, skill="deploy-checklist", tools="on"
    ):
        buf.append(line)
    db.start_stage(project["id"], "monthly_report", target=f"monthly-{stamp}.md")
    db.finish_stage(project["id"], "monthly_report", True)
    return "\n".join(buf)


def build_schedule_prompt(client: str, project: str, months: int) -> str:
    """Return the delivery-schedule prompt from the SCHEDULE_PROMPT template."""
    return SCHEDULE_PROMPT.format(client=client, project=project, months=months)