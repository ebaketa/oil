#!/usr/bin/env bash
set -Eeuo pipefail

readonly APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PYTHON="$APP_DIR/.venv/bin/python"
readonly MANAGE="$APP_DIR/manage.py"
readonly DOTENV="$APP_DIR/.env"

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

dotenv_value() {
    "$PYTHON" -c \
        'import sys; from dotenv import dotenv_values; print(dotenv_values(sys.argv[1]).get(sys.argv[2], sys.argv[3]))' \
        "$DOTENV" "$1" "$2"
}

readonly SERVER_HOST="${OIL_SERVER_HOST:-$(dotenv_value OIL_SERVER_HOST 127.0.0.1)}"
readonly SERVER_PORT="${OIL_SERVER_PORT:-$(dotenv_value OIL_SERVER_PORT 8000)}"

cd "$APP_DIR"

echo "Starting Django server on $SERVER_HOST:$SERVER_PORT..."
exec "$PYTHON" "$MANAGE" runserver --noreload "$SERVER_HOST:$SERVER_PORT"
