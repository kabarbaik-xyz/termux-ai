"""SQLite metadata store — clients, projects, SDLC stage state.

The real artifacts live on disk under ``data/projects/<client>/<project>/docs/``
(per the team-kit docs-folder convention). This DB tracks the *progress*:
which stage a project is on, stage status, created documents, feedback entries.
File operations are the source of truth; this is a fast index + workflow state.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import settings

# Stage order for the KabarBaik SDLC flow. name maps to a team-kit skill +
# prompt recipe in workflow.py. Each stage is started once and flips to "done"
# when its artifact(s) exist.
STAGES = [
    ("discovery", "Discovery & Requirement Gathering"),
    ("brd_prd", "Initial BRD + PRD"),
    ("prototype", "Prototype"),
    ("feedback", "Present to Client & Gather Feedback"),
    ("proposal", "Proposal"),
    ("post_approval", "Update BRD/PRD + TSD + SAD"),
    ("task_breakdown", "Break Down Development Tasks"),
    ("development", "Development"),
    ("monthly_report", "Monthly Report"),
]

STAGE_IDX = {name: i for i, (name, _) in enumerate(STAGES)}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db() -> sqlite3.Connection:
    settings.ensure_dirs()
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init() -> None:
    with get_db() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS clients (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                name      TEXT NOT NULL UNIQUE,
                org       TEXT DEFAULT '',
                contact   TEXT DEFAULT '',
                notes     TEXT DEFAULT '',
                created   TEXT NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id   INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                name        TEXT NOT NULL,
                slug        TEXT NOT NULL,
                description TEXT DEFAULT '',
                stage       INTEGER NOT NULL DEFAULT 0,
                status      TEXT NOT NULL DEFAULT 'sandbox',
                created     TEXT NOT NULL,
                UNIQUE (client_id, slug)
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS stage_runs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                stage      TEXT NOT NULL,
                started    TEXT NOT NULL,
                finished   TEXT,
                status     TEXT NOT NULL DEFAULT 'running',
                target     TEXT DEFAULT '',
                log        TEXT DEFAULT '',
                UNIQUE (project_id, stage)
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                source     TEXT NOT NULL DEFAULT 'web',
                quote      TEXT DEFAULT '',
                notes      TEXT DEFAULT '',
                status     TEXT NOT NULL DEFAULT 'open',
                created    TEXT NOT NULL
            )
            """
        )
    settings.ensure_dirs()


# ---------- clients ----------

def add_client(name: str, org: str, contact: str, notes: str) -> int:
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO clients (name, org, contact, notes, created) VALUES (?,?,?,?,?)",
            (name.strip(), org, contact, notes, _utcnow()),
        )
        return cur.lastrowid


def list_clients() -> list[dict]:
    with get_db() as db:
        rows = db.execute("SELECT * FROM clients ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def get_client(client_id: int) -> Optional[dict]:
    with get_db() as db:
        r = db.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    return dict(r) if r else None


# ---------- projects ----------

def add_project(client_id: int, name: str, description: str) -> dict:
    slug = _slug(name)
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO projects (client_id, name, slug, description, created) VALUES (?,?,?,?,?)",
            (client_id, name, slug, description, _utcnow()),
        )
        pid = cur.lastrowid
    return get_project(pid)


def list_projects(client_id: Optional[int] = None) -> list[dict]:
    q = (
        "SELECT p.*, c.name AS client_name FROM projects p "
        "JOIN clients c ON c.id = p.client_id"
    )
    args: tuple = ()
    if client_id is not None:
        q += " WHERE p.client_id=?"
        args = (client_id,)
    q += " ORDER BY p.created DESC"
    with get_db() as db:
        rows = db.execute(q, args).fetchall()
    return [dict(r) for r in rows]


def get_project(project_id: int) -> Optional[dict]:
    with get_db() as db:
        r = db.execute(
            "SELECT p.*, c.name AS client_name FROM projects p "
            "JOIN clients c ON c.id = p.client_id WHERE p.id=?",
            (project_id,),
        ).fetchone()
    if not r:
        return None
    d = dict(r)
    d["stage_name"] = STAGES[d["stage"]][1] if 0 <= d["stage"] < len(STAGES) else "archived"
    return d


def set_stage(project_id: int, stage_index: int, status: str = "sandbox") -> None:
    with get_db() as db:
        db.execute(
            "UPDATE projects SET stage=?, status=? WHERE id=?",
            (stage_index, status, project_id),
        )


# ---------- stage runs ----------

def start_stage(project_id: int, stage: str, target: str = "") -> None:
    now = _utcnow()
    with get_db() as db:
        db.execute(
            "INSERT OR REPLACE INTO stage_runs (project_id, stage, started, target, status) "
            "VALUES (?,?,?,?, 'running')",
            (project_id, stage, now, target),
        )


def finish_stage(project_id: int, stage: str, ok: bool, log: str = "") -> None:
    with get_db() as db:
        db.execute(
            "UPDATE stage_runs SET finished=?, status=?, log=? WHERE project_id=? AND stage=?",
            (_utcnow(), "ok" if ok else "failed", log, project_id, stage),
        )


def get_stage_run(project_id: int, stage: str) -> Optional[dict]:
    with get_db() as db:
        r = db.execute(
            "SELECT * FROM stage_runs WHERE project_id=? AND stage=?",
            (project_id, stage),
        ).fetchone()
    return dict(r) if r else None


# ---------- feedback ----------

def add_feedback(project_id: int, source: str, quote: str, notes: str, status: str) -> int:
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO feedback (project_id, source, quote, notes, status, created) "
            "VALUES (?,?,?,?,?,?)",
            (project_id, source, quote, notes, status, _utcnow()),
        )
        return cur.lastrowid


def list_feedback(project_id: int) -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM feedback WHERE project_id=? ORDER BY created DESC",
            (project_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ---------- artifact index ----------

def index_artifacts(project_id: int) -> dict:
    """Walk the project's docs/ tree and return {folder: [filenames]}."""
    p = get_project(project_id)
    if not p:
        return {}
    root = project_dir(p)
    docs = root / "docs"
    if not docs.is_dir():
        return {}
    out = {}
    for folder in sorted(d for d in docs.iterdir() if d.is_dir()):
        files = sorted(f for f in folder.iterdir() if f.is_file() and not f.name.startswith("."))
        if files:
            out[folder.name] = [f.name for f in files]
    return out


# ---------- paths ----------

def project_dir(project: dict) -> Path:
    return settings.PROJECTS_ROOT / _slug(project["client_name"]) / project["slug"]


def design_dir(project: dict) -> Path:
    return project_dir(project) / "docs"


def _slug(name: str) -> str:
    import re

    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return base or "project"