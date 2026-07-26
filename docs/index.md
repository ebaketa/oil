# OIL Documentation

Open Instrument Lab (OIL) is a Django application intended to support
laboratory instrument workflows.

The project is currently in an early development stage. Authenticated users
can access the Home, About, and Contact pages; instrument management and
measurement features have not yet been implemented.

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
