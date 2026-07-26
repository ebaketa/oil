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

The project currently uses SQLite for local development. Models, services,
instrument drivers, and measurement workflows will be documented when they
are introduced.

## Access control

Home, Contact, and About require an authenticated user. Anonymous requests are
redirected to `/accounts/login/`. Logout accepts POST requests with CSRF
protection and redirects to the login page.

Authenticated users can open their profile by selecting their username. The
profile supports changes to account details and the interface colour theme.
Updates accept POST requests with CSRF protection, validate all fields, and
store theme choices separately for each user.
