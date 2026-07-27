# Developer Guide

## Language

Source code, identifiers, comments, docstrings, user-interface text, commit
messages, and project documentation must be written in English.

## Python documentation

Public modules, classes, and functions should have concise English docstrings.
Use Google-style sections when parameters, return values, or exceptions need
additional explanation:

```python
def read_measurement(instrument_id: int) -> float:
    """Read a measurement from an instrument.

    Args:
        instrument_id: Database identifier of the instrument.

    Returns:
        The measured value.

    Raises:
        LookupError: If the instrument does not exist.
    """
```

## Django application boundaries

Place new code in the application that owns its domain:

- `accounts` for profile and preference behavior
- `dashboard` for summary and informational pages
- `instruments` for inventory and driver operations
- `measurements` for acquisition workflows and stored readings

`main` remains the owner of existing database models and migrations during the
transition. Its forms, views, services, context processor, and URL modules are
compatibility imports only; new code must import from the domain application.
Do not move a model to a new Django app label without an explicit state and
data migration that preserves existing tables, content types, and permissions.

## Adding an instrument driver

New instrument drivers must inherit from `BaseInstrumentDriver` and accept the
stored instrument address as their first constructor argument. Import the class
from `drivers/__init__.py` and register its persistent inventory name with
`DriverRegistry.register()`. Do not add model-specific conditionals to
`create_driver()`. Define the class-level `CAPABILITIES` mapping with a
`MeasurementCapability` entry for every function the implementation supports;
capabilities must describe only behavior implemented and verified by the
driver.

For hardware-free development, add an instrument with driver `Mock instrument`
and address `mock://default`. Use `mock://timeout` to simulate a measurement
timeout or `mock://connection-error` to simulate unavailable hardware.

## Instrument transports

Drivers must use an `InstrumentTransport` implementation instead of opening
serial ports or USBTMC device nodes directly. Reuse `SerialTransport`,
`USBTMCTransport`, or `MockTransport` when their behavior matches the device.
Add a new transport only for a genuinely different communication channel.

Keep responsibilities separate:

- transports open and close channels and transfer decoded SCPI messages
- drivers define model-specific commands, timing, validation, and results
- services manage driver lifecycles and persistence

Inject transports into driver constructors in unit tests. Hardware-specific
framing and timeout tests belong to the transport; SCPI sequence tests belong
to the driver.

## Validation

Run the application and documentation checks before committing:

```bash
python manage.py check
python manage.py test
mkdocs build --strict
```

The generated `site/` directory is ignored by Git.

## Dashboard cards

Dashboard summary cards use `card oil-dashboard-card` on the card container and
`oil-dashboard-card-title` on the title. Reuse these classes for new cards so
borders, shadows, height, title size, and text colour stay consistent.
Keep the Status card last in the Dashboard card row; add new summary cards
before it.

## Application development service

Install the generated systemd units to keep the local Django development server
and documentation preview running:

```bash
chmod +x run.sh run-docs.sh deploy/install-systemd.sh
sudo ./deploy/install-systemd.sh --user "$USER"
```

The installer detects the checkout directory and renders both units for the
selected user and primary group. Both launchers use host and port values from
the checkout's `.env`; no fixed installation path or separate systemd
environment file is required.

Inspect the service and follow its logs with:

```bash
systemctl status oil
journalctl -u oil -f
```

This unit runs Django's development server on `127.0.0.1:10000` by default. It is
intended for local development and must not be used as a production web
server.

## Documentation preview service

The application service installer also installs the documentation preview
service.

Inspect the service and follow its logs with:

```bash
systemctl status oil-docs
journalctl -u oil-docs -f
```

The preview service is intended for the local network and listens on
`127.0.0.1:10001`.
