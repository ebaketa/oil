# OIL Documentation

Open Instrument Lab (OIL) is a Django application intended to support
laboratory instrument workflows.

The project is currently in an early development stage. Authenticated users can
manage a shared instrument inventory from the Dashboard and Instruments pages.
Initial drivers support the Agilent 34401A over serial/FTDI and the Keysight
34461A over Linux USBTMC. Hardware connection and measurement workflows have
not yet been exposed through the application interface.

## Documentation workflow

1. Update the relevant page whenever behavior or setup changes.
2. Add English docstrings to public Python modules, classes, and functions.
3. Preview changes with `./run-docs.sh`.
4. Validate the site with `mkdocs build --strict`.

## License

Copyright (C) 2026 Elvis Baketa.

OIL is licensed under the GNU Affero General Public License, version 3 or
(at your option) any later version (`AGPL-3.0-or-later`). The complete license
text is available in the repository's `LICENSE` file.
