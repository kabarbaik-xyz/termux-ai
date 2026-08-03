# Termux AI CLI

A zero-dependency AI chat CLI for [Termux](https://termux.dev) on Android — and any terminal. Talks to OpenAI-compatible endpoints, Anthropic's Claude API natively, or runs fully offline with Ollama.

![version](https://img.shields.io/badge/version-6.8.0-green)
![python](https://img.shields.io/badge/python-3.8+-blue)
![dependencies](https://img.shields.io/badge/deps-zero-brightgreen)
![platform](https://img.shields.io/badge/platform-Android%20%7C%20Termux-orange)

---

## Features

- **Multi-backend support** — Ollama (local/free), OpenAI, Anthropic Claude, Groq, OpenRouter, or any OpenAI-compatible API
- **Streaming responses** with animated terminal spinner
- **Chat history** stored in SQLite — resume, search, rename, export, delete
- **Tool system (BUILD/PLAN modes)** — AI can read files, list directories, search code, and optionally write files & run shell commands (with batch confirmation)
- **Batch tool confirmation** — all tool calls in a single AI response are grouped; read-only tools (read, list, search) auto-execute without prompting, while dangerous actions (write, run_command) require one collective y/N
- **Smart failure handling** — if a tool action fails or is blocked, the AI is nudged to reflect and try a different approach; after 3 consecutive failed rounds it stops and explains, instead of thrashing
- **Iteration safety limit** — prompts "Continue working?" after every 10 tool-call iterations
- **File attachments** — automatically detects `./path` references in your prompt and attaches file contents
- **Directory scanning** — reference a folder and the AI reads all relevant source files
- **Office document reading** — reads `.docx`, `.pptx`, `.xlsx` natively (no dependencies)
- **PDF reading** — via `pdftotext` (optional, `pkg install poppler`)
- **Markdown rendering** — colored headings, bold, italic, inline code, code blocks, lists
- **Auto-compact** — summarizes long conversations (>3000 tokens) to save context
- **Auto-router** — falls back to another backend if the primary fails
- **Cost estimation** — tracks token usage and estimates spend
- **Tab completion** — auto-completes slash commands, backend names, and conversation IDs
- **Self-update** — update to the latest version from inside the CLI (`/update`)
- **Multi-line input** — toggle with `/multi`
- **Termux API integration** — clipboard copy/paste, TTS speech, Android share sheet
- **Ollama server management** — start/stop from inside the CLI
- **One-shot mode** — ask a question directly from the shell: `ai "what is rust?"`
- **Shell command generator** — `ai -c "list docker containers"` generates + runs a command

---

## Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/kabarbaik-xyz/termux-ai/main/install.sh | bash
```

Then restart your terminal (or `source ~/.bashrc`) and run:

```bash
ai
```

### What the installer does

1. Installs Python if missing
2. Installs `readline` for arrow-key history
3. Downloads the `ai` script to `~/.local/bin/`
4. Adds `~/.local/bin` to your `PATH`

---

## Backend Setup

### Option A: Ollama (free, local, no API key)

```bash
pkg install ollama
ollama pull llama3.2
ollama serve &
```

Ollama is the **default** backend — no configuration needed. Manage the server and its models from inside the CLI:

```
/server start            # start the local Ollama daemon
/server pull qwen2.5:3b  # download a model (progress bar; keep screen on)
/server models           # list installed models
/server search qwen      # search the registry
/server show qwen2.5:3b  # model details
/server rm qwen2.5:3b    # remove a model (frees storage)
/server stop
/server status
```

After a successful `/server pull`, it asks whether to switch the active model —
that prompt only appears when your active backend is the local one. The model
commands auto-start the server if it isn't running.

#### Model reference for 8 GB RAM Android devices

Rule of thumb: the model file **plus ~2–4 GB overhead** must fit in free RAM.
On an 8 GB phone, Android + Termux already use ~2.5–3.5 GB, leaving ~4–5 GB
for Ollama — so stick to quantized models with files ≤ ~2.5 GB. Sizes below are
the default quantizations, measured from [ollama.com](https://ollama.com/library).

| Model | File size | Verdict on 8 GB |
|---|---|---|
| `qwen2.5:0.5b` | 398 MB | fast but weak; handy for simple chores |
| `qwen2.5:1.5b` | 986 MB | best CPU-only speed/quality trade-off |
| `deepseek-r1:1.5b` | 1.1 GB | reasoning-style replies, decent speed |
| `llama3.2:1b` | 1.3 GB | tiny and quick |
| `gemma2:2b` | 1.6 GB | solid small all-rounder |
| `smollm2:1.7b` | 1.8 GB | fast and surprisingly capable |
| `qwen2.5:3b` | 1.9 GB | **sweet spot** — recommended default |
| `llama3.2:3b` | 2.0 GB | **sweet spot** — good alternative |
| `phi3:mini` | 2.2 GB | good, a bit dated |
| `qwen3:4b` | 2.5 GB | borderline — OK with a Vulkan GPU (`ollama-backend-vulkan`) |
| `gemma3:4b` | 3.3 GB | too tight — will swap and crawl |
| `qwen2.5:7b` | 4.7 GB | no — needs ~12 GB effective RAM |

Practical picks for an 8 GB phone: **`qwen2.5:3b`** or **`llama3.2:3b`** as your
everyday model, **`qwen2.5:1.5b`** when you want speed, and **`qwen3:4b`** only if
Vulkan acceleration works on your chip (most Snapdragon 8xx / Dimensity). Avoid
7B+ models entirely.

### Option B: Anthropic Claude

Get an API key from <https://console.anthropic.com/>

```
/profile set anthropic.api_key sk-ant-api03-xxxxx
/backend anthropic
```

### Option C: OpenAI

Get an API key from <https://platform.openai.com/api-keys>

```
/profile add openai https://api.openai.com/v1 gpt-4o sk-xxxxx
/backend openai
```

### Option D: Groq (free tier, fast)

Get an API key from <https://console.groq.com/keys>

```
/profile add groq https://api.groq.com/openai/v1 llama-3.3-70b-versatile gsk_xxxxx
/backend groq
```

### Option E: OpenRouter (100+ models)

Get an API key from <https://openrouter.ai/keys>

```
/profile add openrouter https://openrouter.ai/api/v1 anthropic/claude-3.5-sonnet sk-or-xxxxx
/backend openrouter
```

### Option F: Any OpenAI-compatible API

```
/profile add myserver https://my-api.example.com/v1 my-model my-api-key
/backend myserver
```

---

## Usage

### Interactive mode

```bash
ai
```

### One-shot mode

```bash
ai "explain the quicksort algorithm"
ai -c "compress a folder into a tarball"   # shell command generator
ai -m gpt-4o "what is TCP?"               # override model
ai -j "hello"                               # JSON output
```

### Piping input

```bash
cat error.log | ai "what went wrong?"
docker ps | ai "which container has port 8080?"
```

---

## Slash Commands

### Chat

| Command | Description |
|---|---|
| `/new` | Start a fresh conversation |
| `/show` | Show messages in current chat |
| `/history` | List past conversations |
| `/search <keyword>` | Search conversations by content |
| `/load <id>` | Load a conversation by ID |
| `/rename <title>` | Rename current conversation |
| `/delete [id]` | Delete a conversation |
| `/undo` | Undo last user+assistant message pair |
| `/regen` | Regenerate last response |
| `/retry <model>` | Retry with a different model |
| `/diff` | Show uncommitted git changes |
| `/compact` | Summarize chat to save tokens |
| `/export [file]` | Export chat to markdown |

### Model & Backend

| Command | Description |
|---|---|
| `/setup` | Run the interactive setup wizard |
| `/update` | Update the script to the latest version from GitHub |
| `/backends` | List configured profiles |
| `/backend <name>` | Switch active profile |
| `/model <name>` | Change model on active profile |
| `/profile add <n> <url> <model> [key]` | Add a new backend profile |
| `/profile set <n>.<field> <value>` | Update a profile field |
| `/profile show <name>` | Show profile details (key masked) |

### Settings

| Command | Description |
|---|---|
| `/system [prompt]` | View/set system prompt |
| `/config set <key> <value>` | Set any config value |
| `/config` | Show full config (keys masked) |
| `/tools [on\|off]` | Toggle BUILD (on) vs PLAN (off) mode |
| `/strategy [on\|off]` | Toggle strategy-before-act: the model outlines a numbered strategy, shows it, then executes step by step |
| `/think [on\|off]` | Toggle Claude extended thinking: deeper hidden reasoning before acting (Anthropic backend only; raises token use) |
| `/skill` | List / run reusable skills (`/skill <name> [args]`, `/skill new`, `/skill seed`) |
| `/multi [on\|off]` | Toggle multi-line input |
| `/tokens` | Show token usage for current chat |
| `/cost` | Estimate token cost spent |
| `/status` | Show current settings |

### Termux API & Server

| Command | Description |
|---|---|
| `/copy` | Copy last reply to clipboard |
| `/paste` | Paste clipboard and send to AI |
| `/speak` | TTS the last reply |
| `/share` | Share last reply via Android |
| `/server start\|stop\|status\|pull\|models\|search\|show\|rm` | Manage local Ollama server + pull/list/remove models |
| `/expand` (or `/last`) | View the **full** last reply (unfolded) in `less` — scroll/search, `q` to return |
| `/fold on\|off` | Toggle folding of long lists/tables (default on; `fold_head` controls how many stay visible) |
| `/clear` | Clear the screen |

### Sessions & resume

Every chat is saved to the local database as you go. On startup the app
**auto-resumes your last session** (config `auto_resume`, default on) and shows
a banner with the title, message count and when it was last active:
`[Resumed: "campaign dashboard" — 24 messages, last active 2h ago]`.

Everything auto-saves and re-attaches on resume, so the new model picks up
where you left off \u2014 including a `/compact` summary if you merged the
history earlier. The resume banner also flags a model change:
`[Resumed: ".." \u2014 24 messages, last active 2h ago \u2014 now on deepseek-chat; /retry to re-answer with the current model]`.

- `/continue` — resume the last session explicitly
- `/new` — start a fresh session (clears the resume pointer)
- `/load <id|name>` — load any past session by id or by name/title match
- `/sessions` — list saved sessions, pinned first (● = bookmarked)
- `/save [name]` — bookmark the current session (rename with a name)
- `/unsave` — un-bookmark the current chat
- `/history` — list all chats
- `/prune [days]` — delete old unpinned chats (or set `prune_days` in config to auto-prune on startup; 0 = off)
- `/import <file>` — restore a session from an `/export` backup
- `ai --continue` / `ai --new` / `ai -l <id>` — same, at launch
- `ai <prompt>` one-shot calls are unaffected (never auto-resume)

### Resilience & context

Backend hiccups (connection drops, timeouts, 429/5xx) are retried automatically
with exponential backoff (`retries`, `retry_delay` in config) — but only when
nothing has been printed yet, so you never see duplicated output. If the stream
drops mid-reply, nothing is saved and the app tells you to run `/retry`, which
regenerates with the same context.

Switching models never loses the conversation: `/model`, `/backend`, `/profile`
and `/retry <model>` only swap the client — history lives in the local database
and is re-attached on every turn, so the new model picks up exactly where the
last one left off. `/model` and `/backend` confirm how many messages stay in
context after the switch.

### Interrupted turns: continue, never restart

When a connection drops or a backend fails **mid-task**, the app snapshots the
in-flight state (already-executed tool calls + results) into a checkpoint and
**auto-continues** (config `auto_continue`, default **on**): a notice shows the
completed steps with a 2s window to press Ctrl+C and skip, then the model
receives a *"continue, don't redo"* instruction and picks up from the last
completed step — tool work is never re-executed from scratch. Up to
`max_auto_continue` (default 2) attempts before giving up.

The checkpoint is persisted, so after a phone kill/reboot, resuming the
session shows `[Interrupted turn pending: N tool steps completed]` and
`/retry` continues from the checkpoint instead of restarting. A fresh user
message clears the pending checkpoint.

### Compact output (folding)

Long **lists** and **tables** in a reply are folded inline (first `fold_head` items, default 8, then a dim `… N more — /expand to view`) so a big list doesn't flood a small screen. The full reply is always retained — run `/expand` (alias `/last`) to page through the whole thing in `less`. Folding is display-only (the saved reply is complete) and toggleable: `/fold off`, or set `fold_long_blocks`/`fold_head` in config. Paragraphs and code blocks are never folded.
| `/help` | Show all commands |
| `/exit` | Quit (Ctrl-C also works) |

---

## Tool Modes

### PLAN mode (default)

The AI can **read** files, list directories, search code, and run safe inspection commands (`ls`, `cat`, `grep`, `head`, etc.). It **cannot** write, modify, or delete anything.

Plan-mode commands run **without a shell** against a **read-only allowlist** (e.g. `ls`, `cat`, `grep`, `head`, `tail`, `find`, `wc`, `sort`, `git status/diff/log`, …). Pipes work (`grep foo f | wc -l`), but because there is no shell, redirects (`>`, `>>`), `&&`/`;`, command substitution (`$(…)`, backticks), newlines, and every non-allowlisted binary (including all interpreters) are inert or rejected. This is the complete security boundary for Plan mode.

In PLAN mode, the following command patterns are **automatically blocked** to prevent accidental modification:

`rm`, `mv`, `cp`, `touch`, `mkdir`, `chmod`, `chown`, `dd`, `tee`, `ln`, `rmdir`, `truncate`, `chattr`, `unlink`, `install`, `pip install`, `apt`, `pkg`, `npm`, `yarn`, `sed -i`, `awk -i`, `perl -i`, `find -delete` / `-exec` / `-ok`, `git rm` / `git clean` / `git reset --hard`, output redirection (`>`, `>>`), and interpreter execution (`python3 -c` / `-m`, `bash -c`, `sh -c`, `node`, `perl`, `ruby`, `php`, etc.).

### BUILD mode

```
/tools on
```

The AI can also **write files** and **run any shell command**. Key behaviors:

- **Batch confirmation** — all tool calls in one response are shown together; you approve or decline the entire batch with a single y/N
- **Auto-run for safe tools** — read-only tools (`read_file`, `list_files`, `search_files`, `fetch_url`) execute automatically without prompting
- **Web research** — `fetch_url` does an HTTP GET and returns the page as readable text (HTML stripped). The AI uses it to read/research websites directly. It refuses private/local addresses (127.0.0.1, localhost, 10.x …) as an SSRF guard unless `AI_FETCH_ALLOW_PRIVATE=1` is set; ~500 KB cap, 10s timeout.
- **GitHub repos** — for `api.github.com` calls, `fetch_url` auto-attaches `GITHUB_TOKEN`/`GH_TOKEN` (lifts the rate limit from 60→5000/hr). To **analyze a repo locally**, the AI uses `clone_repo <https-url>` (Build mode): it shallow-clones (`--depth 1`) into an isolated temp dir and returns the path, after which `read_file`/`search_files`/`list_files` work on it. HTTPS-only (blocks ssh/git@/file). Great for "summarize this repo", "find the bug in …", or "clone it and run the tests". Best with a capable model (`qwen2.5:3b`+ or cloud); a 0.5b can't manage multi-step repo tasks.
- **CWD sandbox** — `write_file` is restricted to the current working directory for safety
- **Chunked writes** — `write_file` supports `append=true` so large files (e.g. a full HTML dashboard) can be built in sections. If a tool-call response is **truncated by the output token limit** (OpenAI `finish_reason=length` / Anthropic `stop_reason=max_tokens`), the AI is told it was cut off and to split the work with `write_file` + `append` — instead of failing silently with empty arguments
- **Reflect-on-failure** — when a tool action errors or is blocked, a system note asks the AI to state what it will do differently before the next step (it learns the rules from the tool description up front, so it rarely proposes a blocked command at all)
- **Failure guard** — after 3 consecutive failed action rounds the AI stops and explains (rather than thrashing). The runaway backstop is **`max_iterations`** (default **50**, up from 25) and you're prompted to continue every **`continue_every`** tool calls (default 10). The continue prompt now offers **`a` = "yes, and don't ask again this task"** so a long, trusted run finishes uninterrupted. All three are configurable: `/config set max_iterations 100`. Skipped automatically in one-shot/piped mode
- **Bounded context** — each tool result is capped (default ~10 KB) and older tool results are trimmed to head snippets in-loop so long multi-step sessions stay within budget. **The most recent result is always kept in full** (the model must see what it just read to continue)
- **Final answer only** — mid-loop narration streams live to the terminal, but only the final answer is saved to chat history

---

## Configuration

All settings live in `~/.config/termux-ai/config.json`. Key settings:

| Key | Default | Description |
|---|---|---|
| `backend` | `ollama` | Active backend profile name |
| `system_prompt` | _(see below)_ | Persona: role, environment, and output style |
| `system_instruction` | `""` | If set, overrides the persona; the fixed tool-use rules are always appended |
| `temperature` | `0.7` | Sampling temperature |
| `max_tokens` | `4096` | Max response tokens |
| `stream` | `true` | Stream responses |
| `show_tokens` | `true` | Show token count per reply |
| `tools_enabled` | `false` | BUILD mode on/off |
| `tts_replies` | `false` | Auto-speak all replies |
| `multi_line` | `false` | Multi-line input mode |
| `auto_compact` | `true` | Auto-summarize a chat that exceeds ~3000 tokens |
| `max_file_chars` | `20000` | Max chars when attaching files |
| `attach_files` | `true` | Auto-detect file references |

Change any setting from inside the CLI:

```
/config set temperature 0.9
/config set max_tokens 8192
/config set system_instruction "You are a Python expert"
```

---

## Skills

Skills are reusable, user-authorable capability modules — a name + description + instructions (markdown). They're compatible in spirit with the [Agent Skills standard](https://agentskills.io), so you can adapt skills from Claude Code / Codex / pi.

Skills live in `~/.config/termux-ai/skills/`. A skill is either `name.md` (flat) or `name/SKILL.md` (a directory that may bundle helper scripts the AI can run).

```markdown
---
name: review
description: Review code for bugs, security, and style. Use for code reviews.
mode: once
---
You are a senior code reviewer. Report bugs, security issues, and style...
```

Two run modes (`mode:` in front-matter):
- **`once`** — `/skill review ./file.py` runs the skill instructions + your args as a single turn (args honor `@file` / `./path`).
- **`session`** — `/skill python` injects the skill into the system prompt for the rest of the session (a temporary expert mode); `/skill off` clears them.

```bash
/skill                     # list skills (* = active session skill)
/skill seed                # drop in the bundled examples (review, commit, python, reverse-engineer)
/skill review ./main.py    # run a once-skill
/skill python              # toggle a session-skill on/off
/skill show review         # view a skill
/skill new my-skill        # create + open in $EDITOR
/skill edit my-skill       # edit in $EDITOR
/skill off                 # clear all session skills
```

Bundled example skills ship in the repo's [`skills/`](skills/) directory for reference; `/skill seed` copies them into your skills dir.

**`reverse-engineer`** (session) — a PM/PO playbook: turn a code repo into **BRD → PRD → SAD → TSD → Epic/Task breakdown → User Manual/Guide** (six docs, each in `docs/`). The **03-SAD (Software Architecture Document)** carries **embedded Architecture Decision Records** (ADR-00n: Context · Decision · Consequences · Alternatives) plus Mermaid diagrams (system context, containers, components, sequence, deployment). The **04-TSD** is the detailed close-up (per-module breakdown, **full API/endpoints reference**, Mermaid ERD, business logic, security, config, build/test/deploy, observability). **All diagrams use Mermaid** (never ASCII/prose). It drives `clone_repo` / `fetch_url` / `search_files`, verifies every claim against the real code (file:line citations), and matches your language (Bahasa/English). Activate with `/skill reverse-engineer`, then e.g. *"analyze github.com/owner/repo, write the SAD first"*. (Best with a capable model; on 8 GB use `qwen2.5:3b`+, ideally cloud for the technical docs.)

**`data-engineer`** (session) — a Data Engineer / BI playbook. Reads a data report (`.xlsx`/`.xls`/`.csv`) **and** an objective doc (`.docx`/`.doc`/`.pdf`/`.txt`) via `read_file`, elaborates the real business need in `docs/analysis.md` (working **both** directions: report→dashboard and dashboard→report), then builds a self-contained single-page **HTML BI dashboard** (`dashboard.html`, inline CSS/JS/SVG, no CDN, opens offline). Activate `/skill data-engineer`, then *"read sales.xlsx and the brief.pdf, then build the dashboard"*.

**`cloud-arch`** (session) — Cloud Architecture + SRE. Ingests deployment signals from a codebase (`clone_repo` / `list_files recursive` / `search_files`) and/or product docs, infers the workload profile and NFRs, then produces `docs/cloud-architecture.md` (provider, compute/data/network/IAM, regions, topology, well-architected trade-offs), `docs/sre.md` (SLIs/SLOs, error budgets, HA/DR, observability, runbooks), `docs/security-compliance.md`, and starter `docs/iac/` (Terraform by default). Activate `/skill cloud-arch`, then *"design the infra for this repo"*.

**`finops`** (session) — cloud cost optimization. Reads IaC (Terraform/CDK/CloudFormation/Pulumi/Bicep), architecture docs, and billing CSV/XLSX exports to find waste (idle/oversized compute, wrong storage tier, egress, non-prod 24/7, missing commit discounts) and writes `docs/finops-assessment.md`, `docs/finops-recommendations.md` (prioritized: effort/impact/risk), and `docs/finops-governance.md` (tagging, budgets, unit-economics KPIs). Activate `/skill finops`, then *"audit the terraform in this folder for savings"*.

**`pentest`** (session) — authorized security assessment. Enumerates the attack surface of a codebase (`clone_repo` / recursive `list_files` / `search_files`) and/or infra/IaC, runs available scanners when present (npm/pip audit, semgrep, bandit, tfsec, checkov, gitleaks, trivy), and evaluates against **OWASP Top 10/ASVS, NIST CSF, CIS Controls**. Writes `docs/security-assessment.md` (exec summary + risk rating), `docs/vulnerabilities.md` (each finding: severity, exact file:line, framework reference, remediation), `docs/dependency-audit.md` (CVEs → fixed-in), `docs/infra-hardening.md`, and `docs/remediation-plan.md` (quick wins first). Authorized-scope only, fix-oriented, no weaponization. Activate `/skill pentest`, then *"security-review this repo"*.

> **Binary file reading**: `read_file` parses `.xlsx` (full row/column table, sparse-aware), `.docx`, `.pptx` natively (stdlib, no deps), and `.pdf` via `pdftotext` (install with `pkg install poppler`). Legacy `.xls`/`.doc` aren't supported — convert to `.xlsx`/`.csv`/`.docx`.

Skills compose with everything else: `/strategy on` + `/skill review`, or `/tools on` + `/skill commit`.

---

## File Attachments

Reference files or directories in your prompt and they are automatically included. Any of these path styles are detected:

```
Look at ./main.py and tell me what it does     # ./ relative path
Review ../sibling/folder for bugs              # ../ parent path
What's in ~/project/config.yaml?               # ~ home path
Check the source in @src/utils.py              # @ explicit reference
Summarize the code in ./src                    # a directory is scanned recursively
```

When you point at a **directory**, every source file under it (skipping `.git`, `node_modules`, `__pycache__`, `venv`, etc.) is read up to a bounded total and attached. References that don't exist on disk are left untouched.

**Supported file types** (for both attachment and directory scanning):

`.py`, `.js`, `.ts`, `.tsx`, `.jsx`, `.java`, `.c`, `.cpp`, `.h`, `.cs`, `.go`, `.rs`, `.rb`, `.php`, `.swift`, `.kt`, `.sh`, `.bash`, `.css`, `.scss`, `.html`, `.json`, `.md`, `.txt`, `.csv`, `.xml`, `.yaml`, `.yml`, `.toml`, `.ini`, `.cfg`, `.pdf`, `.docx`, `.pptx`, `.xlsx`

---

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/kabarbaik-xyz/termux-ai/main/uninstall.sh | bash
```

Or manually:

```bash
rm ~/.local/bin/ai
# Optionally: rm -rf ~/.config/termux-ai
```

---

## Requirements

- **Python 3.8+** (stdlib only — zero pip dependencies)
- **Termux** (recommended) or any Linux/macOS terminal
- `readline` — for command history with arrow keys (`pkg install readline` on Termux)
- `poppler` — optional, for PDF reading (`pkg install poppler` on Termux)

---

## Development

The CLI ships as a **single file** (`ai`) so installation and `/update` stay trivial — but the source is split into small modules under [`src/`](src/) and stitched together by [`build.py`](build.py). **Edit `src/`, never edit `ai` directly.**

```
src/
  _header.py     shebang, stdlib imports, __version__
  _constants.py  paths, colors, IS_TTY, est_tok, PRICING, parse_value...
  fileio.py      FileReader
  ui.py          MarkdownFormatter, Spinner
  termux_api.py  TermuxAPI
  server.py      ServerManager
  db.py          Database
  config.py      Config
  tools.py       Tools (+ Plan-mode read-only executor)
  backends.py    Backend, OpenAICompatible, AnthropicBackend, get_backend
  app.py         App (core: chat, streaming, dispatch)
  commands.py    App slash-command handlers (_cmd_*), continuing the class body
  cli.py         main() + __main__ guard
```

Fragments rely on **concatenation order**, not imports — `build.py` forbids cross-module `import`/`from .` statements and fails loudly if you add one. Module-level globals live in `_constants.py` so every later fragment can see them.

### Make a change & ship it

```bash
# 1. edit a module, e.g. src/tools.py
# 2. regenerate the single-file artifact
python3 build.py
# 3. verify
python3 tests/test_security.py
# 4. commit both the source and the regenerated artifact
git add src ai && git commit -m "fix: ..." && git push
```

Users running `/update` then receive the new single-file `ai` — their experience is unchanged.

### Debugging

Errors are normally shown as a one-line message. Set **`AI_DEBUG=1`** to print full tracebacks (useful when something crashes unexpectedly):

```bash
AI_DEBUG=1 ai
```

### Keep `ai` from going stale

Enable the pre-commit hook once:

```bash
git config core.hooksPath .githooks
```

Now any commit that touches `src/` rebuilds `ai` automatically and **refuses to commit** if the generated file isn't staged. GitHub Actions (`.github/workflows/ci.yml`) double-checks on push: it rebuilds, rejects a stale `ai`, and runs the test suite.

---

## License

MIT — see [LICENSE](LICENSE).
