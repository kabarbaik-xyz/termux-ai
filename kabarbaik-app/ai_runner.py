"""Subprocess wrapper around the termux-ai ``ai`` binary.

The web app never calls the model APIs directly — it shells out to termux-ai,
which reads its own config.json and therefore always uses the currently active
backend + model. This module provides:

* ``run()`` — a one-shot call with optional skill/tools flags and stdin context.
* ``active_backend()`` — read termux-ai's config.json to display the active
  backend/model in the UI (read-only; termux-ai remains the single source).
* ``install_team_kit_skills()`` — copy the team-kit house skills into the live
  skills dir so ``ai --skill <name>`` can resolve them.

The ``ai`` binary is a single-file executable; we invoke it as a subprocess and
stream its output back to the caller (the FastAPI route returns it, so a long
document generation is streamed to the browser rather than buffered whole).
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path
from typing import Optional

import settings

# Skills in team-kit that form the SDLC pipeline (installed into the live dir).
PIPELINE_SKILLS = [
    "doc-ingest",
    "discovery",
    "client-feedback",
    "webapp",
    "proposal",
    "tsd-sad",
    "epic-breakdown",
    "go-api-endpoint",
    "py-api-endpoint",
    "nuxt-component",
    "nuxt-page",
    "db-migration",
    "deploy-checklist",
    "figma-tokens",
    "figma-to-component",
    "ui-audit",
]


class AiError(RuntimeError):
    pass


def ensure_binary() -> Path:
    """Accept either `ai` on PATH or the explicit AI_BINARY path."""
    if settings.AI_BINARY.is_file():
        return settings.AI_BINARY
    on_path = shutil.which("ai")
    if on_path:
        return Path(on_path)
    raise AiError(
        "termux-ai `ai` binary not found. Set KABARBAIK_AI_BIN or build it "
        "with `python3 build.py` in the termux-ai repo."
    )


def active_backend() -> dict:
    """Return {backend, model, base_url, available} describing termux-ai's active setup."""
    cfg = {}
    try:
        cfg = json.loads(settings.TERMUX_AI_CONFIG_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"backend": "(unconfigured)", "model": "", "base_url": "", "available": False}
    except Exception:
        return {"backend": "(unreadable config)", "model": "", "base_url": "", "available": False}

    backend = cfg.get("backend", "ollama")
    model = ""
    base_url = ""
    backends = cfg.get("backends") or {}
    prof = backends.get(backend) or {}
    if isinstance(prof, dict):
        model = prof.get("model") or ""
        base_url = prof.get("base_url") or ""
    return {
        "backend": backend,
        "model": model,
        "base_url": base_url,
        "available": True,
    }


def install_team_kit_skills() -> list:
    """Copy team-kit skills into the live termux-ai skills dir.

    The `ai` binary loads skills only from its config-dir skills folder, so for
    `--skill <name>` to work for the pipeline skills we stage them there.
    Existing files are never overwritten (a user may have customized a skill).
    Returns the list of names installed (created).
    """
    settings.ensure_dirs()
    src = settings.TEAM_KIT_DIR / "skills"
    installed = []
    if not src.is_dir():
        return installed
    for name in PIPELINE_SKILLS:
        f = src / f"{name}.md"
        dst = settings.AI_SKILLS_DIR / f"{name}.md"
        if f.is_file() and not dst.exists():
            shutil.copyfile(f, dst)
            installed.append(name)
    return installed


async def run(
    prompt: str,
    *,
    project_dir: Path,
    skill: Optional[str] = None,
    json_mode: bool = False,
    tools: Optional[str] = None,
    process: Optional[str] = None,
    stdin_data: Optional[str] = None,
    model: Optional[str] = None,
    timeout: float = 900.0,
):
    """Run one `ai` one-shot inside project_dir and stream lines to the caller.

    Yields the text output line-by-line (so the browser can show progress).
    An ``ai`` non-zero exit or an empty response raises AiError.
    """
    binary = ensure_binary()
    argv = [str(binary)]
    if model:
        argv += ["-m", model]
    if json_mode:
        argv += ["-j"]
    if skill:
        argv += ["--skill", skill]
    if tools in ("on", "off"):
        argv += ["--tools", tools]
    if process in ("on", "off", "auto"):
        argv += ["--process", process]
    argv.append(prompt)

    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(project_dir),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=stdin_data.encode("utf-8") if stdin_data else None),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        raise AiError("termux-ai call timed out.")

    out = stdout.decode("utf-8", errors="replace")
    err = stderr.decode("utf-8", errors="replace")

    text = out.strip()
    if proc.returncode != 0:
        # Fall back to showing stderr when stdout is empty.
        detail = (text or err).strip()
        raise AiError(detail or f"termux-ai exited {proc.returncode}.")
    if not text:
        raise AiError("termux-ai returned no output.")

    # Emit stdout line-by-line (already captured; in future this can stream).
    for line in out.splitlines():
        yield line
