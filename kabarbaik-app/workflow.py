"""KabarBaik SDLC workflow — maps each stage to a team-kit skill + prompt.

Each stage's *recipe* says which ``ai --skill`` to run, what to inject from the
project's docs/ tree, and which artifact(s) to expect after it completes. The
heavy lifting (document structure, citations, QA gates) lives in the team-kit
skills themselves — the web app only orchestrates.

Flow (client feedback arrives via docs/inbox/ uploads, not a stage):
  doc-ingest → discovery → BRD+PRD → UX spec+tokens (ux-design skill)
  → prototype (spec-driven, prototype skill) → proposal
  → final BRD/PRD/TSD/SAD → QA package (qa-spec skill) → task breakdown
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
    if (_folder_has_files(docs, "08-test-cases.md")
            and _folder_has_files(docs, "10-corner-cases.md")):
        stage = 6
    if has["plan"]:
        stage = 7
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
            "Follow the proposal skill, using the STRUCTURE of "
            "docs/proposal/TEMPLATE.md exactly (same sections/order, every "
            "section filled). From docs/prd/ (latest v), docs/prototype/ "
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
            "the prototype in prototype/ or docs/prototype/ (its README.md or "
            "handoff.md — carry anything marked unresolved into corner cases), "
            "docs/tsd/tsd.md + docs/sad/sad.md (architecture-implied failure "
            "modes), and docs/proposal/proposal-vN.md (highest N — respect "
            "scope boundaries). Produce the three linked docs per the skill: "
            "docs/08-test-cases.md (TC-xxx grouped by screen/flow, positive "
            "AND negative side by side, PRD refs, P0/P1/P2), "
            "docs/09-acceptance-criteria.md (Given/When/Then per Epic + "
            "checkable DoD — use the same Epic grouping Task Breakdown will "
            "use next so they line up 1:1), docs/10-corner-cases.md (risk "
            "heat map + corner-case catalog + known deferred risk). Trace "
            "everything to a source; flag ambiguity, never guess.",
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
            "docs/08-test-cases.md, use the Given/When/Then AC verbatim from "
            "docs/09-acceptance-criteria.md (same Epic grouping), and carry "
            "P0/P1 items from docs/10-corner-cases.md into story DoD / risk "
            "notes — ready for the development phase.",
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
    "qa_spec": ["docs/08-test-cases.md", "docs/09-acceptance-criteria.md",
                "docs/10-corner-cases.md"],
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
    if stage_name == "qa_spec":
        if not ((docs / "tsd" / "tsd.md").is_file()
                and (docs / "sad" / "sad.md").is_file()):
            return ("Blocked: no TSD/SAD yet — run 'Update BRD/PRD + TSD + "
                    "SAD' first. The QA package must sweep architecture-"
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


_ACTIVE_RUNS: dict[int, str] = {}   # project_id -> stage_name (one at a time)


async def run_stage_stream(project: dict, stage_index: int, timeout: float = 900.0):
    """Execute one SDLC stage, YIELDING live events for the browser console.

    Event dicts: {"type": "status"|"line"|"done", ...}
      status — human-readable stage lifecycle ("gate", "start", "retry", ...)
      line   — one line of live `ai` output (what the AI is doing right now)
      done   — final: {"ok": bool, "message": str}
    On completion the run log keeps a console tail (last 8 KB) so the UI's
    'last run' details show what happened even after a reload.
    """
    recipe = stage_recipe(stage_index)
    if recipe is None or recipe[0] is None:
        concluded = True
        yield {"type": "done", "ok": False,
               "message": "Stage has no automated recipe (tracked externally)."}
        return

    skill, tools, prompt_template = recipe[0], recipe[1], recipe[2]
    stage_name = db.STAGES[stage_index][0]
    pid = project["id"]

    if _ACTIVE_RUNS.get(pid):
        yield {"type": "done", "ok": False,
               "message": f"Another stage ({_ACTIVE_RUNS[pid]}) is already "
                          "running for this project."}
        return
    _ACTIVE_RUNS[pid] = stage_name
    console: list[str] = []
    concluded = False   # did this generator record a finish (ok or failed)?
    started_run = False
    try:
        root = db.project_dir(project)
        root.mkdir(parents=True, exist_ok=True)
        _scaffold_docs(root)
        if stage_name in STAGE_TEMPLATES:
            _seed_templates(root, stage_name)

        gate = _stage_gate(stage_name, root)
        if gate:
            db.start_stage(pid, stage_name)
            db.finish_stage(pid, stage_name, False, gate)
            yield {"type": "status", "text": "⛔ " + gate}
            concluded = True
            yield {"type": "done", "ok": False, "message": gate}
            return

        db.start_stage(pid, stage_name)
        started_run = True
        sig_before = _artifact_sig(root, stage_name)
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

        sig_after = _artifact_sig(root, stage_name)
        if stage_name in STAGE_ARTIFACTS and sig_after == sig_before:
            if sig_before:
                msg = ("No changes — artifacts were already present and "
                       "complete. Delete them first to force a rebuild.")
                db.finish_stage(pid, stage_name, True, msg + "\n" + log_text(),
                                tok_in, tok_out)
                concluded = True
                yield {"type": "done", "ok": True, "message": msg}
                return
            msg = ("Stage reported success but produced NO artifacts "
                   f"({', '.join(STAGE_ARTIFACTS[stage_name])}). The AI likely "
                   "could not write files — re-run the stage.")
            db.finish_stage(pid, stage_name, False, msg + "\n" + log_text(),
                            tok_in, tok_out)
            concluded = True
            yield {"type": "done", "ok": False, "message": msg}
            return

        unfilled = _unfilled_outputs(root, stage_name)
        if unfilled:
            msg = (f"{', '.join(unfilled)} came out as an unfilled template "
                   "copy — a skill or template likely wasn't available to the "
                   "AI. Re-run the stage (skills auto-seed at app start).")
            db.finish_stage(pid, stage_name, False, msg + "\n" + log_text(),
                            tok_in, tok_out)
            concluded = True
            yield {"type": "done", "ok": False, "message": msg}
            return

        db.finish_stage(pid, stage_name, True, log_text(), tok_in, tok_out)
        yield {"type": "status",
               "text": f"✓ artifacts verified · tokens {tok_in + tok_out:,} "
                       f"(in {tok_in:,} · out {tok_out:,})"}
        refreshed = refresh_artifact_state(project)
        if refreshed["stage"] > project["stage"]:
            db.set_stage(pid, min(refreshed["stage"], len(db.STAGES) - 1))
        concluded = True
        yield {"type": "done", "ok": True, "message": "Stage completed."}
    finally:
        _ACTIVE_RUNS.pop(pid, None)
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
    """Synchronous-POST path: consume the stream, return the AI output text."""
    output = []
    async for ev in run_stage_stream(project, stage_index, timeout):
        if ev["type"] == "line":
            output.append(ev["text"])
        elif ev["type"] == "done" and not ev.get("ok", False):
            # surface failures as text (POST page shows it in the output panel)
            output.append(f"\n[{ev.get('message', 'failed')}]")
    return "\n".join(output)


_KIT = Path(__file__).resolve().parent.parent / "team-kit"

def _scaffold_docs(root: Path) -> None:
    """Create the team-kit docs/ folder tree if missing. ONLY folder creation —
    document templates are seeded by the stage that consumes them (see
    _seed_templates), so e.g. running Discovery never drops BRD/PRD files
    that look like an auto-triggered stage 2."""
    for folder in ("inbox", "discovery", "brd", "prd", "prototype",
                   "proposal", "tsd", "sad", "plan", "reports"):
        (root / "docs" / folder).mkdir(parents=True, exist_ok=True)


# kit template filename → where it lands inside a project. Managed via the
# /templates page (edits go to team-kit/templates/, seeding is non-destructive:
# a project keeps whatever it already has).
STAGE_TEMPLATES = {
    "brd_prd": [("brd.md", "docs/brd/TEMPLATE.md"),
                ("prd.md", "docs/prd/TEMPLATE.md")],
    "proposal": [("proposal.md", "docs/proposal/TEMPLATE.md")],
    "post_approval": [("tsd.md", "docs/tsd/TEMPLATE.md"),
                      ("sad.md", "docs/sad/TEMPLATE.md")],
    "task_breakdown": [("backlog.md", "docs/plan/TEMPLATE.md")],
}


def _seed_templates(root: Path, stage_name: str = "") -> None:
    """Seed this stage's kit templates into the project — called right
    before the stage's run, so the recipe's 'follow the structure of
    docs/<x>/TEMPLATE.md' refers to files the model can actually read."""
    pairs = STAGE_TEMPLATES.get(stage_name, [])
    for kit_name, dst in pairs:
        kit_src = _KIT / "templates" / kit_name
        target = root / dst
        if kit_src.is_file() and not target.exists():
            target.write_text(kit_src.read_text())


def _unfilled_outputs(root: Path, stage_name: str) -> list:
    """Artifact paths for the stage whose content still smells like the
    template (placeholder markers survived). proposal checks its newest vN."""
    checks = {
        "brd_prd": ["docs/brd/brd.md", "docs/prd/prd.md"],
        "proposal": [],   # filled below: newest proposal-v*.md
        "post_approval": ["docs/tsd/tsd.md", "docs/sad/sad.md"],
        "task_breakdown": ["docs/plan/backlog.md"],
    }
    if stage_name == "proposal":
        versions = sorted((root / "docs" / "proposal").glob("proposal-v*.md"))
        checks["proposal"] = [f"docs/proposal/{v.name}" for v in versions[-1:]]
    return [rel for rel in checks.get(stage_name, [])
            if _looks_unfilled(root / rel)]


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
