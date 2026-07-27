# JSON API

OIL exposes a session-authenticated JSON API under `/api/`. It uses the same
forms, measurement service, connection manager, and drivers as the HTML
interface.

## Authentication and CSRF

API requests use the existing Django login session. Anonymous requests return:

```json
{"error": "Authentication is required."}
```

with HTTP status `401`. API requests are not redirected to the HTML login page.

Read-only `GET` requests require the session cookie. The Single measurement
`POST` additionally requires Django's CSRF cookie and matching `X-CSRFToken`
header. This prevents another website from starting hardware activity through
an authenticated browser session.

## Instruments

### List instruments

```http
GET /api/instruments/
```

The response contains `count` and `results`. Each result includes inventory
identity, driver, address, persisted status, current process-local online state,
description, and timestamps.

### Instrument details

```http
GET /api/instruments/12/
```

The detail response additionally contains the selected driver's capability
metadata. Functions include their label, unit, autorange support, ranges, and
NPLC values.

## Measurements

### List measurements

```http
GET /api/measurements/?limit=50&offset=0
```

`limit` defaults to 50 and must be between 1 and 100. `offset` defaults to zero.
The response contains:

```json
{
  "count": 1,
  "limit": 50,
  "offset": 0,
  "results": [
    {
      "id": 458,
      "run_id": null,
      "instrument_id": 12,
      "instrument": "Reference DMM",
      "parameter": "Voltage DC",
      "value": 1.2345,
      "unit": "V",
      "timestamp": "2026-07-27T20:15:30+00:00",
      "notes": "Reference input"
    }
  ]
}
```

### Perform a Single measurement

```http
POST /api/measurements/single/
Content-Type: application/json
X-CSRFToken: <csrf-cookie-value>

{
  "instrument_id": 12,
  "function": "dc_voltage",
  "notes": "Reference input"
}
```

The function must be both a valid OIL measurement choice and a capability of
the selected instrument. Successful requests return the stored measurement
with HTTP status `201`.

Malformed JSON, invalid identifiers, unsupported functions, and invalid notes
return status `400` with JSON validation details. Driver or communication
failures return status `502` and do not create a measurement record.

## Current scope

The initial API intentionally exposes inventory reads, measurement reads, and
Single measurements. Connect, Disconnect, Continuous, and Loop operations
remain in the HTML application until their longer-running lifecycle and
authorization rules are represented safely in the API.
