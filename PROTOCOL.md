# PROTOCOL.md: how the Urja Meter Ops portal works

Everything here was found by using the portal as a normal logged-in user
(browser DevTools, then scripts in `scripts/`). Nothing was attacked or modified.
Portal: https://urja-ops.flockenergy.tech

## 1. Stack and authentication

- The portal is a **SvelteKit** app. Sessions use a cookie named
  `__Secure-better-auth.session_token` (the Better Auth library); it is Secure,
  HttpOnly, SameSite=Lax and the browser showed about 1 hour of lifetime.
- **Login:** `POST /login` as an HTML form (`email`, `password`).
  - It needs an `Origin` header equal to the portal's own address. Without it the
    answer is **403 "Cross-site POST form submissions are forbidden"** (SvelteKit's
    CSRF check). A browser sends it automatically; `requests` does not.
  - Success is **HTTP 200** with the body `{"type":"redirect","status":303,"location":"/meters"}`.
    The redirect is inside the body, not an HTTP redirect, so read the body and the cookie.
- **No session:** data endpoints answer **401** with
  `{"error":"unauthorized","message":"A valid session is required."}`. The service
  logs in again once and retries when it sees this.

## 2. Endpoints

| Purpose                    | Request                                                    | Notes                                   |
| -------------------------- | ---------------------------------------------------------- | --------------------------------------- |
| Login                      | `POST /login`                                              | form fields, `Origin` header required   |
| Meter list / search        | `GET /portal/meters/search?q=&page=N`                      | JSON, 20 per page                       |
| Energy readings            | `GET /portal/meters/{id}/energy[?from=&to=]`               | JSON                                    |
| Location                   | `GET /portal/meters/{id}/geo`                              | `{"data":{"latitude","longitude"}}`     |
| Transformer (DT) list      | `GET /portal/dts?page=N`                                   | JSON, 20 per page                       |
| Meter detail and hierarchy | `GET /meters/{id}/__data.json?x-sveltekit-invalidated=001` | SvelteKit page data, outside `/portal/` |

The page `/meters/{id}` renders location and consumption after load, which is how
the `energy` and `geo` calls were found in the Network tab.

## 3. Data, endpoint by endpoint

### Meter list

- 403 meters, `J100000` to `J100402`: no duplicates, no gaps, no empty fields.
- Fields: `meterId`, `serialNo`, `make` (5 values), `phaseType` (single/three),
  `installStatus` (Installed 238, Faulty 90, Decommissioned 75), `dtCode`.
- Response also has `total`, `page`, `pageSize` (always 20; a `pageSize` parameter is ignored).
- Past the last page the portal returns **200 with `"data": []`**, not an error.
- `q` is a **case-insensitive substring match on meter ID and serial number only**.
  Make, DT code and status are not searched, so filtering on those is done locally.
- Meters per DT: 10 to 13. Serial prefixes do not correspond to the make.

### Transformers

- 40 DTs (`DT-001` to `DT-040`) with `code`, `name`, `feederCode`, `capacityKva`.
- `capacityKva` is a real number while most other numbers in the portal are strings.
- Only 28 distinct feeders: some DTs share a feeder.
- This list only goes DT -> feeder; the rest of the chain comes from the meter pages.

### Energy

- Every value is a **string** (`"kwh": "42594.05"`), and timestamps are
  **`DD/MM/YYYY HH:mm` with no timezone**.
- `kwh` and `kvah` are **cumulative registers**, not usage. Usage in an interval is
  the difference between consecutive readings. Only `voltR` is reported, even for the
  three-phase meter tested (J100005).
- **Default window: the last 7 days** (337 half-hourly readings, 23/06 23:30 to 30/06 23:30).
- `from` and `to` take **ISO dates (`YYYY-MM-DD`), inclusive whole days**. `days` and
  `page` are ignored. `from=2026-06-25&to=2026-06-27` gives 144 rows (3 days x 48).
- Data runs **01/06/2026 to 30/06/2026** (1440 rows for a wide range). `to=2026-06-03`
  starts at 01/06, so 1 June is the real start, not a row cap.
- The portal does **not validate dates**: `25/06/2026` and `not-a-date` return the
  default window with 200, and a reversed range returns 200 with an empty list.
