# Termux AI CLI

A zero-dependency AI chat CLI for [Termux](https://termux.dev) on Android — and any terminal. Talks to OpenAI-compatible endpoints, Anthropic's Claude API natively, or runs fully offline with Ollama.

![version](https://img.shields.io/badge/version-7.5.0-green)
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

Install Ollama for your platform:

```bash
# Termux (Android)
pkg install ollama

# Linux (Debian/Ubuntu/Fedora/Arch...) — official installer
curl -fsSL https://ollama.com/install.sh | sh

# macOS
brew install ollama
```

Then pull a model and start the server:

```bash
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

> **Reasoning models (qwen3, deepseek-r1, qwq, ...) are slow by default** — they
> ship with thinking/reasoning mode ON, which can take **several minutes** to
> answer a trivial question on phone CPU. termux-ai automatically detects any
> local Ollama model that reports a `thinking` capability and routes it through
> Ollama's native `/api/chat` endpoint with `think:false` (config
> `ollama_no_think`, on by default) — this cuts a trivial qwen3 query from
> **~250s to ~10s**. The OpenAI-compatible `/v1` endpoint silently ignores
> `think`, so this native path is required to actually disable thinking.
> Detection is per-model and authoritative (via `/api/show`), so it works for
> qwen3, qwq, and any future thinking-capable model without code changes.
>
> **Note on deepseek-r1 / phi-reasoning:** these emit reasoning as `<think>`
> tags *inside the content stream* rather than via Ollama's `think` protocol, so
> thinking often can't be disabled server-side — they're inherently slower. For
> an 8 GB phone prefer a non-reasoning model (`qwen2.5:3b`, `llama3.2:3b`) or
> `qwen3` (where thinking IS controllable) for interactive use.
>
> termux-ai strips `<think>...</think>` blocks from the streamed output
> automatically, so reasoning models don't dump their raw chain-of-thought onto
> your screen. In BUILD mode the reasoning is shown dim (as a `thinking` event)
> so you can still follow along; in plain chat it's hidden for a clean answer.
>
> **Pick a model with `/models`.** It lists every pulled Ollama model with its
> file size, capabilities (`reasoning` / `tools`), marks the active one, and
> reads free RAM to suggest an OOM-safe `num_ctx`:
> ```
> $ ai -c "/models"
> Local Ollama models (1):
>   qwen3:1.7b                   1.4 GB  [reasoning, tools] ← active
> Free RAM: 3.5 GB  |  headroom after model load: ~1.6 GB
> Suggested num_ctx: 4096  (current: default)
>   Set with: /config set num_ctx 4096
> ```
>
> **Why local models feel "stuck".** A small model on phone CPU generates at
> only ~6 tok/s, and every request re-evaluates the tool list (~700 tokens)
> because Ollama's prompt cache doesn't reliably hold it. termux-ai applies
> three fixes automatically for local Ollama: (1) `keep_alive: 30m` keeps the
> model resident so a slow tool mid-skill doesn't force a ~30s reload; (2) a
> **compact tool schema** (terse descriptions, no per-param docs) trims ~250
> tokens off every request; (3) `/models` warns when `max_tokens` is high (8192
> tokens × 6 tok/s ≈ 20 min worst case — lower it with `/config set max_tokens
> 2048`). Even so, expect the *first* reply of a session to take ~20s (cold
> model load + schema eval); later replies are faster. Cloud backends are
> unaffected (full schemas, no keep_alive needed).

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

### One-shot with skills + overrides

Flags can be combined to run a task with a skill, force Build mode, and control
 tool-call display — all per-run (your config is not changed; use `/config set`
to persist):

```bash
ai "build a simple website" --skill fullstack --tools on --process off
```

| Flag | Values | Effect |
|---|---|---|
| `-s, --skill` | `NAME[,NAME...]` | Activate comma-separated skill(s) for this run (e.g. `--skill fullstack,pentest`). A missing skill warns and asks to continue without it (non-interactive runs warn and continue). |
| `--tools` | `on` / `off` | Force **Build** (write allowed) or **Plan** (read-only) mode for this run — needed for one-shot tasks that create files, since the config default may be Plan mode. |
| `--process` | `on` / `off` / `auto` | Override tool-call display for this run: `on`=compact (one line/step), `off`=full live output, `auto`=inline-then-compact. |

These compose with everything else: `ai -m llama3.2 "..." --skill python --tools on`. In the interactive REPL the same controls are `/skill`, `/tools`, `/process`. 

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
| `/process [on\|off\|auto]` | Show/compact tool-call output: `on` = clean summary only, `off` = full tool calls live, `auto` = smart (compact when 4+ steps); no args shows last turn's step log |
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
- `/backup` — atomic snapshot of the full history DB into `~/.config/termux-ai/backup-<ts>.db` (`VACUUM INTO`; safe while running). Keeps the last 5. Restore by copying a snapshot over `ai_history.db` while `ai` is closed
- `/rename auto` — AI-generated short title for the current session (falls back to the smart heuristic offline)
- `/prune [days]` — delete old unpinned chats (or set `prune_days` in config to auto-prune on startup; 0 = off)
- `/import <file>` — restore a session from an `/export` backup
- `ai -C` / `ai --continue` / `ai --new` / `ai -l <id>` — same, at launch (`-C` short alias)
- **Named sessions** — `ai -S <name>` creates-or-resumes a tagged session (e.g. `ai -S webproject`): first run starts a new session tagged `webproject`, the next `ai -S webproject` resumes exactly it. Tag the current session with `/session <name>` (or `/session off` to clear); `/sessions` shows `#tags`. `/load <tag>` loads by tag first.
- **Project-scoped resume** — `--continue`/auto-resume prefers the last session **started in the current directory**, so resuming in repo A never grabs repo B's chat.
- **Session working set** — each session remembers the directory it started in, the Build/Plan mode, and the active skills; resuming re-applies them (`[Session tools mode restored: Build]`, `[Session skills restored: …]`). If you resume from a different directory, you get a one-line `cd <path>` hint instead of wrong-tree answers.
- `ai <prompt>` one-shot calls are unaffected (never auto-resume)

### Resilience & context

Backend hiccups (connection drops, timeouts, 429/5xx) are retried automatically
with exponential backoff (`retries` default 3, `retry_delay` default 1s in
config) — but only when nothing has been printed yet, so you never see
duplicated output. Retry happens in **one layer** (the old code retried inside
the HTTP call *and* again around the stream, compounding into up to 9 attempts
on a persistent 429/503 — which made cloud backends slow and spammy); now it's
exactly `retries` attempts total. **`Retry-After` is honored** on 429s, so a
rate-limited gateway gets the wait it asked for instead of being hammered. If
the stream drops mid-reply, nothing is saved and the app tells you to run
`/retry`, which regenerates with the same context.

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

### Empty / flaky responses

A backend that returns an **empty body** or drops before sending real content
(whitespace-only stream) is treated as a transient failure and retried with
backoff — it no longer fails silently ("AI went blank") or errors on output
that was never really shown. Only a drop **after real content** streams stops
the retry (to avoid duplicate output) and triggers the interrupt-continuation
flow above.

### Read loops that never progress

`read_file` now supports **line offsets** (`start`/`end`, 1-based): a large
file is read in pages with a `[lines N–M of T]` header and a
`read_file(..., start=M+1)` hint, so a model can walk a file top-to-bottom
instead of re-reading the same head. Previously, offset arguments were
silently ignored and every call returned the identical truncated head — the
classic "reads the same file 40 times" spiral. As a second backstop, the tool
loop now counts identical tool calls and **stops after `repeat_limit`
(default 3) unchanged repeats** with a clear message (instead of burning all
50 iterations), configurable via `repeat_limit`.

### Gather-then-execute

The loop now steers agentic turns into two phases instead of letting the model
dribble reads across every iteration: the system prompt recommends batching
all context reads (read_file / list_files / search_files) into the first one
or two responses, then executing (config `gather_first`, default on). If the
model ignores that and keeps reading for `gather_threshold` (default 3)
consecutive iterations, the harness injects a nudge (shown as a notice and
sent to the model) telling it to batch the remaining reads into one response
and move to execution. The streak resets the moment it writes or runs, so a
later re-read spiral gets nudged again.

A separate **re-read guard** (`re_read_limit`, default 3) stops the worst
case — a model that keeps reading *overlapping* ranges of the same file (the
identical-call guard can't see these because the args differ). The harness
tracks which line ranges of each file it has already shown this turn and,
when the same file's covered ground is re-requested 3 times, stops with
"you've re-read {file} N times over ground already shown".

### Compact output (folding)

Long **lists** and **tables** in a reply are folded inline (first `fold_head` items, default 8, then a dim `… N more — /expand to view`) so a big list doesn't flood a small screen. The full reply is always retained — run `/expand` (alias `/last`) to page through the whole thing in `less`. Folding is display-only (the saved reply is complete) and toggleable: `/fold off`, or set `fold_long_blocks`/`fold_head` in config. Paragraphs and code blocks are never folded.

**Tool-call chatter** (the `[Tool 1/2] read_file({...})` lines + raw results) can be collapsed the same way: in compact mode each step prints as a one-line `⚙️ read dashboard.html ✓` and tool results are suppressed, leaving a clean `⚙️ N steps — /process for details` footer. Run `/process` to page through the full step-by-step log (tool, args, result, ✓/✗ status), or `/process on|off|auto` to choose: `on` (default) = always compact, `off` = full live tool output (the original behavior), `auto` = inline when the task is simple, compact once it grows past `compact_threshold` steps (default 4). Errors always break through even in compact mode. Config: `compact_process`, `compact_threshold` (existing installs saved at the old default `auto` are migrated to `on` once).
| `/help` | Show all commands |
| `/exit` | Quit (Ctrl-C also works) |

---

## Tool Modes

### PLAN mode (default)

The AI can **read** files, list directories, search code, and run safe inspection commands (`ls`, `cat`, `grep`, `head`, etc.). It **cannot** write, modify, or delete anything.

> **Local-model responsiveness gate** (small non-thinking local models only): casual chat gets **no tools** (a small model loops file-tools on "hi" for ~200s otherwise), knowledge questions get **web-only** tools, tasks get the full read-only set — and a mid-task "ok"/"lanjutkan" never drops the toolset. Understands English **and Indonesian** phrasing ("tolong buatkan website" is a task). Cloud backends are never gated: full tools in Build mode, read-only in Plan mode, every turn.

Plan-mode commands run **without a shell** against a **read-only allowlist** (e.g. `ls`, `cat`, `grep`, `head`, `tail`, `find`, `wc`, `sort`, `git status/diff/log`, …). Pipes work (`grep foo f | wc -l`), but because there is no shell, redirects (`>`, `>>`), `&&`/`;`, command substitution (`$(…)`, backticks), newlines, and every non-allowlisted binary (including all interpreters) are inert or rejected. This is the complete security boundary for Plan mode.

In PLAN mode, the following command patterns are **automatically blocked** to prevent accidental modification:

`rm`, `mv`, `cp`, `touch`, `mkdir`, `chmod`, `chown`, `dd`, `tee`, `ln`, `rmdir`, `truncate`, `chattr`, `unlink`, `install`, `pip install`, `apt`, `pkg`, `npm`, `yarn`, `sed -i`, `awk -i`, `perl -i`, `find -delete` / `-exec` / `-ok`, `git rm` / `git clean` / `git reset --hard`, output redirection (`>`, `>>`), and interpreter execution (`python3 -c` / `-m`, `bash -c`, `sh -c`, `node`, `perl`, `ruby`, `php`, etc.).

### BUILD mode

```
/tools on
```

The AI can also **write files** and **run any shell command**. Key behaviors:

- **Batch confirmation** — all tool calls in one response are shown together; you approve or decline the entire batch with a single y/N
- **Verified execution** — the loop keeps a **mutation ledger** (ground truth of what actually changed on disk, from the executor — never the model's narration). After each Build turn you get a green `✏️  changed: app.py, tests/x.py` footer listing the real files. A **done-claim guard** catches the "said fixed, but wasn't": an answer claiming completion (EN+ID) with zero successful mutations triggers ONE corrective retry, and a repeated empty claim prints `⚠ no files were actually changed this turn`. **Auto-verify** (config `auto_verify`, default on) runs the project's tests once after edits and shows the model the result before it can claim done. A **blank-out guard** refuses empty writes over non-empty files unless `allow_empty=true`
- **Smart paste (`/paste`)** — recognizes what you pasted before sending: stack traces (shows referenced files + `[a]`ttaches bounded source around the failing frames), diffs/patches, GitHub issue/PR/repo links (`[f]`etches the page into the message), JSON, YAML, markdown, or code — with a line/token count header, first-lines preview, `e` to edit in $EDITOR first, Esc to cancel, Enter to send raw. `/paste --raw` skips the preview and sends verbatim (non-interactive runs always do)
- **Auto-run for safe tools** — read-only tools (`read_file`, `list_files`, `search_files`, `fetch_url`) execute automatically without prompting
- **Parallel batch execution** — batched read-only calls (read/list/search/fetch/search-web/weather/graphify) run **concurrently** in a small thread pool (`parallel_tools`, default on; `parallel_workers`, default 4), so a batch of reads takes as long as the slowest call instead of their sum. Mutating calls (`write_file`, `run_command`, `clone_repo`) stay sequential and run **after** the reads, preserving the old ordered semantics; results are always returned to the model in the original call order
- **Project memory (CONTEXT.md)** — if the cwd has a `CONTEXT.md` (or `.ai/context.md`), it's attached to every message as project context (stack, structure, conventions, gotchas — capped at `max_context_md`, default 12 KB) so repeat sessions don't re-discover the project. The AI is instructed to KEEP it current (tool rule 7). Manage with `/context` (show / `init` / `edit` / `refresh` / `off`)
- **Web research** — `fetch_url` does an HTTP GET and returns the page as readable text (HTML stripped). The AI uses it to read/research websites directly. It refuses private/local addresses (127.0.0.1, localhost, 10.x …) as an SSRF guard unless `AI_FETCH_ALLOW_PRIVATE=1` is set; ~500 KB cap, 10s timeout. Web tools (`fetch_url`, `web_search`, `weather`) share a short-TTL cache (`AI_WEB_CACHE_TTL` seconds, default 60, `0` disables) so repeated lookups in a turn don't re-fetch.
- **Web search** — keyless, three-source chain: Bing HTML → DuckDuckGo HTML → Wikipedia API. Each parser is pinned by frozen fixtures in CI, so a provider markup change fails loudly instead of silently degrading. `weather` is Open-Meteo (no key).
- **GitHub repos** — for `api.github.com` calls, `fetch_url` auto-attaches `GITHUB_TOKEN`/`GH_TOKEN` (lifts the rate limit from 60→5000/hr). To **analyze a repo locally**, the AI uses `clone_repo <https-url>` (Build mode): it shallow-clones (`--depth 1`) into an isolated temp dir and returns the path, after which `read_file`/`search_files`/`list_files` work on it. HTTPS-only (blocks ssh/git@/file). Great for "summarize this repo", "find the bug in …", or "clone it and run the tests". Best with a capable model (`qwen2.5:3b`+ or cloud); a 0.5b can't manage multi-step repo tasks.
- **Structured search (`search_files`)** — regex mode, `ignore_case`, `context` lines, `glob` file filter (`*.py`), `max_results` cap; results grouped per file with match counts and a shown/total tally
- **`test` tool** — runs the project's suite with the runner auto-detected from its manifest (pytest / npm test / cargo / go / make / composer); returns `total/passed/failed` counts plus the failing test names and first error lines, so "run tests → fix failures" loops are one call per round
- **`project_info` tool** — one-shot project snapshot: languages, test runner, lint/format config, entry points, file counts, recent commits. The model calls it first in an unfamiliar directory instead of probing file by file
- **CWD sandbox** — `write_file` and `edit_file` are restricted to the current working directory for safety
- **Surgical edits (`edit_file`)** — replace an exact substring instead of rewriting whole files: far cheaper (no 300-line regen on local models) and safer. `find` must match exactly once (or `replace_all`); a miss returns a helpful "re-read and copy exactly" error, ambiguity reports the match count. Build mode only, cwd-sandboxed like `write_file`
- **Git tool** — `git` with actions: `status` / `diff` / `log` / `show` run read-only in ANY mode (auto-approved, no shell overhead); `stage` / `commit` / `unstage` / `checkout_file` require Build mode + the normal approval prompt. Makes edit→verify→commit loops natural instead of shell round-trips
- **Chunked writes** — `write_file` supports `append=true` so large files (e.g. a full HTML dashboard) can be built in sections. If a tool-call response is **truncated by the output token limit** (OpenAI `finish_reason=length` / Anthropic `stop_reason=max_tokens`), the AI is told it was cut off and to split the work with `write_file` + `append` — instead of failing silently with empty arguments
- **Long commands** — `run_command` takes an optional `timeout` (seconds, max 600; default 30). The AI sets it higher for slow commands (`npm install`, builds, test suites) so they finish in **one call** instead of backgrounding and polling with `sleep` (each poll was a full agentic iteration — a 5-min install used to burn the whole step budget). On timeout it kills the process group **gracefully** (SIGTERM, then SIGKILL) so a hard kill mid-write can't corrupt state (e.g. a half-installed `node_modules`).
- **Reflect-on-failure** — when a tool action errors or is blocked, a system note asks the AI to state what it will do differently before the next step (it learns the rules from the tool description up front, so it rarely proposes a blocked command at all)
- **Smooth loop status (pi-style)** — routine events print as dim one-liners, never alarms: `⏳ context compacted · 12 old results → summary`, `↻ retrying with tools available`, `↻ retry 1/3 in 5s · HTTP 429`, `↻ connection dropped after 12 tool steps · resuming in 2s (Ctrl+C to skip)`. Warnings are one yellow line (`⚠ output hit the token limit · asking the model to split the write`). Fatal stops are **state + options, two lines max**: `✖ iteration limit reached (50)` / `  /retry to continue · /config set max_iterations N to raise the ceiling`. Loop coaching aimed at the *model* (batch your reads, answer now) stays in the model's context — you only see `↻ coaching: batch the reads, then act`
- **Keep-going long tasks** — `continue_mode` (default **`auto`**, pi-style): at each checkpoint the loop extends the iteration ceiling itself and keeps working, no prompt; safety stays with the stuck-detector (5 no-progress rounds), the 3-consecutive-failure guard, and the repeat limit, and Ctrl+C still interrupts (checkpoint kept → `/retry`). `prompt` mode asks every `continue_every` calls: `⏱ long task · 12 iterations, 34 tool calls` with `[y] keep going · [a] don't ask again · [n] stop`. Unattended (piped/one-shot) runs stay hard-capped by `max_iterations`. For a single *slow* command, `run_command` takes a `timeout` (max 600s) so it finishes in one step instead of polling
- **Self-healing gate** — if the local chat gate misreads a task as casual chat (no tools offered) but the model's answer says it needed tools ("maaf, saya tidak bisa mengakses file"), the loop re-offers the toolset **once** and lets it retry — the task completes without the user rephrasing. Never loops: a second tool-less answer stands.
- **Instant history search** — `/search` uses an **FTS5** full-text index over messages (instant MATCH, ~0.2 ms on hundreds of messages) with an automatic fallback to LIKE scanning on builds without FTS5.
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
| `ollama_no_think` | `true` | For a LOCAL **reasoning model** on Ollama (any model that reports a `thinking` capability — qwen3, qwq, deepseek-r1 if Ollama marks it, etc.): route through the native `/api/chat` endpoint, which is the only way to control thinking (the `/v1` endpoint ignores `think`). Default `true` sends `think:false` — reasoning models otherwise burn minutes of phone CPU before answering (measured **247s → 10s** on qwen3). Set `false` to actually **think**: `think:true` with the reasoning shown live (dim) and passed back on tool turns. Auto-detected per-model via Ollama's `/api/show` capabilities; no effect on cloud backends or non-thinking models. |
| `ollama_keep_alive` | `30m` | Keep the model resident between requests so a slow tool mid-skill (graphify/fetch can take minutes) doesn't force a ~30s cold reload on the next step — the #1 cause of "stuck in thinking". Ollama's default ~5-min idle unload is too short for multi-step skills. Set `0` to disable. |
| `ollama_max_tokens` | `0` | Ollama-only max-generation cap (0 = use `max_tokens`). Set low (e.g. `2048`) for a slow phone CPU **without** lowering cloud's `max_tokens` — `max_tokens` is global and would otherwise cap your cloud replies too. |
| `num_ctx` | `0` | Optional Ollama context-length override (0 = Ollama default). Lower this on memory-constrained devices, e.g. `4096`. |
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

When your message contains a distinctive trigger word ("playwright", "pentest", "finops" ...), a one-line **tip** suggests the matching skill — run `/skill <name>` to activate it for that task (`skill_suggest` in config to disable).

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

**`brainstorm`** (session) — a two-phase thinking partner: diverges on ideas/angles/risks, then converges into a **compressed blueprint** (`docs/brainstorm-blueprint.md`, ~4 KB) carrying the *decisions*, not the prose. Hand the blueprint to a bigger/cloud model to expand — decisions cost tokens locally, prose is written once by the cloud model. Activate `/skill brainstorm`, then e.g. *"ideas for a habit tracker"*; then `/backend opencode` + the hand-off prompt from the blueprint.

### Sample output documents

The `docs/` folder contains **real outputs** produced by AI skills running on termux-ai's own codebase — these demonstrate what each skill produces:

| Document | Skill | Description |
|----------|-------|-------------|
| [`docs/code-graph.md`](docs/code-graph.md) | `/graphify` | Code structure map: definitions, dependency graph |
| [`docs/security-assessment.md`](docs/security-assessment.md) | `pentest` | Executive summary, risk rating, scope, methodology |
| [`docs/vulnerabilities.md`](docs/vulnerabilities.md) | `pentest` | 14 findings (V-01–V-14); **5 remediated** ✅ |
| [`docs/remediation-plan.md`](docs/remediation-plan.md) | `pentest` | Prioritized roadmap (quick wins → strategic) |
| [`docs/dependency-audit.md`](docs/dependency-audit.md) | `pentest` | Third-party package CVE analysis |
| [`docs/infra-hardening.md`](docs/infra-hardening.md) | `pentest` | IaC/config misconfigs with CIS/CSF references |
| [`docs/02-PRD.md`](docs/02-PRD.md) | `reverse-engineer` | Product requirements document |
| [`docs/03-SAD.md`](docs/03-SAD.md) | `reverse-engineer` | Software architecture document with ADRs |
| [`docs/04-TSD.md`](docs/04-TSD.md) | `reverse-engineer` | Technical specification (API reference, data model) |
| [`docs/MANUAL_TEST_CASES.md`](docs/MANUAL_TEST_CASES.md) | `qa` | Risk heat map, step-by-step test cases, checklists |

All skills call `graphify` first to map the codebase structure before deep analysis.

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
- `readline` — for command history with arrow keys (`pkg install readline` on Termux; built in on most Linux/macOS Python builds)
- `poppler` — optional, for PDF reading (`pkg install poppler` on Termux, `apt-get install poppler-utils` on Debian/Ubuntu; the installer prints the right command)

The installer (`install.sh`) auto-detects your platform and prints the correct
package commands; `ai` itself stays a single portable file. On Linux, `~/.local/bin`
is added to `~/.profile`, `~/.bashrc`, and `~/.zshrc` (whichever exists) so `ai`
is on your PATH in login, interactive, and zsh shells.

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
