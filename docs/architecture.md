# Architecture

```text
Browser → Django authentication → URL configuration → Views → Templates
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
- `drivers` contains hardware communication isolated from Django models and
  views. The first drivers support the Agilent 34401A over serial/FTDI and the
  Keysight 34461A over Linux USBTMC.

The project currently uses SQLite for local development. Hardware connection
services and measurement workflows will be documented when they are introduced.

## Instrument drivers

Both digital multimeter drivers implement the same lifecycle and measurement
contract. Device addresses and measurement settings are supplied when a driver
is created; importing a driver never opens hardware. Drivers support context
managers so connections are closed after successful operations and exceptions.

Hardware-independent unit tests use simulated serial and USBTMC connections.
Application views do not communicate with either instrument directly.

## Instrument inventory

Authenticated users open the dedicated Instruments page to view the shared
inventory or add a laboratory instrument. The Dashboard only shows summary
counts and links to the inventory. New instruments start offline; creating an
inventory record never opens a hardware connection.

## Access control

Dashboard, Contact, and About require an authenticated user. Anonymous requests are
redirected to `/accounts/login/`. Logout accepts POST requests with CSRF
protection and redirects to the login page.

Authenticated users can open their profile by selecting their username. The
profile supports changes to account details and the interface colour theme.
Updates accept POST requests with CSRF protection, validate all fields, and
store theme choices separately for each user.