- **Reading interval depends on the meter.** In a sample of every 8th meter,
  J100000 to J100032 report every 30 minutes (337 rows) and J100040 to J100400 report
  once a day at 00:00 (8 rows). It does not depend on phase or status. The exact boundary
  between the two groups was not located.
- The cumulative registers never decreased in the meters checked.
- The latest reading is 30/06/2026 23:30 while the server's own clock says October 2026,
  so the data is a **static snapshot**.

### Location

- Latitude and longitude are strings. A sample of every 10th meter had no missing or
  unparseable coordinates. The coordinates are around Jaipur.

### Meter detail and hierarchy (`__data.json`)

- The response uses SvelteKit's compact format: one flat array in which objects hold
  **indexes** into the array instead of values, and repeated values are stored once.
  `app/decoder.py` follows the indexes recursively. Negative indexes (SvelteKit's
  special values) are read as null; no other special encodings were seen.
- **The detail block comes in two shapes** (found when a crawl crashed on 165 of 403 meters):
  - Shape A (238 meters): a list of `{parameterName, parameterValue}` pairs.
  - Shape B (165 meters): `{"classData": "<JSON string>"}`, **double-encoded**, with
    different key names (`SerialNo`, `PhaseType`, `InstallationStatus`, `InstallationType`).
  - Nothing says which shape a meter gets, so the decoder detects it and fails loudly on a third.
- `Installation Type` (Whole Current 205, CT Operated 198) exists **only** on this page.
- The hierarchy is an object of display strings, `"Name (CODE)"`: Zone, Circle, Division,
  Subdivision, `Sub Station` (with a space), Feeder, DT. It repeats three fields that are
  already in the detail block.
- Serial, make, phase, status and DT on the page matched the list for all 403 meters.
- **22 meters have damaged hierarchy labels**: Circle on 11, Feeder on 8, Sub Station on 3.
  Damage is either blank (`""`) or a name without its code (`"Circle 6"`).
- Across all 403 meters, **no DT has two different real values at any level**; the only
  differences are the damaged labels. Every level of every DT is reported by at least one
  of its meters. The service therefore fills a damaged level from the same DT's other meters
  and marks it `inferred: true`.
- **A missing meter returns HTTP 200** with an error node inside the data
  (`"type":"error","error":{"message":"Meter not found"},"status":404`). The `energy` and
  `geo` endpoints return a real 404 (`{"error":"not_found","message":"Meter not found"}`).

## 4. Quirks and surprises, in one place

1. Login answers 200 with a redirect in the body, and needs `Origin`.
2. Detail data has two shapes, one of them double-encoded JSON.
3. The meter page reports "not found" with HTTP 200.
4. Damaged hierarchy labels on 22 meters.
5. Half-hourly and daily meters mix, so the interval cannot be assumed.
6. Timestamps have no timezone, and the formats mix `DD/MM/YYYY HH:mm` (readings) with
   `YYYY-MM-DD` (query parameters).
7. The portal ignores invalid input instead of rejecting it.
8. The default energy window is 7 days, but 30 days are available with `from`/`to`.
9. Numbers are strings except `capacityKva`.
10. `__data.json` is sent with `Cache-Control: private, no-store`.

## 5. Rate limiting

- About 85 to 100 consecutive energy requests (at 0.1 s and later 0.25 s spacing)
  produced **HTTP 429**, even with exponential backoff. The 403-page hierarchy crawl at
  0.2 s was never limited, so the limit may only apply to the energy endpoint.
- The portal sends **no rate-limit headers** (no `Retry-After`, no `X-RateLimit-*`), even
  on normal responses. The client waits for `Retry-After` if one ever arrives and otherwise
  backs off exponentially.
- The limit had cleared a few minutes later, including after a fresh login. Window size
  and whether it is per session, user or IP were not measured.

## 6. Not verified

- The exact rate-limit window and scope.
- Where the half-hourly and daily meters split (only every 8th meter was sampled).
- Whether three-phase meters ever report voltages other than `voltR`.
- The timezone of the timestamps. The service assumes UTC+05:30 (the utility is in India).
- Geo values for every meter (only a sample was checked).
- The `/transformers` page of the UI; the DT data came from `/portal/dts`.
