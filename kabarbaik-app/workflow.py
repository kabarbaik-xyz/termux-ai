"""KabarBaik SDLC workflow — maps each stage to a team-kit skill + prompt.

Each stage's *recipe* says which ``ai --skill`` to run, what to inject from the
project's docs/ tree, and which artifact(s) to expect after it completes. The
heavy lifting (document structure, citations, QA gates) lives in the team-kit
skills themselves — the web app only orchestrates.

Flow (client feedback arrives via docs/inbox/ uploads, not a stage):
  doc-ingest → discovery → BRD+PRD → UX spec+tokens (ux-design skill)
  → prototype (spec-driven, prototype skill) → proposal
  → final BRD/PRD/TSD/SAD → task breakdown
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import ai_runner
import db
from settings import PROJECTS_ROOT


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
    stage = -1  # -1 = nothing on disk yet
    if has["inbox"]:
        stage = 0
    if has["discovery"]:
        stage = 1
    if has["brd"] and has["prd"]:
        stage = 2
    if (docs / "03-ux-spec.md").is_file():
        stage = 3
    if has["prototype"] or _folder_has_files(root / "prototype"):
        stage = 4
    if has["proposal"]:
        stage = 5
    if has["tsd"] and has["sad"]:
        stage = 5
    if has["plan"]:
        stage = 6
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
            "markdown. Sources may be md/txt, pdf/docx/pptx/xlsx (read them "
            "with your file tool), *.extracted.md sidecars (pre-extracted text "
            "from rtf/eml/legacy formats — cite the ORIGINAL file name), and "
            "link-*.md / gdoc-*.md link notes (fetch the URL if public, else "
            "flag as an open question). Produce docs/<phase>/<slug>.md files with SRC-<n> headers, "
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
            "Generate the INITIAL BRD and PRD. Follow the discovery skill. "
            "Input: docs/discovery/discovery.md plus the SRC files it cites "
            "(docs/<phase>/*.md). Output: docs/brd/brd.md and docs/prd/prd.md — "
            "follow the STRUCTURE of docs/brd/TEMPLATE.md and docs/prd/TEMPLATE.md "
            "exactly (same sections, same order) but with every section FILLED "
            "with real content from the sources — these are finished DOCUMENTS, "
            "not template copies; NONE of the template's placeholder text may "
            "remain. PRD: assign US-xxx IDs with acceptance criteria. BRD: "
            "business objectives BO-x. Both: header version=v1.0 sources=[SRC-n], "
            "scope OUT as binding as IN, numbered OPEN QUESTIONS for the next "
            "client meeting. Do not invent content — gaps become open questions.",
        ),
        2: (
            "ux-design",
            "on",
            "Follow the ux-design skill. Inputs: the PRD at docs/prd/prd.md "
            "(this project's equivalent of docs/02-PRD.md — required) and "
            "discovery notes at docs/discovery/discovery.md. Produce "
            "docs/03-ux-spec.md with ALL 6 sections of the skill (scope & "
            "assumptions, Mermaid user flows, screen inventory traced to PRD "
            "requirements, per-screen wireframes with states, design tokens, "
            "client open questions) and design-tokens.json at the project root. "
            "SPEC ONLY — no code. If docs/03-ux-spec.md already exists, lead "
            "with what changed this round.",
        ),
        3: (
            "prototype",
            "on",
            "Follow the prototype skill — build the clickable demo FROM the "
            "spec: docs/03-ux-spec.md is your build spec and "
            "design-tokens.json your only styling source (never invent "
            "tokens). Functional detail the spec references but doesn't "
            "spell out comes from docs/prd/prd.md. Output to prototype/ at "
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
            "Follow the proposal skill. From docs/prd/ (latest v), docs/prototype/ "
            "(or prototype/ at the project root), "
            "docs/discovery/ and any RFP [SRC-n], write "
            "docs/proposal/proposal-v1.md with the skill's full structure "
            "(executive summary, understanding, solution overview with Mermaid, "
            "RFP compliance matrix, scope, delivery phases, team & allocation, "
            "risks, why-us). Keep pricing as a [PRICING — HUMAN OWNED] "
            "placeholder. If a proposal already exists (proposal-vN.md), write "
            "the next version vN+1 incorporating the client feedback uploaded to docs/inbox/ — the "
            "final agreed proposal will later be uploaded to docs/inbox/ as the "
            "source of truth for the post-approval docs.",
        ),
        5: (
            "tsd-sad",
            "on",
            "Follow the tsd-sad skill and produce the FINAL agreed documentation "
            "from the signed-off proposal. Source of truth: the FINAL proposal — "
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
            "epic-breakdown",
            "on",
            "Follow the epic-breakdown skill. From the FINAL docs/prd/prd.md, "
            "docs/brd/brd.md, TSD and SAD, produce docs/plan/backlog.md with "
            "epics (E-xx), stories (US-xxx with AC, DoD, screens SC-xx, "
            "dependencies, estimate range, suggested role) and the traceability "
            "matrix PRD req → US-xx → SC-xx → component → test file — ready for "
            "the development phase.",
        ),
    }
    return recipes.get(stage_index)


# What each stage must leave on disk — a run that produces none of these
# is marked FAILED even if the AI exited 0 (guards against the model
# "chatting done" while its file writes were declined).
STAGE_ARTIFACTS = {
    "discovery": ["docs/discovery/discovery.md"],
    "brd_prd": ["docs/brd/brd.md", "docs/prd/prd.md"],
    "ux_design": ["docs/03-ux-spec.md", "design-tokens.json"],
    # prototype: new skill writes prototype/ at root; legacy runs wrote docs/prototype/
    "prototype": ["prototype/", "docs/prototype/"],
    "proposal": ["docs/proposal/"],
    "post_approval": ["docs/tsd/tsd.md", "docs/sad/sad.md"],
    "task_breakdown": ["docs/plan/backlog.md"],
}


def _artifact_sig(root: Path, stage_name: str) -> set:
    """(path, mtime, size) fingerprints of the stage's expected artifacts."""
    sig = set()
    for rel in STAGE_ARTIFACTS.get(stage_name, []):
        target = root / rel
        if rel.endswith("/"):                      # whole folder
            if target.is_dir():
                for f in target.rglob("*"):
                    if f.is_file():
                        sig.add((str(f), f.stat().st_mtime, f.stat().st_size))
        elif target.is_file():
            sig.add((str(target), target.stat().st_mtime, target.stat().st_size))
    return sig


