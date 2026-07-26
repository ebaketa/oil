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
python manage.py migrate
./run.sh
```

The supplied development script serves the application at
`http://127.0.0.1:10000/`.

## Documentation site

```bash
source .venv/bin/activate
python -m pip install -r requirements-docs.txt
./run-docs.sh
```

The documentation preview is served at `http://127.0.0.1:10001/`.
Use `mkdocs build --strict` to generate and validate the static site.
