# KabarBaik SDLC Web App

A thin orchestration layer over the **termux-ai** `ai` binary that drives the
**KabarBaik SDLC workflow** described by the team-kit:

```
Discovery → Initial BRD + PRD → Prototype → Present + feedback
→ Proposal → (approved) Update BRD/PRD + TSD + SAD → Task breakdown
→ Development → Monthly report
```

The web app never talks to model APIs itself. Every AI step shells out to
termux-ai (`ai --skill <name>`), which reads its **own** `~/.config/termux-ai/config.json`
and therefore always uses the currently active backend + model (bynara,
openrouter, ollama, …). Switch backends in termux-ai; this app follows.

## How it maps to the team-kit

| App stage | team-kit skill / artifact |
|-----------|---------------------------|
| Discovery & Requirement Gathering | `doc-ingest` → `docs/inbox/` → `docs/discovery/discovery.md` |
| Initial BRD + PRD | `discovery` + `templates/brd.md`, `templates/prd.md` |
| Prototype | `webapp` (prototype mode) → `docs/prototype/` |
| Present + feedback | `client-feedback` → `docs/prd/change-requests.md` |
| Proposal | `proposal` → `docs/proposal/proposal-vN.md` |
| Update BRD/PRD + TSD + SAD | `tsd-sad` → `docs/tsd/tsd.md`, `docs/sad/sad.md` + ADRs |
| Break down dev tasks | `epic-breakdown` → `docs/plan/backlog.md` |
| Development | tracked externally (PM/CI) |
| Monthly report | `deploy-checklist` → `docs/reports/monthly-yyyy-mm.md` |

Artifacts live on disk following the team-kit `docs-folders.md` convention under
`data/projects/<client>/<project>/docs/…`. SQLite at `data/kabarbaik.db` only
tracks workflow state (clients, projects, stage runs, feedback).

## Setup

```bash
cd kabarbaik-app
python3 -m venv --without-pip .venv
python3 /tmp/opencode/get-pip.py   # or any pip bootstrap
.venv/bin/pip install -r requirements.txt
```

`ai_runner.install_team_kit_skills()` (called automatically on startup) copies
the team-kit pipeline skills into `~/.config/termux-ai/skills/` so `ai --skill`
can resolve them.

## Run (localhost only)

```bash
.venv/bin/python -m main            # binds 127.0.0.1:8021
```

Optional auth token:

```bash
KABARBAIK_TOKEN=secret .venv/bin/python -m main
# then access via http://127.0.0.1:8021/?token=secret
```

## Config (env vars)

- `KABARBAIK_AI_BIN` — path to the `ai` binary (default `~/.local/bin/ai`)
- `KABARBAIK_DATA_DIR` — artifacts + DB root (default `./data`)
- `KABARBAIK_HOST` / `KABARBAIK_PORT` — bind address (default `127.0.0.1:8021`)
- `KABARBAIK_TOKEN` — optional shared token gate
- `KABARBAIK_AI_CONFIG_DIR` — termux-ai config dir (default `~/.config/termux-ai`)
- `KABARBAIK_MAX_UPLOAD_BYTES` — upload cap (default 15 MB)

## Notes

- Meeting notes / requirements can be **uploaded** (pdf/docx/xlsx/…) into the
  project inbox or **typed in a rich-text editor** (CKEditor 5); both land in
  `docs/inbox/` for `doc-ingest` to normalize.
- Document artifacts are edited as Markdown (source-of-truth), rendered with a
  live preview.