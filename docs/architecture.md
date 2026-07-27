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
- `MeasurementRun` stores the owner, instrument, function, acquisition mode,
  requested interval and count, lifecycle timestamps, status, notes, and error
  for one measurement series.
- `Measurement` stores normalized values, units, parameters, and timestamps
  while protecting referenced instrument and run records from deletion.
- `drivers` contains hardware communication isolated from Django models and
  views. The first drivers support the Agilent 34401A over serial/FTDI and the
  Keysight 34461A over Linux USBTMC, plus a deterministic Mock instrument for
  hardware-free development.
- `DriverRegistry` maps persistent inventory driver names to implementation
  classes without conditional logic in the driver factory.
- `services` owns instrument connection lifecycle, caching, and concurrency.

The project currently uses SQLite for local development. Hardware connection
services and measurement workflows will be documented when they are introduced.

## Instrument drivers

Both digital multimeter drivers implement the same lifecycle and measurement
contract. Device addresses and measurement settings are supplied when a driver
is created; importing a driver never opens hardware. Drivers support context
managers so connections are closed after successful operations and exceptions.

Built-in implementations register their persistent names with
`DriverRegistry`. The factory resolves the stored name and delegates inventory
construction to the driver's shared `from_instrument()` class method. A new
driver therefore extends the registry without adding another branch to
`create_driver()`. Duplicate names cannot replace a different implementation.

Each driver also publishes immutable measurement metadata through
`capabilities()` without opening a hardware connection. Every function
describes its display label, unit, autorange support, and any supported ranges
or NPLC values. `DriverRegistry` and `Instrument` expose the same metadata to
forms and views. Measurement forms enforce the selected instrument's supported
functions on the server, and the driver details page lists them for users.

Hardware-independent unit tests use simulated serial and USBTMC connections.
Application views do not communicate with either instrument directly.

The registered Mock driver uses `mock://default` and cycles through stable
readings for DC voltage, AC voltage, and resistance while following the same
connect, identify, configure, measure, and disconnect contract as physical
hardware. The
`mock://timeout` and `mock://connection-error` profiles support deterministic
failure-path testing.

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

The Agilent measurement transport follows the instrument manual's 9600 baud,
8 data bits, no parity, and 2 stop bits framing. Error codes 511, 512, and 513
indicate RS-232 framing, overrun, and parity failures. NPLC 100 conversions can
take longer than a fixed five-second delay, so OIL does not force NPLC 100.
DC and AC voltage and two-wire resistance measurements use autorange and wait
within a bounded response window. Configuration completes before the first
requested conversion; repeated
physical session tests confirmed that an additional discarded warm-up
conversion is unnecessary.

Keysight 34461A measurements use the same function-specific autorange policy.
DC voltage does not force a fixed 10 V range or NPLC 100. Its USBTMC transport
does not require the Agilent-specific serial framing.

An instrument marked `Reachable` passed its most recent driver operation.
`Online` on the Dashboard is reserved for a currently open managed connection;
temporary operations normally return it to zero after cleanup. The Dashboard
groups are mutually exclusive, so an online instrument is not also included in
the reachable count.

## Measurements

The Dashboard shows the number of stored measurements and links to a dedicated
Measurements page. Measurement records reference their instrument and store a
normalized parameter, numeric value, unit, optional notes, and capture
timestamp.

`MeasurementRun` provides persistent series metadata for Single, Continuous,
and Loop acquisitions. Its lifecycle supports pending, running, completed,
stopped, and failed states. A run can retain history after its user account is
deleted, while its instrument and any run referenced by readings are protected
from deletion. The `Measurement.run` relationship remains optional during the
0.0.5 transition; the acquisition workflows will populate it before a later
migration makes the relationship mandatory.

The Single measurement form selects an instrument and a supported operation.
Submitting DC voltage, AC voltage, or resistance uses a managed connection,
calls the driver's normalized measurement method, and stores the result only
after successful communication.
A failed operation stores the driver error on the instrument and does not
create a measurement record. Temporary connections return front-panel control
after the operation, while a connection opened explicitly from the inventory
remains open.

The Loop form performs a bounded series of 2 to 100 readings at intervals from
0.1 to 3600 seconds. A single managed connection is held for the series, and
each successful reading is stored independently. The initial implementation
runs synchronously, so the browser request remains open until the loop
finishes, then displays that series in a results table below the configuration
form. Long-running and scheduled acquisition should move to a dedicated
instrument worker.

With JavaScript enabled, the loop form uses an authenticated POST streaming
endpoint. The server holds one connection and emits newline-delimited JSON
after each stored reading; the browser appends each record to the table before
the next interval completes. Proxy buffering is explicitly disabled for this
response. The regular synchronous form submission remains available as a
non-JavaScript fallback.

Once a loop starts, its editable fields are hidden and the selected instrument,
function, count, interval, and notes are copied into a two-row summary above
the results. Invalid settings restore the form before any hardware operation
begins.

Continuous measurement uses the same live NDJSON result format but has no
predefined count. Start opens one temporary connection, applies the selected
driver configuration once, and stores and streams readings until Stop is
selected. Each browser run supplies a UUID owned by the signed-in user. The
Stop endpoint sets a process-local event, which interrupts the interval wait
and lets the generator's cleanup close the instrument immediately. Leaving the
page also sends the same stop request. A multi-process deployment should move
these stop signals to shared infrastructure or a dedicated instrument worker.

## Access control

Dashboard, Contact, and About require an authenticated user. Anonymous requests are
redirected to `/accounts/login/`. Logout accepts POST requests with CSRF
protection and redirects to the login page.

Authenticated users can open their profile by selecting their username. The
profile supports changes to account details and the interface colour theme.
Updates accept POST requests with CSRF protection, validate all fields, and
store theme choices separately for each user.
