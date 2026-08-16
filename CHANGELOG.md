# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Added responsive DMM panels with local continuous measurement, single
  trigger, driver-backed range controls, live Task-owned read-only values,
  statistics, trigger activity, and an automatically scaled graph.
- Added selectable 3½ through 6½-digit Mock DMM DC voltage modes from 2,000 to
  1,200,000 counts with range-dependent quantization and display precision.
- Added Raspberry Pi CPU temperature acquisition with two-decimal readings and
  optional secondary Task chart-axis assignment.
- Added automatic recovery of persisted Pending and Running Tasks after an
  application restart, preserving completed history and continuing at the next
  sample index.
- Added European Task CSV export with semicolon delimiters, decimal commas,
  millisecond ISO 8601 timestamps, and the Europe/Berlin UTC offset.

- Added an RND Lab 320-KA3005P DC power-supply driver for its documented
  9600-baud serial protocol, including identification, voltage and current
  programming, output control, readback, validation, and safe shutdown.
- Added read-only instrument details for all authenticated users and
  administrator-only inventory creation, editing, deletion, and driver tests.
- Added a required connection test before a new instrument configuration can
  be saved.
- Added keyboard and double-click row navigation to instrument and measurement
  lists.
- Added a task-level trigger clock with hour, minute, second, and hundredth
  controls. Continuous and Loop tasks now keep their requested trigger cadence
  without adding instrument communication time to every interval.
- Added an optional power-supply output-voltage readback after each task
  trigger, using the physical or Mock driver's measurement query.
- Added a live HH:MM:SS elapsed-time display to open task headers.
- Added a configurable task start delay after instrument preparation and before
  the first trigger.
- Added an optional Agilent 34401A and Keysight 34461A front-panel display-off
  setting for tasks, with automatic display restoration during cleanup.
- Added optional short task descriptions and selectable Single, Continuous,
  and Loop execution modes with mode-specific interval and measurement-count
  settings.
- Added owner-only task deletion with confirmation, active-task protection,
  cascading cleanup of stored readings, and immediate Task list updates.
- Added confirmation before stopping an active task and an owner-only action
  for marking a stopped task as completed.

### Changed

- Renamed the generic Mock instrument to Mock DMM, including its driver key and
  address scheme, with data migrations for existing inventory records.
- Instrument lists are now ordered by database ID and distinguish the
  management controls available to administrators from read-only access.
- Loop tasks now accept up to 10,000 requested measurements instead of 100.
- Simplified the new-task header by removing the generic Task settings heading
  and moving Stop beside the live task status.
- Completed tasks are now labelled consistently as Completed in the Task list.

### Fixed

- Continuous tasks no longer restart a completed finite PSU Sweep program;
  they finish as Completed at its final setpoint. Cycle count represents the
  exact number of complete return-to-start cycles.
- Marking a stopped task as Completed no longer clears its result table from
  the open task tab.
- RND KA3005P commands now observe the controller's processing interval so an
  output-voltage readback immediately after programming does not time out.
- Task runners now program the first PSU setpoint before enabling its output
  and allow the RND output to settle before readback, preventing a previous
  front-panel setpoint from appearing in the first sample.
- Power-supply setpoints and readbacks now use each driver's published voltage
  resolution in task tables and CSV exports instead of always showing six
  decimal places.
- PSU-only setpoint columns now retain driver voltage precision even when
  output readback is disabled.
- RND readbacks now consume their raw unterminated serial responses without
  waiting for a newline timeout on every sample.
- Task triggers now follow absolute monotonic deadlines and record the trigger
  instant before instrument communication, preventing timing drift from being
  accumulated across samples.
- Keysight 34461A task functions are now prepared before the trigger clock
  starts, removing one-time autorange configuration from the first sample.
- Newly created tasks now appear in the Task list immediately without a page
  reload.
- Task JavaScript assets now use cache-busting versions so interface changes
  are not hidden by stale browser caches.

## [0.0.8] - 2026-07-29

### Added

- Extended the Mock instrument with deterministic DC current, AC current, and
  temperature capabilities and realistic function-specific default readings.
- Added a separate Mock DC Power Supply driver with a programmable 0 to 60 V
  output, 1 mV resolution, output enable/disable control, setpoint readback,
  simulated terminal-voltage measurement, and safe disconnect behavior.