def _stage_gate(stage_name: str, root: Path) -> str | None:
    """Return a blocking message when a stage's inputs don't exist yet.

    Post-approval docs must derive from the FINAL proposal: either an
    uploaded/signed proposal in docs/inbox/ or a generated
    docs/proposal/proposal-vN.md. Keeps the SDLC order honest instead of
    letting the model improvise TSD/SAD from the PRD alone.
    """
    docs = root / "docs"
    if stage_name == "ux_design":
        if not (docs / "prd" / "prd.md").is_file():
            return ("Blocked: no PRD yet — run 'Initial BRD + PRD' first "
                    "(the UX spec must trace every screen to PRD requirements).")
        return None
    if stage_name == "prototype":
        if not (docs / "03-ux-spec.md").is_file():
            return ("Blocked: no UX spec — run 'UX Design' first. It produces "
                    "docs/03-ux-spec.md + design-tokens.json, which the "
                    "prototype skill requires (it will not invent a design).")
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


async def run_stage(project: dict, stage_index: int, timeout: float = 900.0) -> str:
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

    # Hard preconditions — prompt-level guards are advisory; enforce in code.
    gate = _stage_gate(stage_name, root)
    if gate:
        db.start_stage(project["id"], stage_name)
        db.finish_stage(project["id"], stage_name, False, gate)
        return gate

    db.start_stage(project["id"], stage_name)
    sig_before = _artifact_sig(root, stage_name)
    output = None
    last_err = None
    for attempt in (1, 2):   # one transparent retry: free-tier gateways 429
        try:
            output = await ai_runner.run(
                prompt_template,
                project_dir=root,
                skill=skill,
                tools=tools,
                timeout=timeout,
            )
            break
        except ai_runner.AiError as e:
            last_err = e
            if attempt == 1:
                import asyncio as _aio
                await _aio.sleep(30)   # let the rate-limit window pass
    if output is None:
        db.finish_stage(project["id"], stage_name, False, str(last_err))
        raise last_err
    # The run "succeeded" only if it produced or updated its artifacts.
    sig_after = _artifact_sig(root, stage_name)
    if stage_name in STAGE_ARTIFACTS and sig_after == sig_before:
        if sig_before:
            # Artifacts already existed and the model changed nothing — a
            # legitimate "already complete" re-run, not a phantom.
            db.finish_stage(project["id"], stage_name, True,
                            "No changes — artifacts were already present and "
                            "complete. Delete them first to force a rebuild.")
        else:
            msg = ("Stage reported success but produced NO artifacts "
                   f"({', '.join(STAGE_ARTIFACTS[stage_name])}). The AI likely "
                   "could not write files — re-run the stage.")
            db.finish_stage(project["id"], stage_name, False, msg)
            return msg
    else:
        db.finish_stage(project["id"], stage_name, True)
    # The project advances to the next stage once artifacts exist.
    refreshed = refresh_artifact_state(project)
    if refreshed["stage"] > project["stage"]:
        db.set_stage(project["id"], min(refreshed["stage"], len(db.STAGES) - 1))
    return output


_KIT = Path(__file__).resolve().parent.parent / "team-kit"

def _scaffold_docs(root: Path) -> None:
    """Create the team-kit docs/ folder tree if missing, seeding BRD/PRD
    templates from the kit so stage recipes reference files that exist in
    the PROJECT (the model can't see the kit from the project dir)."""
    for folder in ("inbox", "discovery", "brd", "prd", "prototype",
                   "proposal", "tsd", "sad", "plan", "reports"):
        (root / "docs" / folder).mkdir(parents=True, exist_ok=True)
    seeds = {"docs/brd/TEMPLATE.md": "templates/brd.md",
             "docs/prd/TEMPLATE.md": "templates/prd.md"}
    for dst, src in seeds.items():
        kit_src = _KIT / src
        target = root / dst
        if kit_src.is_file() and not target.exists():
            target.write_text(kit_src.read_text())
