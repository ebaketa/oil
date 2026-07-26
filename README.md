# Oil

Copyright © 2026 Elvis Baketa

Open Instrument Lab (OIL) is a Django application for laboratory instrument
workflows.

The current application provides authenticated Home, About, and Contact pages.

Notable project changes are recorded in the [`CHANGELOG.md`](CHANGELOG.md)
file.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
./run.sh
```

The application is served at `http://127.0.0.1:10000/` by the supplied
development script. Sign in at `/accounts/login/`.

To run the application as a persistent local development service:

```bash
sudo cp deploy/systemd/oil.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now oil
```

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
