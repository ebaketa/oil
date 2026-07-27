# Installation

## Requirements

- Python 3.11 or newer
- A Python virtual environment

## Local setup

```bash
git clone https://github.com/ebaketa/oil.git
cd oil
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -c 'from pathlib import Path; from django.core.management.utils import get_random_secret_key; path = Path(".env"); path.write_text(path.read_text().replace("replace-with-a-long-random-secret", get_random_secret_key()))'
chmod 600 .env
python manage.py migrate
./run.sh
```

The supplied development script serves the application at
`http://127.0.0.1:10000/`.

Keep `OIL_SECRET_KEY` private and reuse the same value across restarts.
Changing it invalidates existing sessions and other signed Django data.
`OIL_DEBUG=True` is intended only for local development and must not be set in
the systemd environment file. Django reads `.env` automatically for local
development without overriding variables already supplied by the environment.

## Systemd deployment

Install both services from the checked-out application directory:

```bash
chmod +x run.sh run-docs.sh deploy/install-systemd.sh
sudo ./deploy/install-systemd.sh --user "$USER"
```

The installer detects the checkout path instead of assuming `/opt/oil`, renders
both systemd units with the selected account and its primary group, validates
the virtual environment and `.env`, then enables and starts the services.
Use `--app-dir PATH` only when installing a checkout other than the one that
contains the installer. Use `--no-start` to install the units without starting
them.

Both launchers read host and port settings directly from the checkout's `.env`;
a separate `/etc/oil/oil.env` is not required. Keep `.env` readable only by the
service account:

```bash
chmod 600 .env
```

Set `OIL_ALLOWED_HOSTS` to the exact comma-separated IP addresses or DNS names
used to reach the application. Do not use `*`. `OIL_SERVER_HOST` and
`OIL_DOCS_HOST` may use the server's specific interface address.

Inspect the installed services with:

```bash
sudo systemctl status oil oil-docs --no-pager -l
sudo journalctl -u oil -u oil-docs -n 100 --no-pager
```

## Documentation site

```bash
source .venv/bin/activate
python -m pip install -r requirements-docs.txt
./run-docs.sh
```

The documentation preview is served at `http://127.0.0.1:10001/`.
Use `mkdocs build --strict` to generate and validate the static site.
