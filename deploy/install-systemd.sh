#!/usr/bin/env bash
set -Eeuo pipefail

readonly DEPLOY_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly DEFAULT_APP_DIR="$(cd -- "$DEPLOY_DIR/.." && pwd)"
readonly SYSTEMD_DIR="/etc/systemd/system"

APP_DIR="$DEFAULT_APP_DIR"
SERVICE_USER="${SUDO_USER:-}"
START_SERVICES=true

usage() {
    cat <<'EOF'
Usage: sudo ./deploy/install-systemd.sh [options]

Options:
  --user USER       Account that owns and runs OIL (default: invoking sudo user)
  --app-dir PATH    OIL checkout directory (default: detected automatically)
  --no-start        Install units without enabling or starting them
  -h, --help        Show this help
EOF
}

fail() {
    echo "Error: $*" >&2
    exit 1
}

while (($#)); do
    case "$1" in
        --user)
            (($# >= 2)) || fail "--user requires a value."
            SERVICE_USER="$2"
            shift 2
            ;;
        --app-dir)
            (($# >= 2)) || fail "--app-dir requires a value."
            APP_DIR="$2"
            shift 2
            ;;
        --no-start)
            START_SERVICES=false
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            fail "unknown option: $1"
            ;;
    esac
done

((EUID == 0)) || fail "run this installer with sudo."
[[ -n "$SERVICE_USER" ]] || fail "use --user USER when no sudo user is available."
[[ "$SERVICE_USER" =~ ^[a-z_][a-z0-9_-]*[$]?$ ]] \
    || fail "unsupported service user name: $SERVICE_USER"
id "$SERVICE_USER" >/dev/null 2>&1 \
    || fail "service user does not exist: $SERVICE_USER"

APP_DIR="$(realpath "$APP_DIR")"
[[ "$APP_DIR" != *[[:space:]]* ]] \
    || fail "the application path must not contain whitespace."
[[ -x "$APP_DIR/run.sh" ]] || fail "run.sh is not executable in $APP_DIR."
[[ -x "$APP_DIR/run-docs.sh" ]] \
    || fail "run-docs.sh is not executable in $APP_DIR."
[[ -x "$APP_DIR/.venv/bin/python" ]] \
    || fail "Python virtual environment was not found in $APP_DIR/.venv."
[[ -f "$APP_DIR/.env" ]] || fail "configuration file was not found: $APP_DIR/.env"
[[ -f "$APP_DIR/mkdocs.yml" ]] || fail "mkdocs.yml was not found in $APP_DIR."

SERVICE_GROUP="$(id -gn "$SERVICE_USER")"
runuser -u "$SERVICE_USER" -- test -r "$APP_DIR/.env" \
    || fail "$SERVICE_USER cannot read $APP_DIR/.env."
runuser -u "$SERVICE_USER" -- \
    "$APP_DIR/.venv/bin/python" -c "import django, dotenv, mkdocs" \
    || fail "Django, python-dotenv, or MkDocs is missing from the virtual environment."
(
    cd "$APP_DIR"
    runuser -u "$SERVICE_USER" -- \
        "$APP_DIR/.venv/bin/python" manage.py check
) || fail "Django configuration check failed."

render_unit() {
    local template="$1"
    local destination="$2"
    local content

    content="$(<"$template")"
    content="${content//@OIL_USER@/$SERVICE_USER}"
    content="${content//@OIL_GROUP@/$SERVICE_GROUP}"
    content="${content//@OIL_APP_DIR@/$APP_DIR}"
    printf '%s\n' "$content" >"$destination"
    chmod 0644 "$destination"
}

render_unit \
    "$DEPLOY_DIR/systemd/oil.service.in" \
    "$SYSTEMD_DIR/oil.service"
render_unit \
    "$DEPLOY_DIR/systemd/oil-docs.service.in" \
    "$SYSTEMD_DIR/oil-docs.service"

systemctl daemon-reload

if $START_SERVICES; then
    systemctl enable oil.service oil-docs.service
    systemctl restart oil.service oil-docs.service
    echo "OIL and OIL documentation services are installed and running."
else
    echo "OIL systemd units are installed but were not started."
fi

echo "Application directory: $APP_DIR"
echo "Service account: $SERVICE_USER:$SERVICE_GROUP"
echo "Configuration: $APP_DIR/.env"
