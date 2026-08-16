# Architecture

```text
Browser → Views → Services → ConnectionManager → Drivers → Instrument
                    ↓
                 Models
```

## Current components

- `config` contains project-wide Django settings and root URL configuration.
- `api` exposes session-authenticated JSON inventory and measurement endpoints
  while reusing the domain forms and services.
- `dashboard` owns the Dashboard, About, and Contact views and templates.
- `accounts` owns the profile form, preference context processor, view, and
  template.
- `instruments` owns inventory forms, views, driver-operation services, URLs,
  templates, and admin configuration.
- `measurements` owns acquisition forms, views, services, session state, URLs,
  templates, static assets, and admin configuration.
- `tasks` owns persistent multi-instrument automation configuration, background
  execution, synchronized samples, generic readings, live charts, and Task CSV
  export.
- `dmm_panel` provides responsive local and read-only live front panels for
  registered measurement instruments.
- `main` is the transitional database and compatibility application. It retains
  the existing models and migration history so application decomposition does
  not rename tables, recreate records, or invalidate permissions.
- `templates/registration` contains the login form used by Django auth views.
- `templates/main/base.html` and shared static assets provide the common UI
  shell; domain-specific templates and JavaScript live with their applications.
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
  Keysight 34461A over Linux USBTMC, plus a deterministic Mock DMM for
  hardware-free development and the RND Lab 320-KA3005P power supply over
  serial.
- `drivers/transports` owns reusable communication channels for Serial/FTDI,
  Linux USBTMC, and in-memory Mock operation.
- `DriverRegistry` maps persistent inventory driver names to implementation
  classes without conditional logic in the driver factory.
- `services` owns instrument connection lifecycle, caching, and concurrency.

The project currently uses SQLite for local development. Existing database
tables retain their `main_*` names during the application decomposition.
Compatibility imports in `main` allow external code to migrate gradually to
the domain modules without changing runtime behavior.

## Instrument drivers

Both digital multimeter drivers implement the same lifecycle and measurement
contract. Device addresses and measurement settings are supplied when a driver
is created; importing a driver never opens hardware. Drivers support context
managers so connections are closed after successful operations and exceptions.

Drivers own model-specific SCPI commands, timing, capability metadata, and
measurement normalization. They delegate communication to the shared
`InstrumentTransport` contract:

```text
Driver → InstrumentTransport → Serial / USBTMC / Mock
```

Every transport implements `open`, `close`, `write`, `read`, and `query`.
Serial additionally supports input-buffer cleanup needed by the Agilent
initialization sequence. Transport injection keeps driver tests independent
from physical hardware.

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

The registered Mock DMM driver uses `mock-dmm://default` and cycles through stable,
function-specific readings for DC voltage, AC voltage, DC current, AC current,
resistance, and temperature while following the same connect, identify,
measure, and disconnect lifecycle as physical hardware. The
`mock-dmm://timeout` and `mock-dmm://connection-error` profiles support deterministic
failure-path testing. DC voltage supports selectable 3½, 3¾, 4½, 4¾, 5½, and
6½-digit modes from 2,000 to 1,200,000 counts. Each mode publishes full-scale
ranges and quantization resolution used consistently by the runner, Task table,
DMM panel, and CSV export. The original 50,000-count 4¾ profile remains
available for compatibility with saved Tasks.

The Raspberry Pi CPU temperature driver reads Linux thermal-zone millidegrees
from `/sys/class/thermal/thermal_zone0/temp`, normalizes the result to degrees
Celsius, and reports two decimal places. It is read-only and can be assigned to
the primary or secondary Task chart axis.

The separate Mock DC Power Supply uses `mock-psu://default`. It provides a
single programmable output from 0.000 V to 60.000 V in exact 0.001 V steps.
Its output starts disabled, measures zero volts while disabled, follows the
configured setpoint while enabled, and is disabled automatically whenever its
connection closes. The `mock-psu://connection-error` profile provides a
deterministic connection failure.

