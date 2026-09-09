"""Async subprocess wrapper around the termux-ai CLI.

Runs one `ai` invocation and returns the full output as a string.
Raises AiError when the process fails or times out.
"""

import asyncio
import os
import re
from pathlib import Path

import settings
from settings import AI_BINARY, PROJECTS_ROOT


class AiError(Exception):
    """Raised when the AI subprocess fails or times out."""


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
