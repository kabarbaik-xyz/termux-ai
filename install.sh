#!/usr/bin/env bash
# Termux AI CLI Installer
# Usage: curl -fsSL https://raw.githubusercontent.com/kabarbaik-xyz/termux-ai/main/install.sh | bash
set -e

REPO="kabarbaik-xyz/termux-ai"
RAW_BASE="https://raw.githubusercontent.com/${REPO}/main"
INSTALL_DIR="${HOME}/.local/bin"
SCRIPT_PATH="${INSTALL_DIR}/ai"
VERSION="7.0.0"

echo "🔍 Termux AI Installer v${VERSION}"
echo ""

# ── Check Python ─────────────────────────────────────────────────────────────
echo "📦 Checking prerequisites..."
if ! command -v python3 &>/dev/null; then
    echo "   Installing Python..."
    if command -v pkg &>/dev/null; then
        pkg update -y && pkg install -y python
    elif command -v apt &>/dev/null; then
        apt update -y && apt install -y python3
    else
        echo "❌ Python3 not found. Please install Python 3.8+ manually."
        exit 1
    fi
    echo "   ✓ Python installed"
else
    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    echo "   ✓ Python ${PY_VER} found"
fi

# ── Check readline (optional, for arrow-key history) ──────────────────────────
if ! python3 -c "import readline" 2>/dev/null; then
    echo "📦 Installing readline (for arrow-key history)..."
    if command -v pkg &>/dev/null; then
        pkg install -y readline 2>/dev/null || true
    fi
fi

# ── Optional: check pdftotext ─────────────────────────────────────────────────
if ! command -v pdftotext &>/dev/null; then
    echo "💡 Tip: Install poppler for PDF reading:  pkg install poppler"
fi

# ── Create install directory ──────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR"

# ── Backup existing install ───────────────────────────────────────────────────
if [ -f "$SCRIPT_PATH" ]; then
    echo "📦 Backing up existing install..."
    cp "$SCRIPT_PATH" "${SCRIPT_PATH}.bak"
    echo "   ✓ Backup saved to ${SCRIPT_PATH}.bak"
fi

# ── Download ──────────────────────────────────────────────────────────────────
echo "📥 Downloading termux-ai v${VERSION}..."
if ! curl -fsSL "${RAW_BASE}/ai" -o "$SCRIPT_PATH"; then
    echo "❌ Download failed. Check your internet connection."
    rm -f "$SCRIPT_PATH"  # clean up partial download
    exit 1
fi
chmod +x "$SCRIPT_PATH"
echo "   ✓ Installed to ${SCRIPT_PATH}"

# ── Update PATH in .bashrc ───────────────────────────────────────────────────
if ! echo "$PATH" | grep -q "$INSTALL_DIR"; then
    # Remove any old Termux AI PATH entries to avoid duplicates
    if grep -q "# Termux AI" ~/.bashrc 2>/dev/null; then
        sed -i '/# Termux AI/d' ~/.bashrc
        ESC_DIR=$(printf '%s' "$INSTALL_DIR" | sed 's/[][\.|$(){}?+*^]/\\&/g')
        ESC_HOME_DIR=$(printf '%s' "${INSTALL_DIR/#$HOME/\$HOME}" | sed 's/[][\.|$(){}?+*^]/\\&/g')
        sed -i -e "\|$ESC_DIR|d" -e "\|$ESC_HOME_DIR|d" ~/.bashrc
    fi

    echo "" >> ~/.bashrc
    echo '# Termux AI' >> ~/.bashrc
    echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> ~/.bashrc
    export PATH="$INSTALL_DIR:$PATH"
    echo "📝 Added $INSTALL_DIR to PATH in ~/.bashrc"
fi

# ── Symlink for easy uninstall ───────────────────────────────────────────────
if [ ! -L "${INSTALL_DIR}/uninstall-ai" ]; then
    # Create a tiny wrapper so users can also run: uninstall-ai
    cat > "${INSTALL_DIR}/uninstall-ai" << 'WRAPPER'
#!/usr/bin/env bash
curl -fsSL https://raw.githubusercontent.com/kabarbaik-xyz/termux-ai/main/uninstall.sh | bash
WRAPPER
    chmod +x "${INSTALL_DIR}/uninstall-ai"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "✅ Termux AI v${VERSION} installed successfully!"
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
echo "  3. SET UP YOUR BACKEND (choose one):"
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
echo "  🗑  Uninstall: uninstall-ai  (or: curl -fsSL ${RAW_BASE}/uninstall.sh | bash)"
echo ""
