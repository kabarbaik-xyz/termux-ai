"""KabarBaik SDLC web app — FastAPI entrypoint.

Thin orchestration layer over the termux-ai `ai` binary + the team-kit SDLC
methodology. Local-only (bind 127.0.0.1) with an optional token gate.

Auto-detects .venv on startup so the correct (pydantic-v2) Python is always
used, even when invoked via ``python3 main.py`` from the system interpreter.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

def _ensure_venv() -> None:
    """Re-exec via .venv/bin/python if needed; no-op when already in venv."""
    if getattr(sys, "real_prefix", None) or sys.prefix != sys.base_prefix:
        return
    venv_python = Path(__file__).resolve().parent / ".venv" / "bin" / "python"
    if venv_python.is_file():
        os.execv(str(venv_python), [str(venv_python)] + sys.argv)

_ensure_venv()

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
    return templates.TemplateResponse(project_request, "project_detail.html", ctx)


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
    return templates.TemplateResponse(project_request, "project_detail.html", ctx)


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

def _ingest_sidecar(path: Path) -> Path | None:
    """Write ``<name>.extracted.md`` next to formats the AI can't read raw.

    - .rtf/.eml/.url: plain-text-ish → parse/strip in python (no deps).
    - .doc/.ppt/.xls/.odt: try any installed converter (soffice/pandoc/
      antiword/catdoc); if none, write a stub so doc-ingest still sees the
      source exists and can ask the client for a docx/pdf export.
    Native AI formats (md/txt/csv/json/html/pdf/docx/pptx/xlsx) need nothing.
    """
    ext = path.suffix.lower()
    if ext in settings.NATIVE_AI_EXTS:
        return None
    out = path.with_suffix(path.suffix + ".extracted.md")
    try:
        if ext == ".eml":
            from email import policy
            from email.parser import BytesParser
            msg = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
            parts = [f"From: {msg.get('From','')}  To: {msg.get('To','')}  "
                     f"Subject: {msg.get('Subject','')}  Date: {msg.get('Date','')}"]
            body = msg.get_body(preferencelist=("plain", "html"))
            if body:
                parts.append(body.get_content() if not body.get_content_maintype()
                             == "multipart" else str(body))
            text = "\n\n".join(parts)
        elif ext == ".rtf":
            import re as _re
            raw = path.read_text(errors="ignore")
            text = _re.sub(r"\\'([0-9a-f]{2})", lambda m: chr(int(m.group(1), 16)), raw)
            text = text.replace("\\par", "\n")
            text = _re.sub(r"\\[a-z]+-?\d* ?|[{}]", "", text)
        elif ext == ".url":
            text = path.read_text(errors="ignore")
        else:  # legacy office / odf
            text = ""
            if shutil.which("soffice"):
                r = subprocess.run(["soffice", "--headless", "--convert-to", "txt",
                                    "--outdir", path.parent, str(path)],
                                   capture_output=True, timeout=120)
                txt = path.with_suffix(".txt")
                if r.returncode == 0 and txt.exists():
                    text = txt.read_text(errors="ignore")
                    txt.unlink(missing_ok=True)
            for tool, cmd in (("antiword", ["antiword", str(path)]),
                              ("catdoc", ["catdoc", str(path)])):
                if not text and shutil.which(tool):
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                    if r.returncode == 0:
                        text = r.stdout
            if not text:
                text = (f"[BINARY SOURCE — not machine-readable on this device]\n"
                        f"File: {path.name}\n"
                        f"Format: {ext}\n"
                        f"Ask the client to export it as .docx or .pdf and "
                        f"re-upload; the original is kept in docs/inbox/.")
        out.write_text(f"<!-- extracted from {path.name} -->\n{text}\n")
        return out
    except Exception as e:
        out.unlink(missing_ok=True)
        return None


def _slugify(text: str) -> str:
    import re as _re
    return _re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "source"


_GDOC_PATTERNS = (
    ("document", "docs.google.com/document/d/", "docx"),
    ("spreadsheet", "docs.google.com/spreadsheets/d/", "xlsx"),
    ("presentation", "docs.google.com/presentation/d/", "pptx"),
    ("drive", "drive.google.com/file/d/", None),
)


def _gdoc_target(url: str) -> tuple[str, str] | None:
    """(download_url, ext) for a Google Docs/Sheets/Slides/Drive link."""
    for kind, marker, ext in _GDOC_PATTERNS:
        if marker in url:
            doc_id = url.split(marker, 1)[1].split("/")[0].split("?")[0]
            if not doc_id:
                return None
            if kind == "drive":
                return (f"https://drive.google.com/uc?export=download&id={doc_id}", "")
            return (f"https://docs.google.com/{'spreadsheets' if kind=='spreadsheet' else kind}"
                    f"/d/{doc_id}/export?format={ext}", ext)
    return None


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
    _ingest_sidecar(inbox / name)
    return RedirectResponse(f"/projects/{pid}", status_code=303)


@app.post("/projects/{pid}/link", response_class=HTMLResponse)
async def ingest_link(project_request: Request, pid: int, url: str = Form(...)):
    """Ingest a pasted link — Google Docs/Sheets/Slides/Drive get exported
    to their office equivalent; anything else becomes a link-source note."""
    _auth(project_request)
    project = _project_or_404(pid)
    inbox = db.project_dir(project) / "docs" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(400, "Paste a full http(s) URL")

    target = _gdoc_target(url)
    if not target:
        slug = _slugify(url.split("//", 1)[-1])
        note = inbox / f"link-{slug}.md"
        note.write_text(f"<!-- link source -->\nSource URL: {url}\n\n"
                        f"[LINK SOURCE]\nFetch/read this URL during doc-ingest "
                        f"(ask the delivery lead if it needs credentials).\n")
        return RedirectResponse(f"/projects/{pid}", status_code=303)

    dl, ext = target
    slug = _slugify(url.split("/d/", 1)[-1][:40] or "gdoc")
    name = inbox / f"gdoc-{slug}{ext}"
    if not shutil.which("curl"):
        (inbox / f"gdoc-{slug}.link.md").write_text(
            f"<!-- link source -->\nSource URL: {url}\n\n[MISSING TOOL: curl] "
            f"Install curl (see requirements.txt) to auto-export Google Docs, "
            f"or export manually and upload the {ext or 'docx'}.\n")
        return RedirectResponse(f"/projects/{pid}", status_code=303)
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        r = subprocess.run(["curl", "-fsSL", "--max-time", "90", "-o", tmp.name, dl],
                           capture_output=True, timeout=120)
        ok = r.returncode == 0 and _looks_like_file(tmp.name, ext)
        if ok:
            name.write_bytes(Path(tmp.name).read_bytes())
        import os as _os
        _os.unlink(tmp.name)
    if not ok:
        # Private doc: keep the link so a human can export it manually.
        (inbox / f"gdoc-{slug}.link.md").write_text(
            f"<!-- link source -->\nSource URL: {url}\n\n[PRIVATE GOOGLE DOC — "
            f"export manually]\nThis document is not link-shared. Open the URL, "
            f"export as {ext or 'docx'} and upload it.\n")
    return RedirectResponse(f"/projects/{pid}", status_code=303)


def _looks_like_file(path: str, ext: str) -> bool:
    """Cheap magic sniff: docx/xlsx/pptx are zip (PK), pdf is %PDF; for
    anything else reject obvious HTML error pages."""
    head = Path(path).read_bytes()[:5]
    if ext in ("docx", "xlsx", "pptx"):
        return head[:2] == b"PK"
    if ext == "pdf":
        return head[:4] == b"%PDF"
    return head[:1] not in (b"<", b"{", b"")


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




@app.post("/admin/reset")
async def admin_reset(request: Request):
    """Wipe ALL clients/projects/runs + project artifact folders. Requires
    the app token when one is set (same gate as every route)."""
    import shutil as _sh
    _auth(request)
    form = await request.form()
    confirm = str(form.get("confirm", "")).strip().lower()
    if confirm != "reset everything":
        return PlainTextResponse("Refusing: type 'reset everything' in the confirm field.", status_code=400)
    db.reset_all()                     # DB rows: clients, projects, runs, feedback
    if settings.DATA_DIR.is_dir():
        for child in settings.DATA_DIR.iterdir():
            if child.name in ("kabarbaik.db",):
                continue
            if child.is_dir():
                _sh.rmtree(child, ignore_errors=True)   # per-project artifact folders
    db.init()                          # recreate schema fresh
    return RedirectResponse("/", status_code=303)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
