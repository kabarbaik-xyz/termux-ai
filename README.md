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

Ollama is the **default** backend — no configuration needed. Manage the server from inside the CLI:

```
/server start ollama
/server stop
/server status
```

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
| `/server start\|stop\|status` | Manage local Ollama server |
| `/clear` | Clear the screen |
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
- **Auto-run for safe tools** — read-only tools (`read_file`, `list_files`, `search_files`) execute automatically without prompting
- **CWD sandbox** — `write_file` is restricted to the current working directory for safety
- **Reflect-on-failure** — when a tool action errors or is blocked, a system note asks the AI to state what it will do differently before the next step (it learns the rules from the tool description up front, so it rarely proposes a blocked command at all)
- **Failure guard** — after 3 consecutive failed action rounds the AI stops and explains (rather than thrashing); a hard cap of 25 iterations remains as a runaway backstop. Every 10 tool calls you're prompted to continue (skipped automatically in one-shot/piped mode)
- **Bounded context** — long tool outputs are truncated (~2000 chars) and older tool iterations are trimmed out in-loop, so requests stay within budget even on long multi-step sessions
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
/skill seed                # drop in the bundled examples (review, commit, python)
/skill review ./main.py    # run a once-skill
/skill python              # toggle a session-skill on/off
/skill show review         # view a skill
/skill new my-skill        # create + open in $EDITOR
/skill edit my-skill       # edit in $EDITOR
/skill off                 # clear all session skills
```

Bundled example skills ship in the repo's [`skills/`](skills/) directory for reference; `/skill seed` copies them into your skills dir.

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
