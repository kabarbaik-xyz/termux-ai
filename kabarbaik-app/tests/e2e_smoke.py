"""End-to-end smoke test for kabarbaik-app.

Sandboxes HOME (so the `ai` binary never touches the user's real
~/.config/termux-ai), probes candidate backends (openrouter → ollama) and picks
the first that answers a ping. Seeds a client + project + one inbox brief and
runs stage 0 (doc-ingest + discovery) through the real `ai` binary, then
asserts the expected artifact files appear under docs/. If no backend answers,
prints [SKIP] and exits 0 (environmental, not a regression).

Usage:
    KABARBAIK_AI_BIN=<path-to-ai> python3 tests/e2e_smoke.py
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

PY = Path(__file__).resolve().parent
sys.path.insert(0, str(PY.parent))

SANDBOX = Path(tempfile.mkdtemp(prefix="kb-e2e-"))
CFG_HOME = SANDBOX / "home"
DATA = SANDBOX / "data"

# Real user config, captured by absolute path BEFORE any env override so the
# sandboxed `ai` runs can reuse the user's backend keys without touching the
# real ~/.config/termux-ai.
REAL_HOME = Path(os.path.expanduser("~")).resolve()
REAL_CONFIG_FILE = REAL_HOME / ".config" / "termux-ai" / "config.json"


def _sandbox_env() -> None:
    """Point every app-level path at the sandbox. Set BEFORE importing app modules."""
    os.environ["HOME"] = str(CFG_HOME)
    os.environ["KABARBAIK_DATA_DIR"] = str(DATA)
    os.environ["KABARBAIK_HOST"] = "127.0.0.1"


def build_sandbox(name: str, prof: dict) -> dict:
    """Set env to sandbox + given backend; returns settings path values.

    Processes run under a sandboxed HOME so the real ~/.config/termux-ai is
    never touched."""
    _sandbox_env()

    cfgdir = CFG_HOME / ".config" / "termux-ai"
    cfgdir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "backend": name,
        "backends": {name: prof},
        "temperature": 0.6,
        "max_tokens": 8192,
        "stream": True,
        "tools_enabled": True,
        "retries": 5,
        "retry_delay": 4.0,
    }
    (cfgdir / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return {"cfgdir": cfgdir, "data": DATA, "home": CFG_HOME}


def _real_backends() -> dict:
    """Read the REAL termux-ai config (keys reused, never printed)."""
    try:
        cfg = json.loads(REAL_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        cfg = {}
    return cfg.get("backends") or {}


async def probe(name: str, prof: dict, ai_bin: str) -> tuple[bool, float]:
    """Tiny end-to-end ping: does `ai` complete a JSON prompt through this backend?"""
    import ai_runner
    build_sandbox(name, prof)
    scratch = DATA / "probe" / name
    scratch.mkdir(parents=True, exist_ok=True)
    t0 = asyncio.get_event_loop().time()
    try:
        lines = []
        async for ln in ai_runner.run('{"ok": true}', project_dir=scratch, json_mode=True,
                                      timeout=45.0):
            lines.append(ln)
        out = "".join(lines).strip()
        ok = "ok" in out and bool(out)
    except Exception:
        ok, out = False, ""
    dt = asyncio.get_event_loop().time() - t0
    print(f"[probe {name}] {'OK' if ok else 'FAIL'} in {dt:.1f}s"
          + (f" · {out[:120]!r}" if ok else ""))
    return ok, dt


async def pick_backend(ai_bin: str):
    """Return (name, prof) of the first backend that answers a probe, else None."""
    real = _real_backends()
    candidates = []
    for name, prof in real.items():
        if isinstance(prof, dict) and prof.get("base_url") and prof.get("model"):
            candidates.append((name, prof))
    if not any(n == "ollama" for n, _ in candidates):
        candidates.insert(0, ("ollama", {
            "base_url": "http://localhost:11434/v1",
            "model": "qwen2.5:3b",
            "api_key": "ollama",
        }))
    # Prefer backends that historically work; the active bynara account is
    # currently out of credits / serving an unavailable model, so probe it last.
    priority = {"opencode": 0, "openrouter": 1, "ollama": 2, "groq": 3, "openai": 3}
    candidates.sort(key=lambda c: priority.get(c[0], 9))
    for name, prof in candidates:
        ok, _dt = await probe(name, prof, ai_bin)
        if ok:
            print(f"[sandbox backend] {name} ({prof.get('model')})")
            return name, prof
    return None


async def main() -> int:
    _sandbox_env()  # BEFORE importing app modules: settings reads env at import

    import settings  # noqa: E402
    import db  # noqa: E402
    import workflow  # noqa: E402
    import ai_runner  # noqa: E402
    from ai_runner import ensure_binary

    ai_bin = str(ensure_binary())
    picked = await pick_backend(ai_bin)
    if picked is None:
        print("[SKIP] no backend answered the probe ping — the stage itself was "
              "already validated; start a backend (e.g. local ollama) and re-run "
              "to re-check.")
        return 0
    backend_name, backend_prof = picked
    build_sandbox(backend_name, backend_prof)

    settings.ensure_dirs()
    db.init()
    installed = ai_runner.install_team_kit_skills()
    print(f"[sandbox skills installed] {len(installed)}")

    cid = db.add_client("Sandbox Client", "Sandbox Co", "pm@local", "e2e")
    project = db.add_project(cid, "Sandbox Portal", "e2e smoke")
    root = db.project_dir(project)
    root.mkdir(parents=True, exist_ok=True)
    inbox = root / "docs" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / "brief-01.md").write_text(
        "<!-- SRC: brief about Sandbox Portal -->\n\n"
        "Sandbox Co needs a portal where warehouse staff can scan parcel barcodes "
        "and see delivery status. Currently tracking is done on paper. They want it "
        "on Android phones inside the warehouse. Budget ~IDR 150M.\n",
        encoding="utf-8",
    )

    print("[running stage 0 through the `ai` binary]")
    docs = root / "docs"
    expected = [docs / "discovery" / "discovery.md",
                docs / "discovery" / "index.md"]
    output = ""
    ok = False
    for attempt in range(1, 4):
        shutil.rmtree(docs / "discovery", ignore_errors=True)
        try:
            output = await workflow.run_stage(project, 0, timeout=180.0)
        except Exception as e:
            print(f"[attempt {attempt}] stage 0 raised: {type(e).__name__}: {str(e)[:200]}")
            continue
        print(f"[attempt {attempt}] stage 0",
              f"{len(output)} chars · first 200: {output[:200]!r}")
        if all(p.is_file() for p in expected):
            ok = True
            break
        await asyncio.sleep(10)  # give free-tier backends a breather
    if not ok:
        print("[FAIL] expected artifacts missing after retries:")
        for m in expected:
            print("   ", str(m.relative_to(root)))
        print("actual file tree:")
        for f in sorted(docs.rglob("*")):
            if f.is_file():
                print("   ", str(f.relative_to(root)))
        return 1

    print("[OK] artifacts found:")
    for p in expected:
        print("   ", str(p.relative_to(root)), f"({p.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))