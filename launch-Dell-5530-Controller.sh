#!/bin/sh
set -eu

APP_DIR="/home/$USER/Dell-5530-Controller"
PYTHON_BIN="/usr/bin/python3"
MAIN_FILE="$APP_DIR/main.py"

cd "$APP_DIR"

# Fast path: works when sudoers exception exists.
if /usr/bin/sudo -n "$PYTHON_BIN" "$MAIN_FILE"; then
    exit 0
fi

# Fallback: prompt via polkit when sudoers is not installed.
if command -v pkexec >/dev/null 2>&1; then
    exec /usr/bin/pkexec "$PYTHON_BIN" "$MAIN_FILE"
fi

# Last resort: start without elevation (keyboard-only features may still work).
exec "$PYTHON_BIN" "$MAIN_FILE"
