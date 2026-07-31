# Termux AI CLI

A zero-dependency AI chat CLI for [Termux](https://termux.dev) on Android — and any terminal. Talks to OpenAI-compatible endpoints, Anthropic's Claude API natively, or runs fully offline with Ollama.

![version](https://img.shields.io/badge/version-6.2.0-green)
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
- **Loop detection** — automatically stops the AI if it repeats the same tool calls 3 times in a row
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
- **Loop detection** — if the AI repeats the same tool call 3 consecutive times, execution stops automatically
- **Iteration cap** — after every 10 tool-call iterations (counting actual tool calls), you're prompted to continue or stop; if you stop (or decline a batch), nothing is saved to history
- **Bounded context** — long tool outputs are truncated (~2000 chars) and older tool iterations are trimmed out in-loop, so requests stay within budget even on long multi-step sessions
- **Final answer only** — mid-loop narration streams live to the terminal, but only the final answer is saved to chat history

---

## Configuration

All settings live in `~/.config/termux-ai/config.json`. Key settings:

| Key | Default | Description |
|---|---|---|
| `backend` | `ollama` | Active backend profile name |
| `system_prompt` | _(see below)_ | System prompt for the AI |
| `system_instruction` | `""` | If set, overrides `system_prompt` |
| `temperature` | `0.7` | Sampling temperature |
| `max_tokens` | `4096` | Max response tokens (auto-reduced to 1024 for short non-code prompts — PLAN mode only) |
| `stream` | `true` | Stream responses |
| `show_tokens` | `true` | Show token count per reply |
| `tools_enabled` | `false` | BUILD mode on/off |
| `tts_replies` | `false` | Auto-speak all replies |
| `multi_line` | `false` | Multi-line input mode |
| `auto_compact` | `true` | Auto-summarize when chat exceeds ~3000 tokens |
| `auto_router` | `false` | Fallback to other backends on failure |
| `max_file_chars` | `12000` | Max chars when attaching files |
| `attach_files` | `true` | Auto-detect file references |

Change any setting from inside the CLI:

```
/config set temperature 0.9
/config set max_tokens 8192
/config set system_instruction "You are a Python expert"
```

---

## File Attachments

Reference files or directories in your prompt and they are automatically included:

```
Look at ./main.py and tell me what it does
Review this folder for bugs
What's in ~/project/config.yaml?
```

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

## License

MIT — see [LICENSE](LICENSE).
