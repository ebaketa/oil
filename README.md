# Oil

Copyright © 2026 Elvis Baketa

Open Instrument Lab (OIL) is a Django application for laboratory instrument
workflows.

The current application provides authenticated Dashboard, instrument inventory,
user profile, About, and Contact pages. Drivers support DC voltage, AC voltage,
and two-wire resistance on the Agilent 34401A over serial/FTDI, the Keysight
34461A over Linux USBTMC, and a deterministic Mock instrument.

Notable project changes are recorded in the [`CHANGELOG.md`](CHANGELOG.md)
file.

The Django application layer is organized by domain in `accounts`,
`api`, `dashboard`, `instruments`, and `measurements`. The transitional `main`
application retains the existing database models and migration history. The
session-authenticated JSON API is available under `/api/`, and authenticated
users can download stored measurements from `/measurements/export.csv`.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -c 'from pathlib import Path; from django.core.management.utils import get_random_secret_key; path = Path(".env"); path.write_text(path.read_text().replace("replace-with-a-long-random-secret", get_random_secret_key()))'
chmod 600 .env
python manage.py migrate
python manage.py createsuperuser
./run.sh
```

The application is served at `http://127.0.0.1:10000/` by the supplied
development script. Sign in at `/accounts/login/`. Keep `OIL_SECRET_KEY`
private and persistent; changing it invalidates existing sessions and other
signed Django data. `OIL_DEBUG=True` is intended only for local development;
omit it from deployed environments. Django automatically reads the ignored
local `.env` file, while existing process variables take precedence.

To install the application and documentation preview as persistent systemd
services from any checkout location:

```bash
chmod +x run.sh run-docs.sh deploy/install-systemd.sh
sudo ./deploy/install-systemd.sh --user "$USER"
```

Set `OIL_ALLOWED_HOSTS` to a comma-separated list of the exact IP addresses or
DNS names used to reach the application. Do not use `*`. The installer detects
the checkout path and renders both units for the selected account. Both
launchers read the checkout's ignored `.env` file.

## Documentation

Install the documentation dependencies and start the local preview:

```bash
python -m pip install -r requirements-docs.txt
./run-docs.sh
```

The documentation preview is available at
`http://127.0.0.1:10001/`. Run `mkdocs build --strict` before publishing
documentation changes.

The systemd installer above installs this preview together with the application.

## License

This project is licensed under the GNU Affero General Public License,
version 3 or later (`AGPL-3.0-or-later`). The full license text is available
in the [`LICENSE`](LICENSE) file.

If you make a modified version of the application available to users over a
network, you must provide those users with access to the corresponding source
code in accordance with Section 13 of the license.
