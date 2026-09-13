# KabarBaik SDLC Web App

A thin orchestration layer over the **termux-ai** `ai` binary that drives the
**KabarBaik SDLC workflow** described by the team-kit:

```
Discovery → Initial BRD + PRD → UX Design (spec + tokens) → Prototype
→ Proposal → Update BRD/PRD + TSD + SAD → QA Package → Task Breakdown
```

Client feedback arrives via **inbox uploads** (not a stage): upload meeting
notes / signed proposals / change requests to `docs/inbox/` and re-run the
relevant stage. Development and reporting are tracked outside the app.

The web app never talks to model APIs itself. Every AI step shells out to
termux-ai (`ai --skill <name> --yes`), which reads its **own**
`~/.config/termux-ai/config.json` and therefore always uses the currently
active backend + model. Switch backends in termux-ai (`/backend`); this app
follows — the dashboard shows the live backend/model.

## Stages → team-kit skills

| # | Stage | Skill | Produces (verified) |
|---|-------|-------|---------------------|
| 1 | Discovery & Requirement Gathering | `doc-ingest` | `docs/discovery/discovery.md` + SRC files |
| 2 | Initial BRD + PRD | `discovery` | `docs/brd/brd.md` + `docs/prd/prd.md` — **filled documents following the kit templates**, US-xxx/BO-x IDs |
| 3 | UX Design (Spec + Tokens) | `ux-design` | `docs/03-ux-spec.md` + `design-tokens.json` |
| 4 | Prototype | `prototype` | `prototype/` — spec-driven, tokens-only, self-contained HTML |
| 5 | Proposal | `proposal` | `docs/proposal/proposal-vN.md` (versioned; pricing stays human) |
| 6 | Update BRD/PRD + TSD + SAD | `tsd-sad` | final `brd.md`/`prd.md` + `docs/tsd/tsd.md` + `docs/sad/sad.md` + ADRs — derived from the **final proposal** (docs/inbox/ first, else proposal-vN) |
| 7 | QA Package | `qa-spec` | `docs/08-test-cases.md` + `docs/09-acceptance-criteria.md` + `docs/10-corner-cases.md` |
| 8 | Break Down Development Tasks | `epic-breakdown` | `docs/plan/backlog.md` — consumes the QA package (TC IDs, AC verbatim, P0/P1 risks in DoD) |

### What keeps the flow honest

- **Hard gates (code, not prompts)**: UX needs the PRD · Prototype needs the
  UX spec · QA needs TSD+SAD · post-approval needs a proposal. Blocked runs
  return instantly with instructions.
- **Artifact verification**: a stage is `ok` only if it produced/updated its
  expected files. Phantom runs ("said done, wrote nothing") and **unfilled
  template copies** (placeholder markers survived) fail loudly.
- **Interrupted runs** (tab closed / server stopped) are marked `failed` with
  a re-run note; any stale `running` row at boot is auto-recovered.
- One transparent retry (30s gap) on gateway errors; empty AI output is a
  retryable failure, never a silent success.

Artifacts live on disk under `data/projects/<client>/<project>/docs/…`.
SQLite at `data/kabarbaik.db` tracks workflow state (clients, projects,
stage runs **incl. token usage**, feedback).

## Setup

```bash
cd kabarbaik-app
python3 -m venv --without-pip .venv
python3 /tmp/opencode/get-pip.py   # or any pip bootstrap
.venv/bin/pip install -r requirements.txt

# System tools (full matrix in requirements.txt):
pkg install poppler curl   # Termux; poppler-utils + curl on Debian
# optional legacy-office converters:
pkg install antiword       # .doc uploads
```

On startup the app **auto-seeds team-kit skills** into
`~/.config/termux-ai/skills/` (content-sync: new *and updated* kit skills
propagate — a fresh machine just needs `git pull` + run), and recovers any
interrupted stage runs.

## Run (localhost only)

```bash
.venv/bin/python main.py             # binds 127.0.0.1:8021
```

> Run it exactly like this (`main.py`, **not** `python -m main`) — see
> Troubleshooting.

Optional auth token:

```bash
KABARBAIK_TOKEN=secret .venv/bin/python main.py
# then access via http://127.0.0.1:8021/?token=secret
```

## The UI

- **Dashboard** — stats (clients · projects · stages done · tokens used),
  per-project progress bars, danger zone (typed-confirm reset).
