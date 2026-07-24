#!/usr/bin/env bash
# Termux AI CLI Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/kabarbaik-xyz/termux-ai/main/install.sh | bash
set -e

REPO="kabarbaik-xyz/termux-ai"
RAW_BASE="https://raw.githubusercontent.com/${REPO}/main"
INSTALL_DIR="${HOME}/.local/bin"
SCRIPT_PATH="${INSTALL_DIR}/ai"

echo "🔍 Checking prerequisites..."

# Check if running in Termux
if [[ ! "$PREFIX" == *"/com.termux"* ]]; then
    echo "⚠  This tool is designed for Termux. Proceeding anyway..."
fi

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "📦 Installing Python..."
    pkg update -y && pkg install -y python
fi

# Create install directory
mkdir -p "$INSTALL_DIR"

echo "📥 Downloading termux-ai..."
curl -fsSL "${RAW_BASE}/ai" -o "$SCRIPT_PATH"
chmod +x "$SCRIPT_PATH"

# Ensure ~/.local/bin is in PATH
if ! echo "$PATH" | grep -q "$INSTALL_DIR"; then
    echo "" >> ~/.bashrc
    echo '# Termux AI' >> ~/.bashrc
    echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> ~/.bashrc
    export PATH="$INSTALL_DIR:$PATH"
    echo "📝 Added $INSTALL_DIR to PATH in ~/.bashrc"
fi

echo ""
echo "✅ Termux AI installed successfully!"
echo ""
echo "╭─────────────────────────────────────────────────────╮"
echo "│                  🚀 NEXT STEPS                      │"
echo "╰─────────────────────────────────────────────────────╯"
echo ""
echo "  1. RESTART your terminal (or run):  source ~/.bashrc"
echo ""
echo "  2. LAUNCH the CLI:"
echo ""
echo "       ai"
echo ""
echo "  3. SET UP YOUR API KEY (choose one):"
echo ""
echo "     ── Option A: Ollama (free, local, no key needed) ──"
echo ""
echo "       pkg install ollama"
echo "       ollama pull llama3.2"
echo "       ollama serve &"
echo ""
echo "       Then in the ai CLI, it's already configured by default."
echo ""
echo "     ── Option B: Anthropic Claude ──"
echo ""
echo "       Get an API key from: https://console.anthropic.com/"
echo ""
echo "       Then in the ai CLI:"
echo "         /profile set anthropic.api_key sk-ant-api03-xxxxx"
echo "         /backend anthropic"
echo ""
echo "     ── Option C: OpenAI ──"
echo ""
echo "       Get an API key from: https://platform.openai.com/api-keys"
echo ""
echo "       Then in the ai CLI:"
echo "         /profile add openai https://api.openai.com/v1 gpt-4o sk-xxxxx"
echo "         /backend openai"
echo ""
echo "     ── Option D: Groq (free tier, fast) ──"
echo ""
echo "       Get an API key from: https://console.groq.com/keys"
echo ""
echo "       Then in the ai CLI:"
echo "         /profile add groq https://api.groq.com/openai/v1 llama-3.3-70b-versatile gsk_xxxxx"
echo "         /backend groq"
echo ""
echo "     ── Option E: OpenRouter (100+ models) ──"
echo ""
echo "       Get an API key from: https://openrouter.ai/keys"
echo ""
echo "       Then in the ai CLI:"
echo "         /profile add openrouter https://openrouter.ai/api/v1 anthropic/claude-3.5-sonnet sk-or-xxxxx"
echo "         /backend openrouter"
echo ""
echo "  4. START CHATTING — just type your question!"
echo ""
echo "  📖 Type /help inside the CLI for all commands"
echo "  🗑  ️Uninstall: curl -fsSL ${RAW_BASE}/uninstall.sh | bash"
echo ""
