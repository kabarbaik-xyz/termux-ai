"""KabarBaik SDLC web app — settings & paths.

Everything is configurable via environment variables, with sane default paths
relative to this project. The web app is a THIN layer: all AI work is done by
shelling out to the termux-ai ``ai`` binary, which reads its own config
(~/.config/termux-ai/config.json) and therefore always uses the user's
currently active backend + model (bynara, openrouter, ollama, ...).
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent

# The termux-ai single-file executable we shell out to.
AI_BINARY = Path(
    os.environ.get("KABARBAIK_AI_BIN", os.path.expanduser("~/.local/bin/ai"))
)

# termux-ai's own config dir (read-only, to display the active backend/model).
TERMUX_AI_CONFIG_DIR = Path(
    os.environ.get(
        "KABARBAIK_AI_CONFIG_DIR", os.path.expanduser("~/.config/termux-ai")
    )
)
TERMUX_AI_CONFIG_FILE = TERMUX_AI_CONFIG_DIR / "config.json"

# Live skills dir that the `ai` binary seeds/loads skills from. Team-kit skills
# are installed here so `ai --skill <name>` resolves them (no CLI flag exists).
AI_SKILLS_DIR = TERMUX_AI_CONFIG_DIR / "skills"

# Where this app keeps its SQLite metadata + per-project artifact folders.
DATA_DIR = Path(
    os.environ.get("KABARBAIK_DATA_DIR", PROJECT_DIR / "data")
)
PROJECTS_ROOT = DATA_DIR / "projects"      # <client>/<project>/ with docs/...
DB_PATH = DATA_DIR / "kabarbaik.db"

# Local-only auth.
HOST = os.environ.get("KABARBAIK_HOST", "127.0.0.1")
PORT = int(os.environ.get("KABARBAIK_PORT", "8021"))
TOKEN = os.environ.get("KABARBAIK_TOKEN", "").strip()  # empty = local only

# Where the team-kit lives (for installing skills/templates into the live skill dir).
TEAM_KIT_DIR = PROJECT_DIR.parent / "team-kit"

# Maximum bytes for an uploaded reference file.
MAX_UPLOAD_BYTES = int(os.environ.get("KABARBAIK_MAX_UPLOAD_BYTES", str(15 * 1024 * 1024)))

ALLOWED_UPLOAD_EXT = {
    ".md", ".txt", ".pdf", ".docx", ".xlsx", ".eml", ".csv",
    ".json", ".html", ".htm", ".rtf",
}


def ensure_dirs() -> None:
    for p in (DATA_DIR, PROJECTS_ROOT, AI_SKILLS_DIR):
        p.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