- Added a persistent Tasks workspace with Saved Tasks, internal New/Open tabs,
  a flexible instrument builder with nested configuration tabs, fixed, sweep,
  and cycle voltage programs, virtual or external DMM voltage sources, seeded
  bounded temperature generation, background execution, generic per-instrument
  readings, live stored results, explicit Stop, and guaranteed PSU cleanup.
- Added per-user profile controls for independently showing or hiding the top
  navigation bar and sidebar, choosing a left or right sidebar position, and
  using full-width content when the sidebar is off.

## [0.0.7] - 2026-07-27

### Fixed

- Replaced host-specific systemd units with a portable installer that detects
  the checkout path and service account, and made the documentation launcher
  read its host and port from the same `.env` file as the Django launcher.

## [0.0.6] - 2026-07-27

### Added

- Added a session-authenticated, CSRF-protected JSON API for instrument
  inventory list/detail, paginated stored measurements, and Single measurement
  execution through the existing measurement service.
- Added an authenticated streaming CSV export for stored measurements with
  instrument metadata, stable columns, UTF-8 support, and spreadsheet formula
  injection protection.
- Added CSV downloads for the results currently displayed in the Single,
  Continuous, and Loop measurement workflows.

### Changed

- Split dashboard, account, instrument, and measurement functionality into
  dedicated Django applications while preserving all existing URLs and
  database tables through a transitional `main` compatibility layer.
- Renamed the Single measurement path from `/measurements/new/` to
  `/measurements/single/` and removed the old route.
- Added a shared transport contract with reusable Serial/FTDI, Linux USBTMC,
  and in-memory Mock implementations. Instrument drivers now own SCPI policy
  while transports own device opening, byte transfer, decoding, and cleanup.
- Removed the legacy standalone Agilent reader and its model-specific transport
  adapter after preserving its 8N2 framing, timing, input cleanup, and bounded
  response polling in the shared serial transport and 34401A driver.

## [0.0.5] - 2026-07-27

### Added

- Added the `MeasurementRun` model for persistent Single, Continuous, and Loop
  configuration and lifecycle metadata, plus an optional transitional
  relationship from each `Measurement`.
- Added a central `DriverRegistry` with protected name registration and shared
  inventory-based driver construction, removing model-specific branching from
  the driver factory.
- Added a deterministic Mock instrument driver for development, demonstrations,
  complete measurement-service tests, and simulated timeout or connection
  failures without physical hardware.
- Added immutable driver capability metadata exposed through the registry and
  instrument model, server-side function validation, and a supported-functions
  table on each driver details page.
- Added autoranged AC voltage and two-wire resistance measurements to the
  Agilent 34401A, Keysight 34461A, and Mock drivers, including Single,
  Continuous, and Loop workflow support.

### Security

- Removed the committed Django secret key. Deployments must now provide a
  private `OIL_SECRET_KEY` environment variable.
- Disabled Django debug output by default. Local development must now opt in
  with `OIL_DEBUG=True`.
- Replaced the wildcard Django host policy with an explicit, required
  `OIL_ALLOWED_HOSTS` deployment setting.
- Removed the private deployment IP address from tracked scripts and
  documentation; server bind addresses are now configured through environment
  variables and default to localhost.
- Added a safe `.env.example` template and automatic local `.env` loading
  without overriding deployment environment variables.
- Removed the real installation path from tracked files. Launcher scripts now
  discover their own directory, and systemd examples use `/opt/oil`.

## [0.0.4] - 2026-07-26

### Added

- New measurement workflow for selecting an instrument, performing a DC voltage
  reading, and storing the normalized result with optional notes.
- Finite measurement loops with a selected count and interval, using one managed
  instrument connection for the complete series and displaying the resulting
  readings directly below the loop form.
- Live loop result streaming that appends each reading to the results table as
  soon as the instrument returns it.
- Loop configuration fields collapse after Start and remain visible as a
  two-row summary above the live result table.
- Continuous measurement with one connection and one instrument configuration,
  live stored results, an interruptible interval, and explicit Start and Stop
  controls.

### Changed

- Live loop success notifications now close automatically after four seconds,
  matching Django success messages elsewhere in the interface.
- Agilent 34401A measurements use the proven model-specific initialization,
  command sequence, and timing from the original standalone reader.
