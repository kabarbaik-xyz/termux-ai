"""KabarBaik SDLC web app — FastAPI entrypoint.

Thin orchestration layer over the termux-ai `ai` binary + the team-kit SDLC
methodology. Local-only (bind 127.0.0.1) with an optional token gate.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Optional

import markdown as md_lib
from fastapi import FastAPI, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import ai_runner
import db
import settings
import workflow

settings.ensure_dirs()
db.init()

app = FastAPI(title="KabarBaik SDLC")
app.mount("/static", StaticFiles(directory=settings.PROJECT_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(settings.PROJECT_DIR / "templates"))


def _active() -> dict:
    try:
        return ai_runner.active_backend()
    except Exception:
        return {"backend": "?", "model": "", "available": False}


def _auth(request: Request):
    """Local-only: same origin + optional token gate via ?token= or cookie."""
    if not settings.TOKEN:
        return
    tok = request.query_params.get("token") or request.cookies.get("kabarbaik_token")
    if tok != settings.TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")


def _common(request: Request) -> dict:
    return {
        "request": request,
        "active": _active(),
        "stages": db.STAGES,
    }


# ----------------------------------------------------------------------------
# Pages
# ----------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    _auth(request)
    ctx = _common(request)
    ctx["clients"] = db.list_clients()
    ctx["projects"] = db.list_projects()
    return templates.TemplateResponse(request, "dashboard.html", ctx)


@app.get("/clients", response_class=HTMLResponse)
async def clients_page(request: Request):
    _auth(request)
    ctx = _common(request)
    ctx["clients"] = db.list_clients()
    return templates.TemplateResponse(request, "clients.html", ctx)


@app.post("/clients")
async def create_client(
    request: Request,
    name: str = Form(...),
    org: str = Form(""),
    contact: str = Form(""),
    notes: str = Form(""),
):
    _auth(request)
    cid = db.add_client(name, org, contact, notes)
    return RedirectResponse("/clients", status_code=303)


@app.get("/clients/{cid}", response_class=HTMLResponse)
async def client_detail(request: Request, cid: int):
    _auth(request)
    client = db.get_client(cid)
    if not client:
        raise HTTPException(404, "Client not found")
    ctx = _common(request)
    ctx["client"] = client
    ctx["projects"] = db.list_projects(cid)
    return templates.TemplateResponse(request, "client_detail.html", ctx)


@app.post("/clients/{cid}/projects")
async def create_project(
    request: Request,
    cid: int,
    name: str = Form(...),
    description: str = Form(""),
):
    _auth(request)
    project = db.add_project(cid, name, description)
    root = db.project_dir(project)
    root.mkdir(parents=True, exist_ok=True)
    for folder in ("docs/inbox", "docs/discovery", "docs/brd", "docs/prd",
                   "docs/prototype", "docs/proposal", "docs/tsd", "docs/sad",
                   "docs/plan", "docs/reports"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    return RedirectResponse(f"/clients/{cid}", status_code=303)


# ----------------------------------------------------------------------------
# Project detail / stages / docs
# ----------------------------------------------------------------------------

def _project_or_404(pid: int) -> dict:
    p = db.get_project(pid)
    if not p:
        raise HTTPException(404, "Project not found")
    return p


@app.get("/projects/{pid}", response_class=HTMLResponse)
async def project_detail(request: Request, pid: int):
    _auth(request)
    project = _project_or_404(pid)
    ctx = _common(request)
    ctx["project"] = project
    ctx["client"] = db.get_client(project["client_id"])
    ctx["artifacts"] = db.index_artifacts(pid)
    ctx["feedback"] = db.list_feedback(pid)
    ctx["stage_runs"] = _stage_runs_map(pid)
    ctx["stage_idx"] = db.STAGE_IDX
    fresh = workflow.refresh_artifact_state(project)
    ctx["fresh_stage"] = fresh["stage"]
    return templates.TemplateResponse(request, "project_detail.html", ctx)


@app.post("/projects/{pid}/stage/{stage_index}", response_class=HTMLResponse)
async def run_stage(project_request: Request, pid: int, stage_index: int):
    _auth(project_request)
    project = _project_or_404(pid)
    stage_index = min(max(stage_index, 0), len(db.STAGES) - 1)
    output = await workflow.run_stage(project, stage_index)
    ctx = _common(project_request)
    ctx["project"] = db.get_project(pid)
    ctx["output"] = output
    ctx["ran_stage"] = stage_index
    ctx["client"] = db.get_client(project["client_id"])
    ctx["artifacts"] = db.index_artifacts(pid)
    ctx["feedback"] = db.list_feedback(pid)
    ctx["stage_runs"] = _stage_runs_map(pid)
    ctx["stage_idx"] = db.STAGE_IDX
    ctx["fresh_stage"] = workflow.refresh_artifact_state(db.get_project(pid))["stage"]
    return templates.TemplateResponse(request, "project_detail.html", ctx)


@app.post("/projects/{pid}/monthly", response_class=HTMLResponse)
async def monthly(project_request: Request, pid: int):
    _auth(project_request)
    project = _project_or_404(pid)
    output = await workflow.generate_monthly_report(project)
    ctx = _common(project_request)
    ctx["project"] = db.get_project(pid)
    ctx["output"] = output
    ctx["ran_stage"] = len(db.STAGES) - 1  # monthly_report
    ctx["client"] = db.get_client(project["client_id"])
    ctx["artifacts"] = db.index_artifacts(pid)
    ctx["feedback"] = db.list_feedback(pid)
    ctx["stage_runs"] = _stage_runs_map(pid)
    ctx["stage_idx"] = db.STAGE_IDX
    ctx["fresh_stage"] = workflow.refresh_artifact_state(db.get_project(pid))["stage"]
    return templates.TemplateResponse(request, "project_detail.html", ctx)


def _all_stage_runs(pid: int) -> list:
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM stage_runs WHERE project_id=? ORDER BY started", (pid,)
        ).fetchall()
    return [dict(r) for r in rows]


def _stage_runs_map(pid: int) -> dict:
    """{stage_name: {status, log, ...}} with a default entry for EVERY stage,
    so templates never hit a missing key (Jinja raises on missing dict attrs)."""
    m = {name: {"status": "", "log": "", "started": "", "finished": "", "target": ""}
         for name, _ in db.STAGES}
    for r in _all_stage_runs(pid):
        m.setdefault(r["stage"], {"status": "", "log": ""}).update(r)
    return m


# ----------------------------------------------------------------------------
# Inbox uploads (doc-ingest feedstock) + WYSIWYG input
# ----------------------------------------------------------------------------

@app.post("/projects/{pid}/upload", response_class=HTMLResponse)
async def upload_inbox(project_request: Request, pid: int, file: UploadFile):
    _auth(project_request)
    project = _project_or_404(pid)
    root = db.project_dir(project)
    inbox = root / "docs" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    name = Path(file.filename or "unnamed").name
    ext = Path(name).suffix.lower()
    if ext not in settings.ALLOWED_UPLOAD_EXT:
        raise HTTPException(400, f"Unsupported file type: {ext}")
    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large")
    (inbox / name).write_bytes(data)
    return RedirectResponse(f"/projects/{pid}", status_code=303)


@app.post("/projects/{pid}/note", response_class=HTMLResponse)
async def add_note(
    project_request: Request,
    pid: int,
    title: str = Form(...),
    body: str = Form(...),
):
    _auth(project_request)
    project = _project_or_404(pid)
    root = db.project_dir(project)
    inbox = root / "docs" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "note").lower()).strip("-") or "note"
    path = inbox / f"{slug}-{len(list(inbox.iterdir())) + 1:02d}.md"
    path.write_text(f"<!-- SRC note: {title} -->\n\n{body}\n", encoding="utf-8")
    return RedirectResponse(f"/projects/{pid}", status_code=303)


# ----------------------------------------------------------------------------
# Docs CRUD (WYSIWYG ↔ markdown)
# ----------------------------------------------------------------------------

@app.get("/docs/read")
def doc_read(pid: int = 0, path: str = ""):
    project = _project_or_404(pid)
    safe = _safe_doc_path(project, path)
    if not safe.is_file():
        raise HTTPException(404, "Document not found")
    text = safe.read_text(encoding="utf-8")
    return JSONResponse({"name": nice_name(safe), "path": path,
                          "markdown": text, "html": md_lib.markdown(text)})


@app.post("/docs/save")
async def doc_save(request: Request, pid: int = 0, path: str = "", markdown: str = ""):
    _auth(request)
    project = _project_or_404(pid)
    safe = _safe_doc_path(project, path)
    safe.parent.mkdir(parents=True, exist_ok=True)
    safe.write_text(markdown, encoding="utf-8")
    return JSONResponse({"ok": True})


def _safe_doc_path(project: dict, rel: str) -> Path:
    root = db.project_dir(project) / "docs"
    rel = rel.replace("\\", "/").lstrip("/")
    target = (root / rel).resolve()
    if not str(target).startswith(str(root.resolve())):
        raise HTTPException(403, "Path escapes project docs")
    return target


def nice_name(p: Path) -> str:
    return p.name


# ----------------------------------------------------------------------------
# Feedback
# ----------------------------------------------------------------------------

@app.post("/projects/{pid}/feedback", response_class=HTMLResponse)
async def add_feedback(
    project_request: Request,
    pid: int,
    source: str = Form("web"),
    quote: str = Form(""),
    notes: str = Form(""),
):
    _auth(project_request)
    project = _project_or_404(pid)
    db.add_feedback(pid, source, quote, notes, "open")
    # Feed the client-feedback stage via inbox, so doc-ingest consumes it.
    root = db.project_dir(project)
    inbox = root / "docs" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    if quote.strip() or notes.strip():
        n = len(list(inbox.iterdir())) + 1
        (inbox / f"client-feedback-{n:02d}.md").write_text(
            f"<!-- SRC client feedback -->\n\n"
            f"**Quote:** {quote}\n\n**Notes:** {notes}\n",
            encoding="utf-8",
        )
    return RedirectResponse(f"/projects/{pid}", status_code=303)


# ----------------------------------------------------------------------------
# API / status
# ----------------------------------------------------------------------------

@app.get("/api/status")
async def api_status(request: Request):
    _auth(request)
    return JSONResponse({"active": _active(),
                          "token_required": bool(settings.TOKEN)})


@app.get("/healthz")
async def healthz():
    return PlainTextResponse("ok")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.HOST, port=settings.PORT)