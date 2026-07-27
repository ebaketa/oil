# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/ebaketa/oil/compare/v0.0.7...HEAD
[0.0.7]: https://github.com/ebaketa/oil/compare/v0.0.6...v0.0.7
[0.0.6]: https://github.com/ebaketa/oil/compare/v0.0.5...v0.0.6
[0.0.5]: https://github.com/ebaketa/oil/compare/v0.0.4...v0.0.5
[0.0.4]: https://github.com/ebaketa/oil/compare/v0.0.3...v0.0.4
[0.0.3]: https://github.com/ebaketa/oil/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/ebaketa/oil/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/ebaketa/oil/releases/tag/v0.0.1
