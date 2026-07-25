#!/usr/bin/env bash
# Termux AI CLI Uninstaller
# Usage: curl -fsSL https://raw.githubusercontent.com/kabarbaik-xyz/termux-ai/main/uninstall.sh | bash
set -e

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
        read -p "   Stop running ${ENGINE:-ollama} server (PID: $PID)? [Y/n] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            kill -- -"$PID" 2>/dev/null || kill "$PID" 2>/dev/null || true
            echo "   ✓ Stopped ${ENGINE:-ollama} server"
        fi
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
    read -p "   Remove config & chat history ($CONFIG_DIR)? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$CONFIG_DIR"
        echo "   ✓ Removed $CONFIG_DIR"
    else
        echo "   ℹ  Kept $CONFIG_DIR"
    fi
fi

# ── Clean .bashrc ─────────────────────────────────────────────────────────────
if grep -q "# Termux AI" "$HOME/.bashrc" 2>/dev/null; then
    read -p "   Remove PATH entry from ~/.bashrc? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sed -i '/# Termux AI/d' "$HOME/.bashrc"
        sed -i '\|\.local/bin|d' "$HOME/.bashrc"
        echo "   ✓ Cleaned ~/.bashrc"
    else
        echo "   ℹ  Left ~/.bashrc unchanged"
    fi
fi

echo ""
echo "✅ Termux AI uninstalled. Restart your terminal to clear PATH."
