#!/usr/bin/env bash
# Termux AI CLI Installer — Termux (Android), Linux (Debian/Ubuntu/Fedora/Arch/...), macOS
# Usage: curl -fsSL https://raw.githubusercontent.com/kabarbaik-xyz/termux-ai/main/install.sh | bash
set -e

REPO="kabarbaik-xyz/termux-ai"
RAW_BASE="https://raw.githubusercontent.com/${REPO}/main"
INSTALL_DIR="${HOME}/.local/bin"
SCRIPT_PATH="${INSTALL_DIR}/ai"
VERSION="7.9.5"

echo "🔍 Termux AI Installer v${VERSION}"
echo ""

# ── Platform detection ─────────────────────────────────────────────────────────
case "$PREFIX" in
    *com.termux*) IS_TERMUX=1 ;;
    *)            IS_TERMUX=0 ;;
esac

PKG_MGR=""
if [ "$IS_TERMUX" = "1" ]; then
    PKG_MGR="pkg"
elif command -v apt-get >/dev/null 2>&1; then
    PKG_MGR="apt-get"
elif command -v dnf >/dev/null 2>&1; then
    PKG_MGR="dnf"
elif command -v pacman >/dev/null 2>&1; then
    PKG_MGR="pacman"
elif command -v zypper >/dev/null 2>&1; then
    PKG_MGR="zypper"
elif command -v apk >/dev/null 2>&1; then
    PKG_MGR="apk"
elif command -v brew >/dev/null 2>&1; then
    PKG_MGR="brew"
fi

# pkg_install <package>: install for real when possible (Termux user-space, or
# root), otherwise print the sudo/brew command the user can run. Never fails the
# script by itself — callers decide how fatal a miss is.
pkg_install() {
    local pkg="$1" rc=0
    local root=0
    [ "$(id -u)" = "0" ] && root=1
    case "$PKG_MGR" in
        pkg)     pkg update -y >/dev/null 2>&1 || true
                 pkg install -y "$pkg" || rc=1 ;;
        apt-get) if [ "$root" = "1" ]; then apt-get install -y "$pkg" || rc=1
                 else echo "   Run: sudo apt-get install -y ${pkg}"; rc=1; fi ;;
        dnf)     if [ "$root" = "1" ]; then dnf install -y "$pkg" || rc=1
                 else echo "   Run: sudo dnf install -y ${pkg}"; rc=1; fi ;;
        pacman)  if [ "$root" = "1" ]; then pacman -S --noconfirm "$pkg" || rc=1
                 else echo "   Run: sudo pacman -S ${pkg}"; rc=1; fi ;;
        zypper)  if [ "$root" = "1" ]; then zypper --non-interactive install "$pkg" || rc=1
                 else echo "   Run: sudo zypper install ${pkg}"; rc=1; fi ;;
        apk)     apk add "$pkg" || rc=1 ;;
        brew)    brew install "$pkg" || rc=1 ;;
        *)       echo "   Install ${pkg} with your system package manager"; rc=1 ;;
    esac
    return $rc
}

# ── Check Python (>= 3.8) ─────────────────────────────────────────────────────
echo "📦 Checking prerequisites..."
# Resolve a working Python even when it isn't on PATH (e.g. sudo/cron/container
# with a stripped PATH): probe `command -v` first, then well-known absolute
# locations, falling back to bare `python` (some systems only ship `python`).
resolve_python() {
    local c
    for c in python3 /usr/bin/python3 /usr/bin/python3.* python /usr/bin/python; do
        if command -v "$c" >/dev/null 2>&1 || [ -x "$c" ]; then
            printf '%s' "$c"; return 0
        fi
    done
    return 1
}

