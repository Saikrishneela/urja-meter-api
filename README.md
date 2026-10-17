# Urja Meter API

A clean JSON API in front of the legacy _Urja Meter Ops_ portal
(https://urja-ops.flockenergy.tech), which has no API of its own.

- **How the portal works:** [PROTOCOL.md](PROTOCOL.md)
- **API description:** [openapi.json](openapi.json), also rendered live at `/docs` when the server runs
- **Reflection:** the last section of this file

## What it does

| Endpoint                                        | Returns                                                                             |
| ----------------------------------------------- | ----------------------------------------------------------------------------------- |
| `GET /meters`                                   | Paged list; filter by `q` (ID or serial), `make`, `status`, `phase_type`, `dt_code` |
| `GET /meters/{id}`                              | Meter detail: nameplate, installation type, 7-level hierarchy, location             |
| `GET /meters/{id}/location`                     | Latitude and longitude as numbers                                                   |
| `GET /meters/{id}/energy?from=&to=`             | Readings with ISO timestamps, numbers, and per-interval usage                       |
| `GET /transformers`, `GET /transformers/{code}` | Distribution transformers and their meters                                          |
| `GET /health`                                   | Liveness check (does not call the portal)                                           |

## Structure

```
app/
  portal_client.py  login, session renewal, throttling, retries, error types
  decoder.py        decodes SvelteKit's __data.json into meter detail + hierarchy
  transform.py      pure functions: hierarchy repair, timestamps, interval usage
  service.py        caching and combining portal calls into API objects
  models.py         response models (these produce openapi.json)
  main.py           FastAPI routes and error mapping
scripts/            the throwaway probes used to investigate the portal
tests/              13 tests (pytest)
```

The layers only depend downward: `main` -> `service` -> `portal_client`/`transform`.
Only `portal_client` knows about cookies, `Origin` headers or SvelteKit.

## Setup and run

Requires Python 3.11+.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
Copy-Item .env.example .env         # macOS/Linux: cp .env.example .env
# edit .env and fill in URJA_EMAIL and URJA_PASSWORD (given in the assignment)
python -m uvicorn app.main:app
```

Open http://127.0.0.1:8000/docs. Run the tests with `python -m pytest`.
Regenerate the spec with `python -m scripts.export_openapi`.

## Sample requests

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/meters?make=Genus&status=Faulty&limit=3"
Invoke-RestMethod "http://127.0.0.1:8000/meters/J100011"
Invoke-RestMethod "http://127.0.0.1:8000/meters/J100002/energy?from=2026-06-25&to=2026-06-26"
```

`GET /meters/J100011` returns the hierarchy with one repaired level:

```json
{ "level": "Circle", "name": "Circle 6", "code": "C-06", "inferred": true }
```

## Assumptions

1. **Timezone is UTC+05:30.** The portal gives none; the coordinates are in Jaipur.
   India has no daylight saving, so a fixed offset is exact. It is reported in the response.
2. **`kwh`/`kvah` are cumulative registers**, so usage is the difference between readings.
3. **Hierarchy gaps can be repaired from sibling meters.** I checked all 403 meters:
   no transformer has two different real values at any level, and every level of every
   transformer is reported by at least one meter.
4. **Not-found on the meter page** (HTTP 200 with an error node) means the meter does not exist.
5. **The portal's data is a static snapshot** (June 2026), so caching is safe.

## Design decisions and trade-offs

- **Eager list, lazy detail.** The meter list and DT list (23 requests) load on first use.
  Per-meter data is fetched when asked and cached. Fetching all 403 detail pages up front
  costs about 2 minutes and the portal rate-limits, so the first request is slow and the rest are fast.
- **Filters the portal cannot do** (make, status, phase, DT) run locally on the cached list,
  because the portal's search only matches ID and serial.
- **Repaired values are labelled** with `inferred: true`, so a consumer can tell portal data
  from reconstructed data. Conflicting levels would never be filled (unit tested).
- **Raw and derived values both returned** (`kwh_register` and `kwh_interval`).
  A register that goes backwards gives a null interval instead of a negative one.
- **Interval is computed from timestamps**, because some meters report every 30 minutes and
  others once a day.
- **Date validation in our layer,** because the portal silently ignores bad dates.
- **Errors:** 404 unknown meter, 422 bad input, 503 plus `Retry-After` when the portal is
  down or rate-limiting, 502 when the portal rejects our credentials.
- **Resilience in the client:** lazy login, one re-login on 401, a minimum gap between requests,
  `Retry-After`-aware backoff on 429, retries for timeouts and 5xx.
- **One lock around portal calls.** The portal rate-limits and the client is not thread-safe.
  This serialises cache misses; cache hits are not blocked.
- **In-memory TTL cache (15 minutes).** No database or Docker: simple to run, lost on restart.

## Intentionally left out

- Persistent storage or a background refresh job.
- Authentication on this API itself.
- The optional web client, spatial queries ("meters near here") and the full-dataset export.
- Integration tests against the live portal (unit tests use fakes, so they are fast and offline).

## What I would improve with more time

- Measure the rate limit properly and pre-warm the cache in a background task.
- Find exactly where half-hourly meters stop and daily ones begin.
- Persist the cache (SQLite) and expose a "data as of" timestamp.
- Contract tests against recorded portal responses; per-request portal-call metrics.
- A spatial endpoint and a map view of meters.

## Reflection

### What assumptions did you make?

(write in your own words)

### Which part was the most difficult, and how did you get unstuck?

(write in your own words)

### If you had another day, what would you improve?

(write in your own words)

### What mistake did you make while solving this?

(write in your own words)

### If you were reviewing your own submission, what would you criticise?

(write in your own words)