The RND Lab 320-KA3005P driver uses a USB virtual COM or RS-232 device path
such as `/dev/ttyUSB0`. It opens the documented 9600-baud 8N1 connection,
programs channel-one voltage in 0.01 V steps and current in 0.001 A steps,
controls the output, and reads actual output voltage and current. Its Task
builder voltage range is limited to the physical 0–30 V capability.

## Automation tasks

The `tasks` application stores shared `AutomationTask` settings, an ordered
collection of `TaskInstrument` assignments with driver-specific JSON
configuration, synchronized `TaskSample` steps, and generic `TaskReading`
values. The New Task builder starts empty: users add inventory instruments
from a combobox and configure each in its own nested tab. Mock supply settings
support a fixed setpoint, inclusive one-way sweep, optional return sweep, or
repeated up/down cycle.
DMM tabs expose only capabilities published by the selected driver. A Mock DMM
can follow the enabled virtual supply output with deterministic
millivolt-scale error or use its external independent sequence. Temperature
values use a stored random seed, range, and resolution so a run is repeatable.

The current runner uses a bounded thread pool inside the Django process. It is
independent of the browser page, polls a database stop flag, stores each sample,
and closes every managed instrument connection through guaranteed cleanup.
The Mock supply also disables its output on disconnect. At application startup,
persisted Pending and Running tasks without a stop request are scheduled again.
A resumed task marks any sample left in Acquiring state as failed, preserves
completed history, skips the original start delay, and continues with the next
sample index. Recovery is designed for the supplied single-process deployment;
a multi-process production deployment still requires a dedicated worker or a
database-backed task-claim mechanism.

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

The shared serial transport opens the Agilent connection at 9600 baud, 8 data
bits, no parity, and 2 stop bits. The driver retains the model-specific Remote,
clear, DCV Auto, and timing sequence. Error codes 511, 512, and 513 indicate
RS-232 framing, overrun, and parity failures. NPLC 100 conversions can take
longer than a fixed five-second delay, so OIL does not force NPLC 100.
DC and AC voltage and two-wire resistance measurements use autorange and wait
within a bounded response window. Configuration completes before the first
requested conversion; repeated
physical session tests confirmed that an additional discarded warm-up
conversion is unnecessary.

Keysight 34461A measurements use the same function-specific autorange policy.
DC voltage does not force a fixed 10 V range or NPLC 100. The reusable USBTMC
transport opens the Linux device node in unbuffered binary mode and does not
include Agilent-specific serial policy.

An instrument marked `Reachable` passed its most recent driver operation.
`Online` on the Dashboard is reserved for a currently open managed connection;
temporary operations normally return it to zero after cleanup. The Dashboard
groups are mutually exclusive, so an online instrument is not also included in
the reachable count.

## Task results and CSV

Task results use one `TaskSample` row per trigger. Instrument readings belonging
to that trigger are stored as related `TaskReading` rows, so a sample ID is not
the same as one individual instrument reading. The live Task table deliberately
loads a bounded recent result set for browser performance.

Task CSV export pivots those related readings into one row per sample and one
column per configured output. It streams rows instead of buffering the complete
file, uses `;` as the delimiter, a decimal comma, and CRLF line endings. Time is
stored by Django as an aware timestamp and exported in the `Europe/Berlin` zone
as ISO 8601 with milliseconds and a numeric UTC offset, for example:

```text
125;2026-08-11T14:32:05.174+02:00;0,174;5,00;5,00;4,9999;48,75
```

## Legacy Measurements

The older Measurements domain and routes remain available for compatibility,
but its page is currently hidden from primary Dashboard and navigation links.
Measurement records reference their instrument and store a
normalized parameter, numeric value, unit, optional notes, and capture
timestamp.

The Measurements page provides an authenticated streaming CSV export. Rows are
read from the database in bounded chunks instead of buffering the complete
dataset in memory. The file includes stable measurement and instrument columns,
uses an Excel-compatible UTF-8 BOM, and prefixes formula-like user text so
spreadsheet applications treat it as literal data. Numeric readings remain
numeric, including negative values.

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
