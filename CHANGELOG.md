# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/ebaketa/oil/compare/v0.0.2...HEAD
[0.0.2]: https://github.com/ebaketa/oil/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/ebaketa/oil/releases/tag/v0.0.1
