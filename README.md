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

To run the application as a persistent local development service:

```bash
sudo install -d -m 700 /etc/oil
python -c 'from django.core.management.utils import get_random_secret_key; print("OIL_SECRET_KEY=" + get_random_secret_key()); print("OIL_ALLOWED_HOSTS=oil.example.com"); print("OIL_SERVER_HOST=127.0.0.1")' | sudo tee /etc/oil/oil.env >/dev/null
sudo chmod 600 /etc/oil/oil.env
sudo cp deploy/systemd/oil.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now oil
```

Set `OIL_ALLOWED_HOSTS` to a comma-separated list of the exact IP addresses or
DNS names used to reach the application. Do not use `*`.
The supplied systemd units use `/opt/oil` as a neutral example installation
directory; adjust both paths in a unit when deploying elsewhere.

## Documentation

Install the documentation dependencies and start the local preview:

```bash
python -m pip install -r requirements-docs.txt
./run-docs.sh
```

The documentation preview is available at
`http://127.0.0.1:10001/`. Run `mkdocs build --strict` before publishing
documentation changes.

To run the documentation preview as a persistent local service:

```bash
sudo cp deploy/systemd/oil-docs.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now oil-docs
```

## License

This project is licensed under the GNU Affero General Public License,
version 3 or later (`AGPL-3.0-or-later`). The full license text is available
in the [`LICENSE`](LICENSE) file.

If you make a modified version of the application available to users over a
network, you must provide those users with access to the corresponding source
code in accordance with Section 13 of the license.
