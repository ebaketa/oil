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

For the supplied systemd service, store the key in its root-readable
environment file before starting the service:

```bash
sudo install -d -m 700 /etc/oil
python -c 'from django.core.management.utils import get_random_secret_key; print("OIL_SECRET_KEY=" + get_random_secret_key()); print("OIL_ALLOWED_HOSTS=oil.example.com"); print("OIL_SERVER_HOST=127.0.0.1")' | sudo tee /etc/oil/oil.env >/dev/null
sudo chmod 600 /etc/oil/oil.env
sudo cp deploy/systemd/oil.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now oil
```

Set `OIL_ALLOWED_HOSTS` to the exact comma-separated IP addresses or DNS names
used to reach the application. Do not use `*`.
The supplied systemd units use `/opt/oil` as a neutral example installation
directory; adjust both paths in a unit when deploying elsewhere.

## Documentation site

```bash
source .venv/bin/activate
python -m pip install -r requirements-docs.txt
./run-docs.sh
```

The documentation preview is served at `http://127.0.0.1:10001/`.
Use `mkdocs build --strict` to generate and validate the static site.
