#!/usr/bin/env bash
set -Eeuo pipefail

readonly APP_DIR="/var/www/oil"
readonly PYTHON="$APP_DIR/.venv/bin/python"
readonly MANAGE="$APP_DIR/manage.py"
readonly SERVER_HOST="127.0.0.1"
readonly SERVER_PORT="10000"

trap 'echo "Error on line $LINENO: command failed." >&2' ERR

if [[ ! -d "$APP_DIR" ]]; then
    echo "Error: application directory does not exist: $APP_DIR" >&2
    exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
    echo "Error: virtual environment Python is not executable: $PYTHON" >&2
    exit 1
fi

if [[ ! -f "$MANAGE" ]]; then
    echo "Error: manage.py was not found: $MANAGE" >&2
    exit 1
fi

cd "$APP_DIR"

echo "Starting Django server on $SERVER_HOST:$SERVER_PORT..."
exec "$PYTHON" "$MANAGE" runserver "$SERVER_HOST:$SERVER_PORT"
