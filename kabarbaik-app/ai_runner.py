"""Async subprocess wrapper around the termux-ai CLI.

Runs one `ai` invocation and returns the full output as a string.
Raises AiError when the process fails or times out.
"""

import asyncio
import os
import re
import shutil
from pathlib import Path

import settings
from settings import AI_BINARY, PROJECTS_ROOT


class AiError(Exception):
    """Raised when the AI subprocess fails or times out."""


async def run_stream(
    prompt: str,
    project_dir: Path | None = None,
    skill: str | None = None,
    tools: str = "on",
    timeout: float = 900.0,
):
    """Stream `ai` output line-by-line (async generator).

    Same invocation contract as run(), but yields each stdout line as it is
    emitted (ANSI-stripped) so the UI can show what the AI is doing while a
    stage runs. Raises AiError on failure/timeout like run() does; on generator
    close/cancel the subprocess is terminated so runs never orphan.
    """
    cmd = [AI_BINARY, "--yes"]
    if skill:
        cmd += ["--skill", skill]
    cmd += ["--tools", tools]
    cmd += [prompt]

    cwd = str(project_dir) if project_dir else str(PROJECTS_ROOT)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=cwd,
        env=os.environ.copy(),
    )
    import time as _time
    deadline = _time.monotonic() + timeout
    buf = []
    try:
        while True:
            remaining = deadline - _time.monotonic()
            if remaining <= 0:
                raise asyncio.TimeoutError()
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
            if not line:
                break
            text = _strip_ansi(line.decode("utf-8", errors="replace")).rstrip()
            if text:
                buf.append(text)
                yield text
        rc = await asyncio.wait_for(proc.wait(), timeout=max(remaining, 5))
        if rc != 0:
            raise AiError(f"ai exited with code {rc}: {' '.join(buf[-3:])[:200]}")
        if not any(b.strip() for b in buf):
            raise AiError("ai produced no output (empty response from the gateway).")
    except asyncio.TimeoutError:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        raise AiError("termux-ai call timed out.")
    except BaseException:
        # client disconnected / generator cancelled — don't orphan the process
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        raise


def max_usage_id() -> int:
    """Highest row id in termux-ai's usage_log — a checkpoint to measure
    exactly the requests a stage run makes (-1 when unavailable)."""
    import sqlite3
    hist = settings.TERMUX_AI_CONFIG_DIR / "ai_history.db"
    try:
        conn = sqlite3.connect(f"file:{hist}?mode=ro", uri=True, timeout=5)
        row = conn.execute("SELECT COALESCE(MAX(id), -1) FROM usage_log").fetchone()
        conn.close()
        return int(row[0])
    except Exception:
        return -1


def usage_after(checkpoint: int) -> tuple:
    """(tin, tout) summed over usage_log rows with id > checkpoint — i.e. the
    tokens consumed by the requests made since the checkpoint. Real backend-
    reported usage; estimation fallback rows are included (they're what the
    gateway gave us)."""
    import sqlite3
    hist = settings.TERMUX_AI_CONFIG_DIR / "ai_history.db"
    try:
        conn = sqlite3.connect(f"file:{hist}?mode=ro", uri=True, timeout=5)
        row = conn.execute(
            "SELECT COALESCE(SUM(tin),0), COALESCE(SUM(tout),0) "
            "FROM usage_log WHERE id > ?", (checkpoint,)).fetchone()
        conn.close()
        return int(row[0]), int(row[1])
    except Exception:
        return 0, 0


def install_team_kit_skills() -> list:
    """Sync team-kit skills into the live termux-ai skills dir.

    The `ai` binary loads skills ONLY from its config-dir skills folder, so
    ``--skill <name>`` resolves only what is staged there. Copies every
    team-kit/skills/*.md whose content differs from the live copy — new AND
    updated kit skills propagate automatically on every app start (a fresh
    machine just needs git pull + run). Returns the names installed/updated.
    """
    settings.ensure_dirs()
    src = settings.TEAM_KIT_DIR / "skills"
    installed = []
    if not src.is_dir():
        return installed
    for f in sorted(src.glob("*.md")):
        dst = settings.AI_SKILLS_DIR / f.name
        try:
            if (not dst.exists()
                    or dst.read_text(errors="ignore") != f.read_text(errors="ignore")):
                shutil.copyfile(f, dst)
                installed.append(f.stem)
        except OSError:
            continue
    return installed


def active_backend() -> dict:
    """Mirror termux-ai's backend resolution (src/config.py active_profile).

    Follows whatever backend/model termux-ai has active — this app never
    stores its own copy. ``available`` is False only when the config is
    missing, the active backend has no profile, or no API key is set
    (local/ollama backends need no key).
    """
    import json
    try:
        cfg = json.loads(settings.TERMUX_AI_CONFIG_FILE.read_text())
    except (OSError, ValueError):
        return {"backend": "not configured", "model": "", "available": False}

    name = cfg.get("backend") or cfg.get("default_backend") or "ollama"
    prof = (cfg.get("backends") or {}).get(name)
    if not isinstance(prof, dict) or not prof:
        return {"backend": name, "model": "", "available": False}

    model = prof.get("model") or cfg.get("model") or ""
    key = prof.get("api_key") or (cfg.get("api_keys") or {}).get(name) or ""
    base = str(prof.get("base_url") or "")
    local = ("localhost" in base or "127.0.0.1" in base
             or base.endswith(":11434/v1") or name == "ollama")
    return {"backend": name, "model": model, "available": bool(key) or local}


async def run(
    prompt: str,
    project_dir: Path | None = None,
    skill: str | None = None,
    tools: str = "on",
    timeout: float = 900.0,
) -> str:
    """Run one `ai` invocation and return its stdout.

    Parameters
    ----------
    prompt : str
        The task description sent to the model.
    project_dir : Path | None
        Working directory for the `ai` process (defaults to PROJECTS_ROOT).
    skill : str | None
        Activate this skill before running (e.g. ``"discovery"``).
    tools : str
        ``"on"`` to enable tool calls.
    timeout : float
        Maximum seconds for the entire call.

    Returns
    -------
    str
        Full stdout from the ``ai`` process with ANSI codes stripped.
    """
    cmd = [AI_BINARY, "--yes"]
    if skill:
        cmd += ["--skill", skill]
    cmd += ["--tools", tools]
    cmd += [prompt]

    cwd = str(project_dir) if project_dir else str(PROJECTS_ROOT)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        cwd=cwd,
        env=os.environ.copy(),
    )

    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        raise AiError("termux-ai call timed out.")

    if proc.returncode != 0:
        text = stdout.decode("utf-8", errors="replace")
        raise AiError(f"ai exited with code {proc.returncode}: {text[:200]}")

    out = _strip_ansi(stdout.decode("utf-8", errors="replace"))
    if not out.strip():
        # Gateways sometimes return an empty 200 after a long hang — treat as
        # a failure so callers can retry instead of recording a phantom "ok".
        raise AiError("ai produced no output (empty response from the gateway).")
    return out


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from a string."""
    return re.sub(r'\x1b\[[0-9;]*[mKH]|\x1b\][^\x07]*\x07', '', text)
