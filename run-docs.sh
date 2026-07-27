#!/usr/bin/env bash
set -Eeuo pipefail

readonly APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PYTHON="$APP_DIR/.venv/bin/python"
readonly CONFIG="$APP_DIR/mkdocs.yml"
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

if [[ ! -f "$CONFIG" ]]; then
    echo "Error: MkDocs configuration was not found: $CONFIG" >&2
    exit 1
fi

if ! "$PYTHON" -c "import mkdocs" 2>/dev/null; then
    echo "Error: MkDocs is not installed in $APP_DIR/.venv." >&2
    echo "Install it with: $PYTHON -m pip install -r requirements-docs.txt" >&2
    exit 1
fi

dotenv_value() {
    "$PYTHON" -c \
        'import sys; from dotenv import dotenv_values; print(dotenv_values(sys.argv[1]).get(sys.argv[2], sys.argv[3]))' \
        "$DOTENV" "$1" "$2"
}

readonly SERVER_HOST="${OIL_DOCS_HOST:-$(dotenv_value OIL_DOCS_HOST 127.0.0.1)}"
readonly SERVER_PORT="${OIL_DOCS_PORT:-$(dotenv_value OIL_DOCS_PORT 10001)}"

cd "$APP_DIR"

echo "Starting MkDocs server on $SERVER_HOST:$SERVER_PORT..."
exec "$PYTHON" -m mkdocs serve \
    --config-file "$CONFIG" \
    --dev-addr "$SERVER_HOST:$SERVER_PORT"
