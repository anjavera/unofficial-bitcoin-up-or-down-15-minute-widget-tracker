#!/bin/sh
# Installs the downloaded Linux build for the current user and adds an app-menu entry.
# Usage: sh install.sh [path/to/btc15-widget-linux-x86_64]   (run it from the folder holding the download)
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="${1:-$HERE/btc15-widget-linux-x86_64}"
ICON_SRC="$HERE/icon.png"
if [ ! -f "$BIN" ]; then
  echo "Could not find the app at: $BIN"
  echo "Usage: sh install.sh path/to/btc15-widget-linux-x86_64"
  exit 1
fi
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications" "$HOME/.local/share/icons"
cp "$BIN" "$HOME/.local/bin/btc15-widget"
chmod +x "$HOME/.local/bin/btc15-widget"
ICON_LINE=""
if [ -f "$ICON_SRC" ]; then
  cp "$ICON_SRC" "$HOME/.local/share/icons/btc15-widget.png"
  ICON_LINE="Icon=$HOME/.local/share/icons/btc15-widget.png"
fi
cat > "$HOME/.local/share/applications/btc15-widget.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=BTC 15m Widget
Comment=Live Polymarket US BTC Up or Down 15-minute tracker
Exec=$HOME/.local/bin/btc15-widget
$ICON_LINE
Terminal=true
Categories=Utility;Finance;
DESKTOP
echo "Installed. Find 'BTC 15m Widget' in your app menu, or run: $HOME/.local/bin/btc15-widget"
echo "(If the command is not found, add \$HOME/.local/bin to your PATH.)"