- Agilent serial connections allow the FTDI and instrument interface to settle
  before the first Remote command.
- The vendored Agilent reader uses the original half-second FTDI startup delay
  before entering Remote mode.
- Agilent RS-232 uses the manual-specified 8N2 framing; DC voltage measurements
  use autorange without forcing NPLC 100 and wait within a bounded response
  window.
- Agilent setup no longer performs and discards a warm-up conversion; repeated
  physical tests confirmed the first requested DCV Auto reading is reliable,
  reducing connection preparation by about one second.
- Agilent measurement sessions leave the front-panel display enabled, removing
  another half-second from connection setup and disconnect.
- Keysight 34461A measurements now use DC voltage autorange without forcing a
  10 V range or NPLC 100.
- Agilent DC voltage setup clears late FTDI input immediately before entering
  Remote mode, matching the original standalone reader.
- Agilent connections prepare DC voltage once when opened; Loop readings then
  send only `READ?`, matching the lifecycle of the proven standalone reader.
- Agilent connection setup enumerates FTDI ports before opening the configured
  device, matching the original reader's USB-serial discovery sequence.
- Agilent reads poll for completion within a bounded ten-second window instead
  of depending on a single fixed-time buffer check.
- Failed driver sessions now discard their cached connection so a later retry
  cannot reuse a desynchronized serial or USBTMC stream.
- Measurement actions are presented as Single, Continuous, and Loop workflows.

## [0.0.3] - 2026-07-26

### Added

- Instrument settings can be opened from the inventory and edited through the
  authenticated instrument form.
- Driver details and a connection/identification test are available from each
  instrument's driver link.
- Dashboard measurement summary and a dedicated Measurements page for stored
  instrument readings.
- Connect and Disconnect controls with Online or Reachable status on the
  Instruments page.

### Changed

- Success notifications can be dismissed manually and close automatically
  after four seconds.
- Driver connection tests now send only `*IDN?`; measurement configuration is
  deferred until an actual measurement is requested.
- DCV Auto mode tests verify command completion, the SCPI error queue, and the
  function/autorange state read back from the instrument.
- Agilent 34401A serial configuration avoids the blocking `*OPC?` path and uses
  error-queue plus setting read-back verification.
- Functional driver tests drain stale SCPI errors before attributing new errors
  to configuration commands.
- Both multimeter drivers return front-panel control with `SYST:LOC` before
  closing a connection.
- Dashboard Status distinguishes currently open connections from instruments
  reached successfully by their most recent driver test, without counting an
  online instrument in both groups.
- Process-local Connection Manager provides per-instrument locking, active
  connection reuse, and guaranteed cleanup for temporary driver sessions.

## [0.0.2] - 2026-07-26

### Added

- Testable Agilent 34401A serial/FTDI and Keysight 34461A USBTMC instrument
  drivers with a shared measurement contract.
- Dashboard instrument summary and a dedicated Instruments page for inventory
  browsing and authenticated instrument creation.

### Changed

- Renamed the Home page to Dashboard.

## [0.0.1] - 2026-07-26

### Added

- Project changelog.
- Locally hosted Bootstrap 5.3.7 assets for faster and offline page loading.
- User profiles for editing account details and choosing from seven persistent
  interface colour themes.
- Initial Django application with authenticated Home, About, and Contact pages.
- Login and CSRF-protected logout flows.
- Local development scripts and systemd service definitions for the application
  and documentation preview.
- MkDocs documentation covering installation, architecture, development, and
  the public Python API.
- GNU Affero General Public License, version 3 or later.

[Unreleased]: https://github.com/ebaketa/oil/compare/v0.0.8...HEAD
[0.0.8]: https://github.com/ebaketa/oil/compare/v0.0.7...v0.0.8
[0.0.7]: https://github.com/ebaketa/oil/compare/v0.0.6...v0.0.7
[0.0.6]: https://github.com/ebaketa/oil/compare/v0.0.5...v0.0.6
[0.0.5]: https://github.com/ebaketa/oil/compare/v0.0.4...v0.0.5
[0.0.4]: https://github.com/ebaketa/oil/compare/v0.0.3...v0.0.4
[0.0.3]: https://github.com/ebaketa/oil/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/ebaketa/oil/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/ebaketa/oil/releases/tag/v0.0.1
