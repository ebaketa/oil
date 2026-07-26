# Architecture

```text
Browser → Views → Services → ConnectionManager → Drivers → Instrument
                    ↓
                 Models
```

## Current components

- `config` contains project-wide Django settings and URL configuration.
- `main` contains the application's URL routes and views.
- `templates/main` contains the user-facing HTML templates.
- `templates/registration` contains the login form used by Django auth views.
- `static/main` contains project-specific static assets.
- `UserPreference` stores each user's selected interface colour theme.
- `Instrument` stores shared laboratory inventory, driver selection, device
  address, and connection status.
- `Measurement` stores normalized values, units, parameters, and timestamps
  while protecting referenced instrument records from deletion.
- `drivers` contains hardware communication isolated from Django models and
  views. The first drivers support the Agilent 34401A over serial/FTDI and the
  Keysight 34461A over Linux USBTMC.
- `services` owns instrument connection lifecycle, caching, and concurrency.

The project currently uses SQLite for local development. Hardware connection
services and measurement workflows will be documented when they are introduced.

## Instrument drivers

Both digital multimeter drivers implement the same lifecycle and measurement
contract. Device addresses and measurement settings are supplied when a driver
is created; importing a driver never opens hardware. Drivers support context
managers so connections are closed after successful operations and exceptions.

Hardware-independent unit tests use simulated serial and USBTMC connections.
Application views do not communicate with either instrument directly.

## Connection Manager

`ConnectionManager` owns process-local active drivers and assigns a re-entrant
lock to every saved instrument. Repeated connects reuse an active driver, while
exclusive access prevents overlapping operations on the same hardware.

Temporary sessions open, lock, and guarantee cleanup of a connection they own.
If a session receives a connection that was already open, it leaves ownership
and disconnection to the original caller. Dashboard `Online` counts are derived
from these live managed connections rather than persisted database status.

The cache is process-local. A multi-process deployment will require a single
instrument worker or an inter-process locking and connection service.

## Instrument inventory

Authenticated users open the dedicated Instruments page to view the shared
inventory, add a laboratory instrument, or select an existing instrument to
edit its settings. The Dashboard only shows summary counts and links to the
inventory. New instruments start offline; creating or editing an inventory
record never opens a hardware connection. The inventory Connect action opens
and retains a managed connection; Disconnect returns front-panel control and
closes it. The displayed connection badge is derived from the live manager
rather than persisted database status: an open connection is `Online`;
otherwise the inventory displays `Reachable`.

Selecting a driver from the inventory opens its details page. An authenticated,
CSRF-protected POST test opens the configured device, requests `*IDN?`, and
returns front-panel control with `SYST:LOC` before closing the connection. No
measurement configuration commands are sent during this test. OIL stores the
test time, identification response, or last error for later review.

The DCV Auto mode test executes configuration commands with `*OPC?` completion
and `SYST:ERR?` error checks. It then queries the active function and autorange
state; command completion alone is not treated as proof that the requested mode
is active. Existing SCPI errors are drained before configuration so an old error
cannot be incorrectly attributed to a new command.

The Agilent 34401A RS-232 driver uses a model-specific completion strategy
because `*OPC?` can remain pending after its configuration command. It waits for
the command, checks `SYST:ERR?`, and relies on the same function and autorange
read-back as the authoritative state confirmation.

An instrument marked `Reachable` passed its most recent driver operation.
`Online` on the Dashboard is reserved for a currently open managed connection;
temporary operations normally return it to zero after cleanup. The Dashboard
groups are mutually exclusive, so an online instrument is not also included in
the reachable count.

## Measurements

The Dashboard shows the number of stored measurements and links to a dedicated
Measurements page. Measurement records reference their instrument and store a
normalized parameter, numeric value, unit, and capture timestamp. Driver
measurement actions will populate this model in a later workflow.

## Access control

Dashboard, Contact, and About require an authenticated user. Anonymous requests are
redirected to `/accounts/login/`. Logout accepts POST requests with CSRF
protection and redirects to the login page.

Authenticated users can open their profile by selecting their username. The
profile supports changes to account details and the interface colour theme.
Updates accept POST requests with CSRF protection, validate all fields, and
store theme choices separately for each user.
