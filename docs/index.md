# OIL Documentation

Open Instrument Lab (OIL) is a Django application intended to support
laboratory instrument workflows.

The project is currently in an early development stage. Authenticated users can
manage a shared instrument inventory, configure persistent automation Tasks,
and monitor registered instruments through responsive DMM panels. Drivers
support the Agilent 34401A over serial/FTDI, the Keysight 34461A over Linux
USBTMC, Mock and physical RND power supplies, a deterministic Mock DMM, and
Raspberry Pi CPU temperature. Task results can be monitored live and downloaded
as a European-format CSV file.

See [Automation Tasks](tasks.md) for acquisition and recovery behavior and
[DMM Panels](panels.md) for local and Task-owned panel operation.

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
