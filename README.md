# Termux AI CLI

A zero-dependency AI chat CLI for [Termux](https://termux.dev) on Android. Talks to OpenAI-compatible endpoints or Anthropic's Claude API natively.

![version](https://img.shields.io/badge/version-6.0.0-green)
![python](https://img.shields.io/badge/python-3.8+-blue)
![dependencies](https://img.shields.io/badge/deps-zero-brightgreen)
![platform](https://img.shields.io/badge/platform-Android%20%7C%20Termux-orange)

## Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/kabarbaik-xyz/termux-ai/main/install.sh | bash
```

Then restart your terminal (or `source ~/.bashrc`) and run:

```bash
ai
```

## API Key Setup

After installing, launch the CLI with `ai` and configure your preferred backend.
Pick **one** of the options below:

### Option A — Ollama (Free, Local, No API Key)

Runs entirely on your phone. No internet needed after setup.

```bash
# In Termux:
pkg install ollama
ollama pull llama3.2      # or any other model
ollama serve &            # start the server
```

The `ai` CLI already defaults to Ollama at `localhost:11434`. Just launch and chat:

```bash
ai
```

### Option B — Anthropic Claude

1. Get an API key from **[console.anthropic.com](https://console.anthropic.com/)**
2. Launch the CLI and configure:

```
ai
/profile set anthropic.api_key sk-ant-api03-xxxxx
/backend anthropic
```

### Option C — OpenAI

1. Get an API key from **[platform.openai.com/api-keys](https://platform.openai.com/api-keys)**
2. Launch the CLI and configure:

```
ai
/profile add openai https://api.openai.com/v1 gpt-4o sk-xxxxx
/backend openai
```

### Option D — Groq (Free Tier, Ultra Fast)

1. Get an API key from **[console.groq.com/keys](https://console.groq.com/keys)**
2. Launch the CLI and configure:

```
ai
/profile add groq https://api.groq.com/openai/v1 llama-3.3-70b-versatile gsk_xxxxx
/backend groq
```

### Option E — OpenRouter (100+ Models)

1. Get an API key from **[openrouter.ai/keys](https://openrouter.ai/keys)**
2. Launch the CLI and configure:

```
ai
/profile add openrouter https://openrouter.ai/api/v1 anthropic/claude-3.5-sonnet sk-or-xxxxx
/backend openrouter
```

> **💡 Tip:** Your API key is stored locally in `~/.config/termux-ai/config.json`.
> It never leaves your device except in direct API calls to your chosen provider.

### Using Any OpenAI-Compatible API

The CLI supports **any** OpenAI-compatible endpoint. The general pattern is:

```
/profile add <name> <base_url> <model> <api_key>
/backend <name>
```

For example, LM Studio, vLLM, or any self-hosted endpoint — just point to its
base URL and you're good to go.

## Features

- 🔌 **Multiple backends** — Ollama, OpenAI, Claude, Groq, OpenRouter, or any OpenAI-compatible API
- 💾 **Chat history** — SQLite-backed conversation storage
- 📎 **File attachments** — Auto-detects files/folders mentioned in your message
- 🛠️ **Tool use** — AI can read/write files and run commands (build mode)
- 📝 **Markdown rendering** — Syntax-highlighted output with inline code support
- 🗣️ **Termux API** — TTS, clipboard, Android share integration
- 🔄 **Streaming responses** — Real-time output as the AI generates
- 📊 **Token counting** — Optional tiktoken support for accurate counts
- 🔒 **Plan/Build modes** — Safe read-only mode by default, opt-in for write access

## One-Shot Usage (No Interactive Mode)

```bash
# Quick question
ai "What is the capital of France?"

# Generate a shell command from natural language
ai -c "list all files larger than 10MB"

# JSON output for scripting
ai -j "explain recursion" | jq .
```

## Commands

| Command | Description |
|---------|-------------|
| `/new` | Start fresh conversation |
| `/history` | List past conversations |
| `/load <id>` | Load a conversation |
| `/backend <name>` | Switch backend |
| `/model <name>` | Change model |
| `/profile add <n> <url> <model> [key]` | Add a new backend profile |
| `/profile set <name>.api_key <key>` | Set or update API key |
| `/tools on\|off` | Toggle build mode (file write access) |
| `/system <prompt>` | Set system prompt |
| `/export [file]` | Export chat to markdown |
| `/help` | Show all commands |

## Manual Install (without installer)

```bash
# In Termux
pkg install python
mkdir -p ~/.local/bin
curl -fsSL https://raw.githubusercontent.com/kabarbaik-xyz/termux-ai/main/ai -o ~/.local/bin/ai
chmod +x ~/.local/bin/ai
export PATH="$HOME/.local/bin:$PATH"
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
```

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/kabarbaik-xyz/termux-ai/main/uninstall.sh | bash
```

Or if you have the repo cloned:

```bash
bash uninstall.sh
```

## Dependencies

**None.** Only Python 3.8+ stdlib is required.

Optional enhancements:

| Package | Install | Purpose |
|---------|---------|---------|
| `readline` | `pkg install readline` | Arrow-key command history |
| `tiktoken` | `pip install tiktoken` | Accurate token counting |
| `poppler` | `pkg install poppler` | PDF file reading |
| `termux-api` | `pkg install termux-api` | TTS, clipboard, Android share |

## License

MIT
