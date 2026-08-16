# Oil

Copyright © 2026 Elvis Baketa

Open Instrument Lab (OIL) is a Django application for laboratory instrument
workflows.

The current application provides an authenticated Dashboard, Tasks, Panels,
instrument inventory, user profile, About, and Contact pages. Physical drivers
support DC voltage,
AC voltage, and two-wire resistance on the Agilent 34401A over serial/FTDI and
the Keysight 34461A over Linux USBTMC. The deterministic Mock DMM also supports
DC current, AC current, resistance, and temperature for hardware-free
development. Selectable 3½ through 6½-digit DC voltage profiles simulate
range-dependent display resolution from 2,000 to 1,200,000 counts.
A separate Mock DC Power Supply provides a programmable 0 to 60 V output with
1 mV resolution and a safe disabled-by-default output state. The physical RND
Lab 320-KA3005P driver controls its 0 to 30 V, 0 to 5 A output over a 9600-baud
USB virtual COM or RS-232 connection.

The Tasks workspace provides an instrument builder: users select inventory
instruments one at a time, add each to the task, and configure it in a nested
instrument tab. Tasks run in the background of the Django process. Mock supply
settings support fixed voltage, one-way sweeps, optional sweep-back, and
repeated cycles; DMM tabs
offer driver capabilities and external or compatible virtual sources, while
seeded temperature samples use user-defined bounds. Task tabs poll generic
per-instrument readings, and leaving the page does not stop acquisition.
Persisted pending and running tasks are recovered after an application restart
and continue at the next sample index.

Registered measurement instruments are available from the Panels page. The
DMM panel provides continuous local measurement, single trigger, autorange and
fixed-range controls, live statistics, an automatically scaled graph, and a
read-only live view while a Task owns the instrument. Raspberry Pi CPU
temperature can be acquired through the Linux thermal-zone driver and assigned
to the secondary Task chart axis.

Each user can independently choose a colour theme and show or hide the top
navigation bar and sidebar from their Profile page. A visible sidebar can be
positioned on either the left or right.

Notable project changes are recorded in the [`CHANGELOG.md`](CHANGELOG.md)
file.

The Django application layer is organized by domain in `accounts`,
`api`, `dashboard`, `instruments`, and `measurements`. The transitional `main`
application retains the existing database models and migration history. The
session-authenticated JSON API remains available under `/api/`. Each Task has a
streaming European-format CSV export using semicolon-separated columns, decimal
commas, millisecond ISO 8601 timestamps, and the Europe/Berlin offset.

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
