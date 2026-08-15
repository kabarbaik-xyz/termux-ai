#!/usr/bin/env bash
# Termux AI CLI Uninstaller
# Usage: curl -fsSL https://raw.githubusercontent.com/kabarbaik-xyz/termux-ai/main/uninstall.sh | bash
set -e

# POSIX `sh` (dash) has no read -p / read -n; emulate a prompt that reads one line.
prompt() {
    printf '%s' "$1"
    IFS= read -r REPLY || REPLY=""
}

INSTALL_DIR="${HOME}/.local/bin"
SCRIPT_PATH="${INSTALL_DIR}/ai"
BACKUP_PATH="${SCRIPT_PATH}.bak"
SYMLINK_PATH="${INSTALL_DIR}/uninstall-ai"
CONFIG_DIR="${HOME}/.config/termux-ai"
PID_FILE="${CONFIG_DIR}/server.pid"

echo "🗑  Uninstalling Termux AI..."
echo ""

# ── Kill managed Ollama server if running ─────────────────────────────────────
if [ -f "$PID_FILE" ]; then
    PID_CONTENT=$(cat "$PID_FILE" 2>/dev/null || true)
    PID=$(echo "$PID_CONTENT" | cut -d',' -f1)
    ENGINE=$(echo "$PID_CONTENT" | cut -d',' -f2)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        prompt "   Stop running ${ENGINE:-ollama} server (PID: $PID)? [Y/n] "
        case "$REPLY" in
            [Nn]) : ;;
            *) kill -- -"$PID" 2>/dev/null || kill "$PID" 2>/dev/null || true
               echo "   ✓ Stopped ${ENGINE:-ollama} server" ;;
        esac
    fi
fi

# ── Remove the script ─────────────────────────────────────────────────────────
if [ -f "$SCRIPT_PATH" ]; then
    rm -f "$SCRIPT_PATH"
    echo "   ✓ Removed $SCRIPT_PATH"
else
    echo "   ℹ  $SCRIPT_PATH not found (already removed)"
fi

# ── Remove backup ─────────────────────────────────────────────────────────────
if [ -f "$BACKUP_PATH" ]; then
    rm -f "$BACKUP_PATH"
    echo "   ✓ Removed backup $BACKUP_PATH"
fi

# ── Remove uninstall symlink ──────────────────────────────────────────────────
if [ -f "$SYMLINK_PATH" ]; then
    rm -f "$SYMLINK_PATH"
    echo "   ✓ Removed $SYMLINK_PATH"
fi

# ── Remove config & history ──────────────────────────────────────────────────
if [ -d "$CONFIG_DIR" ]; then
    prompt "   Remove config & chat history ($CONFIG_DIR)? [y/N] "
    case "$REPLY" in
        [Yy]) rm -rf "$CONFIG_DIR"
              echo "   ✓ Removed $CONFIG_DIR" ;;
        *) echo "   ℹ  Kept $CONFIG_DIR" ;;
    esac
fi

# ── Clean shell PATH entries (all shells we may have touched) ────────────────
# POSIX `sh`: no arrays, so a whitespace-separated list is used.
PATH_FILES=""
for f in "$HOME/.profile" "$HOME/.bashrc" "$HOME/.zshrc"; do
    [ -f "$f" ] && PATH_FILES="$PATH_FILES $f"
done

NEEDS_CLEAN=0
for f in $PATH_FILES; do
    if grep -q "# Termux AI" "$f" 2>/dev/null; then NEEDS_CLEAN=1; fi
done

if [ "$NEEDS_CLEAN" = "1" ]; then
    prompt "   Remove Termux AI PATH entries from your shell config? [y/N] "
    if [ "$REPLY" = "y" ] || [ "$REPLY" = "Y" ]; then
        for f in $PATH_FILES; do
            sed -i '/# Termux AI/d' "$f" 2>/dev/null
            sed -i '\|\.local/bin|d' "$f" 2>/dev/null
            echo "   ✓ Cleaned $f"
        done
    else
        echo "   ℹ  Left shell config unchanged"
    fi
fi

echo ""
echo "✅ Termux AI uninstalled. Restart your terminal to clear PATH."
