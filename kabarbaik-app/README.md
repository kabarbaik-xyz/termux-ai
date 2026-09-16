# KabarBaik Web App

A thin orchestration layer over the **termux-ai** `ai` binary that drives two
workflows defined by the team-kit: the **SDLC workflow** (software build) and
the **Training workflow** (courses for the hosted **kbti-elearning** platform).

Each project is created with a **kind**:

- **SDLC** — software delivery:
  ```
  Gather Client Requirements → Draft BRD & PRD → Design Screens & Style (UX)
  → Build the Clickable Prototype → Write the Proposal → Finalize Docs After
  Approval → Prepare the QA Plan → Plan the Development Backlog
  ```
- **Training** — mindset-first course production for kbti-elearning:
  ```
  Understand the Training Request → Research the Evidence Base
  → Design the Curriculum → Write the Modules & Lessons → Write the Training
  Proposal → Design the Course Experience (UX) → Author & Validate the Course
  Package → QA the Course (Outcome Check) → Plan the Rollout
  ```

Client feedback arrives via **inbox uploads** (not a stage): upload meeting
notes / signed proposals / change requests to `docs/inbox/` and re-run the
relevant stage. Development and reporting are tracked outside the app.

The web app never talks to model APIs itself. Every AI step shells out to
termux-ai (`ai --skill <name> --yes`), which reads its **own**
`~/.config/termux-ai/config.json` and therefore always uses the currently
active backend + model. Switch backends in termux-ai (`/backend`); this app
follows — the dashboard shows the live backend/model.

## Stages → team-kit skills (SDLC)

| # | Stage | Skill | Produces (verified) |
|---|-------|-------|---------------------|
| 1 | Gather Client Requirements | `doc-ingest` | `docs/discovery/discovery.md` + SRC files |
| 2 | Draft the BRD & PRD | `discovery` | `docs/brd/brd.md` + `docs/prd/prd.md` — **filled documents following the kit templates**, US-xxx/BO-x IDs |
| 3 | Design Screens & Style (UX) | `ux-design` | `docs/03-ux-spec.md` + `design-tokens.json` |
| 4 | Build the Clickable Prototype | `prototype` | `prototype/` — spec-driven, tokens-only, self-contained HTML |
| 5 | Write the Proposal | `proposal` | `docs/proposal/proposal-vN.md` (versioned house format: exec summary + project table, solution pillars, scope, phases, budget in separate components — HR + one-time + subscriptions + AI op-cost — with payment terms & an Assumptions & Decisions appendix; in the source docs' language) |
| 6 | Finalize Docs After Approval | `tsd-sad` | final `brd.md`/`prd.md` + `docs/tsd/tsd.md` + `docs/sad/sad.md` + ADRs — derived from the **final proposal** (docs/inbox/ first, else proposal-vN) |
| 7 | Prepare the QA Plan | `qa-spec` | `docs/08-test-cases.md` + `docs/09-acceptance-criteria.md` + `docs/10-corner-cases.md` |
| 8 | Plan the Development Backlog | `epic-breakdown` | `docs/plan/backlog.md` — consumes the QA package (TC IDs, AC verbatim, P0/P1 risks in DoD) |

## Stages → team-kit skills (Training)

| # | Stage | Skill | Produces (verified) |
|---|-------|-------|---------------------|
| 1 | Understand the Training Request | `training-brief` (+ `doc-ingest` on `docs/inbox/`) | `docs/training/discovery/discovery.md` — training field, target audience, end goal |
| 2 | Research the Evidence Base | `evidence-research` | `docs/training/research/evidence-base.md` (inline `[R-n]` citations, Direct/Adapted findings) + `references.md` |
| 3 | Design the Curriculum | `training-design` | `docs/training/curriculum/curriculum.md` — modules → lessons, learning objectives |
| 4 | Write the Modules & Lessons | `lesson-script` | `docs/training/modules/*.md` — lesson content following the kit's lesson structure |
| 5 | Write the Training Proposal | `proposal` (training mode) | `docs/training/proposal/proposal-vN.md` + `docs/training/preview/modules-preview.md` — how the course changes behavior |
| 6 | Design the Course Experience | `ux-design` (KBTI Course Experience mode) | `docs/training/spec/course-spec.md` — course metadata, audience roles, lesson outline, KBTI style (never rebranding platform chrome) |
| 7 | Author & Validate the Course Package | `elearning` | `elearning-package/<course-id>/course.json` + lesson markdown — schema-validated, then **installed** into the kbti-elearning platform (manifest updated atomically) |
| 8 | QA the Course (Outcome Check) | `learning-qa` | `docs/training/qa/review-checklist.md` — behavior-change alignment vs. the proposal |
| 9 | Plan the Rollout | `rollout` | `docs/training/rollout/rollout.md` — audiences, schedule, success metrics |

### What keeps the flow honest

- **Hard gates (code, not prompts)**: UX needs the PRD · Prototype needs the
  UX spec · QA needs TSD+SAD · post-approval needs a proposal. Training:
  Research needs the discovery file · Curriculum needs an evidence base ·
  Lessons need the curriculum · Proposal needs the modules preview · Course
  UX needs an **approved** proposal · Build needs the course spec (and the
  packaged course is schema-validated) · QA needs the package · Rollout needs
  QA sign-off. Blocked runs return instantly with instructions.
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

### Training course installs

Stage 7 (elearning_build) produces an `elearning-package/<course-id>/` inside
the project, then runs the app-side `install_course` step: the package is
schema-validated and copied into the kbti-elearning platform's
`courses/<course-id>/`, and the platform's `courses/manifest.json` is merged
atomically (a versioned manifest with a `course_ids` list; the platform only
lists courses present in it). Installs are idempotent and never touch other
courses. The platform location is `KABARBAIK_ELEARNING_DIR` (default
`~/kbti-elearning`, a small FastAPI app that serves the courses on its own
port/host — see that repo's README). An invalid package **fails** the stage
with the validation errors.

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
  - **Flow** — progress bar, steps colored by run status (8 for SDLC, 9 for
    Training):
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
  SAD, Backlog + the training-flow set: discovery, research, curriculum,
  lessons, modules preview, course spec, rollout) is listed, editable in-app,
  and versioned in git. Edits apply to new stage runs (seeding never
  overwrites existing project docs).
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
- `KABARBAIK_TEAM_KIT_DIR` — team-kit root with stage templates/schemas/skills
  (default `~/termux-ai/team-kit`)
- `KABARBAIK_MAX_UPLOAD_BYTES` — upload cap (default 15 MB)
- `KABARBAIK_ELEARNING_DIR` — kbti-elearning platform root that training
  course packages get installed into (default `~/kbti-elearning`)

## Tests

Pure-logic unit tests (no AI calls):

```bash
.venv/bin/python tests/test_training_flow.py   # training flow + install_course
```

Sandboxed end-to-end smoke (probes a real backend, runs stage 0 through the
`ai` binary, never touches the real `~/.config/termux-ai`):

```bash
KABARBAIK_AI_BIN=~/.local/bin/ai python3 tests/e2e_smoke.py
```

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