- **Project page (real tabs)**
  - **Flow** — progress bar, 8 steps colored by run status:
    **green** = ran & succeeded · **red** = failed · **blue** = never run.
    Ran stages offer `↻ Re-run`; a live run shows a spinner and disables
    every other stage button (survives refresh).
  - **Console** — **live AI console**: streams what the AI does line-by-line
    (SSE). Runs live server-side, so closing the tab doesn't stop them;
    refreshing re-attaches and replays; reconnects resume from the exact
    event; the console tail is stored in the run log.
  - **Documents** — folder board of all artifacts; click to view/edit
    markdown in place.
  - **Inputs** — upload file / paste link (Google Docs → docx/xlsx/pptx) /
    write note; inbox list with extracted-sidecar pills.
  - **Feedback** — structured client quotes.
  - **Tokens** — per-stage + project token totals (read from termux-ai's
    per-request usage log).
- **Templates** — every document stage's template (BRD, PRD, Proposal, TSD,
  SAD, Backlog) is listed, editable in-app, and versioned in git. Edits apply
  to new stage runs (seeding never overwrites existing project docs).
- **Theme** — KBTI brand (learned from kbti.cloud): red `#a11c1c` accents,
  navy console, the KabarBaik logo in the header + favicon.
  `design-tokens.json` is the source of truth; `docs/ux-redesign.md` is the
  UI spec.

## Reset (wipe all clients/projects/runs + artifacts)

```bash
curl -X POST -d "confirm=reset everything" http://127.0.0.1:8021/admin/reset
# with a token: http://127.0.0.1:8021/admin/reset?token=secret
```

- Immediate, no undo — deletes all DB rows (clients, projects, stage runs,
  feedback), empties `data/projects/`, re-inits the schema.
- Wrong/missing confirm field → `400` refusal. Also available as the
  Dashboard's danger-zone card.
- Without the server running:

```bash
python3 -c "import db; db.reset_all(); db.init()"   # DB rows
rm -rf data/projects                                  # artifacts
```

## Config (env vars)

- `KABARBAIK_AI_BIN` — path to the `ai` binary (default `~/.local/bin/ai`)
- `KABARBAIK_DATA_DIR` — artifacts + DB root (default `./data`)
- `KABARBAIK_HOST` / `KABARBAIK_PORT` — bind address (default `127.0.0.1:8021`)
- `KABARBAIK_TOKEN` — optional shared token gate
- `KABARBAIK_AI_CONFIG_DIR` — termux-ai config dir (default `~/.config/termux-ai`)
- `KABARBAIK_MAX_UPLOAD_BYTES` — upload cap (default 15 MB)

## Notes

- Meeting notes / requirements can be **uploaded** into the project inbox,
  **pasted as a link** (Google Docs/Sheets/Slides/Drive — link-shared docs are
  exported to docx/xlsx/pptx automatically), or **typed in a rich-text
  editor**; all land in `docs/inbox/` for `doc-ingest` to normalize.
- Upload formats: `md txt csv json html htm` + `pdf docx pptx xlsx` (read
  directly by the AI; PDF needs `poppler`) + `rtf eml` (parsed to
  `<name>.extracted.md` sidecars) + `doc ppt xls odt` (converted if
  `soffice`/`antiword`/`catdoc` present, else tracked as a binary-source
  stub). External tools: `poppler` (PDF), `curl` (link ingestion) — see
  requirements.txt.
- Document artifacts are edited as Markdown (source-of-truth), rendered with a
  live preview.
- **API-ish endpoints**: `GET /api/status` (backend + token state),
  `GET /healthz`, `GET /projects/{pid}/stage/{n}/stream` (SSE console).

## Troubleshooting

- **`address already in use`** — an older instance holds the port. Find it
  with `pgrep -af "python.*main"` and kill **the server process** (not your
  shell). Avoid starting with `python -m main`: that cmdline pattern is hard
  to target with pkill and has historically left zombie servers serving
  stale code.
- **Stage stuck "running"** — impossible now: interrupted runs are marked
  failed automatically (and any stale row at boot is recovered). Just re-run.
- **Colors look old** — hard-refresh once (the stylesheet is cache-busted
  with `?v=` bumps, but browsers can be stubborn).
- **AI produced nothing / gateway empty responses** — the run fails with a
  clear message and can be re-run; check termux-ai's active backend health
  (`/backend`) and consider switching if the free tier is degraded.