PY=""
if PY="$(resolve_python)" && [ -n "$PY" ]; then
    if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'; then
        PY_VER=$("$PY" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        echo "❌ termux-ai needs Python 3.8+; found ${PY_VER}. Please upgrade Python and re-run."
        exit 1
    fi
    PY_VER=$("$PY" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    echo "   ✓ Python ${PY_VER} found"
else
    echo "   Installing Python..."
    pkg_install python3 || pkg_install python || true
    PY="$(resolve_python)" || PY=""
    if [ -z "$PY" ]; then
        echo "❌ Python3 not found. termux-ai needs Python 3.8+."
        echo "   Install it (e.g. on Debian/Ubuntu):  sudo apt-get install -y python3"
        exit 1
    fi
    if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)'; then
        echo "❌ Installed Python is older than 3.8. Please upgrade Python and re-run."
        exit 1
    fi
    echo "   ✓ Python installed"
fi

# ── Check readline (for arrow-key history) ────────────────────────────────────
if ! python3 -c "import readline" 2>/dev/null; then
    echo "📦 Installing readline (for arrow-key history)..."
    if ! pkg_install readline; then
        echo "   ℹ  readline is missing (unusual on Linux/macOS). Install your distro's"
        echo "      readline library and the python3 module if you want arrow-key history."
    fi
fi

# ── Optional: check pdftotext ─────────────────────────────────────────────────
if ! command -v pdftotext >/dev/null 2>&1; then
    case "$PKG_MGR" in
        pkg)     HINT="pkg install poppler" ;;
        apt-get) HINT="sudo apt-get install -y poppler-utils" ;;
        dnf)     HINT="sudo dnf install -y poppler-utils" ;;
        pacman)  HINT="sudo pacman -S poppler" ;;
        zypper)  HINT="sudo zypper install poppler-tools" ;;
        apk)     HINT="apk add poppler-utils" ;;
        brew)    HINT="brew install poppler" ;;
        *)       HINT="install poppler-utils (pdftotext)" ;;
    esac
    echo "💡 Tip: Install poppler for PDF reading:  $HINT"
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

# ── Update PATH ───────────────────────────────────────────────────────────────
# Login shells source ~/.profile; interactive bash sources ~/.bashrc; interactive
# zsh sources ~/.zshrc. Cover all three so ~/.local/bin is always found.
# (POSIX `sh`: no arrays, so a whitespace-separated list is used.)
PATH_FILES="${HOME}/.profile ${HOME}/.bashrc"
if [ -n "$SHELL" ]; then
    case "$SHELL" in
        *zsh*) PATH_FILES="$PATH_FILES ${HOME}/.zshrc" ;;
    esac
fi

# shellcheck disable=SC2016  # sed regex is intentionally literal (no expansion)
escape_sed() { printf '%s' "$1" | sed 's/[][\.|$(){}?+*^]/\\&/g'; }

ensure_path_entry() {
    file="$1"
    [ -f "$file" ] || : > "$file"
    esc_dir=$(escape_sed "$INSTALL_DIR")
    # shellcheck disable=SC2016  # sed regex is intentionally literal (no expansion)
    esc_home=$(printf '%s' "$INSTALL_DIR" | sed "s|^$HOME|\$HOME|" | sed 's/[][\.|$(){}?+*^]/\\&/g')
    if grep -q "# Termux AI" "$file" 2>/dev/null; then
        sed -i '/# Termux AI/d' "$file"
        sed -i -e "\|$esc_dir|d" -e "\|$esc_home|d" "$file"
    fi
    # shellcheck disable=SC2016  # printf format keeps $PATH literal; appended later
    printf '\n# Termux AI\nexport PATH="%s:$PATH"\n' "$INSTALL_DIR" >> "$file"
    echo "   ✓ Added $INSTALL_DIR to PATH in $file"
}

if ! echo "$PATH" | grep -q "$INSTALL_DIR"; then
    for f in $PATH_FILES; do
        ensure_path_entry "$f"
    done
    export PATH="$INSTALL_DIR:$PATH"
fi

# ── Symlink for easy uninstall ───────────────────────────────────────────────
if [ ! -L "${INSTALL_DIR}/uninstall-ai" ]; then
    cat > "${INSTALL_DIR}/uninstall-ai" << 'WRAPPER'
#!/usr/bin/env bash
curl -fsSL https://raw.githubusercontent.com/kabarbaik-xyz/termux-ai/main/uninstall.sh | bash
WRAPPER
    chmod +x "${INSTALL_DIR}/uninstall-ai"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
if [ "$IS_TERMUX" = "1" ]; then
    OLLAMA_HINT="pkg install ollama"
else
    OLLAMA_HINT="curl -fsSL https://ollama.com/install.sh | sh"
fi

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
echo "       ${OLLAMA_HINT}"
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