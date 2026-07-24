#!/usr/bin/env bash
# Termux AI CLI Uninstaller
# Usage: bash uninstall.sh
set -e

INSTALL_DIR="${HOME}/.local/bin"
SCRIPT_PATH="${INSTALL_DIR}/ai"
CONFIG_DIR="${HOME}/.config/termux-ai"

echo "🗑  Uninstalling Termux AI..."

# Remove the binary
if [ -f "$SCRIPT_PATH" ]; then
    rm -f "$SCRIPT_PATH"
    echo "   ✓ Removed $SCRIPT_PATH"
else
    echo "   ℹ  $SCRIPT_PATH not found (already removed?)"
fi

# Optionally remove config & history
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

# Optionally remove PATH line from .bashrc
if grep -q "# Termux AI" "$HOME/.bashrc" 2>/dev/null; then
    read -p "   Remove PATH entry from ~/.bashrc? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        sed -i '/# Termux AI/d' "$HOME/.bashrc"
        sed -i '/\.local\/bin/d' "$HOME/.bashrc"
        echo "   ✓ Cleaned ~/.bashrc"
    else
        echo "   ℹ  Left ~/.bashrc unchanged"
    fi
fi

echo ""
echo "✅ Termux AI uninstalled. Restart your terminal to clear PATH."
