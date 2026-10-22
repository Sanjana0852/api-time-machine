# API Replay: Design

**Status:** proposed (Phase 2)

Phase 1 compares two JSON **files**. Phase 2 lets the tool fetch the two responses itself: send the same request to an old and a new version of an API, then compare what comes back. It also exposes the engine as a **web API**, which the dashboard (Phase 4) will use.

The comparison engine from Phase 1 is reused unchanged. Phase 2 only adds new ways to get JSON *into* it.

---

## 1. Goals and non-goals

**Goals**

- A **mock API** with `/v1` and `/v2` versions that differ on purpose, so all development and demos run against our own server, never someone else's
- **Replay:** fetch two URLs and compare the responses, including their HTTP status codes
- A **web API** (FastAPI) exposing comparison and replay over HTTP
- A **`replay` command** in the CLI
- **Safe by default:** the tool can only reach hosts you explicitly allow, only with read-only requests, and with limits on time and size

**Non-goals for Phase 2**

- Saving results (Phase 3)
- A user interface (Phase 4)
- Requests other than `GET`, custom headers, or authentication
- Replaying many endpoints in one run

---

## 2. The pieces

```
                         ┌──────────────────────────┐
  you ── CLI ───────────▶│ replay()                 │
                         │  fetch both URLs         │──▶ compare()  (Phase 1)
  browser/dashboard ──▶  │  at the same time        │
     web API (api.py)    └────────────┬─────────────┘
                                      │ HTTP GET, via fetch_json()
                                      ▼
                         ┌──────────────────────────┐
                         │ mock API (mock_api.py)   │
                         │  /v1/products/{id}       │
                         │  /v2/products/{id}       │
                         └──────────────────────────┘
```

| Module | Job |
|---|---|
| `mock_api.py` | A small demo API, run on port 8001. `/v1` and `/v2` serve the same products with deliberate changes between versions. |
| `config.py` | Reads settings (the allowed hosts) from environment variables. |
| `fetch.py` | `fetch_json(client, url)`: one safe HTTP GET. This is the security boundary: every rule in section 4 is enforced here. |
| `replay.py` | `replay(old_url, new_url)`: fetches both URLs concurrently and compares them. |
| `api.py` | The FastAPI web app, run on port 8000: `/health`, `/compare`, `/replay`. |
| `cli.py` | Gains a `replay` subcommand next to `compare`. |

**Dependencies still point one way:** `api` and `cli` → `replay` → `fetch` → `config`, and `replay` → `diff` → `rules` → `models`. The engine never imports anything web-related.

---

## 3. New technologies

| Tool | What it is | Why we need it |
|---|---|---|
| **FastAPI** | A Python framework for building web APIs | Defines endpoints as plain Python functions. Validates request data automatically from type hints and generates interactive docs at `/docs`. |
| **Uvicorn** | A web server that runs FastAPI apps | FastAPI describes *what* to do with a request; Uvicorn listens on a port and delivers the requests. |
| **httpx** | A Python HTTP client | Sends requests and reads responses. Supports async, and ships a fake "transport" so tests never touch the real network. |
| **Pydantic** | Data validation from type hints (comes with FastAPI) | Turns incoming JSON into checked Python objects, with clear errors for bad input. |

---

## 4. Safety rules for outgoing requests

A tool that fetches URLs is risky in two ways:

1. **Hitting systems you don't own.** Replaying requests against someone else's API without permission can overload it or break their terms of service.
2. **SSRF (Server-Side Request Forgery).** Once the web API accepts URLs, *anyone who can call it* can make the server send requests. An attacker could point it at internal addresses only the server can reach, such as a cloud provider's metadata service at `169.254.169.254`, which can hand out credentials.

`fetch_json` enforces these rules on every request:

| # | Rule | Why |
|---|---|---|
| S1 | **Host allowlist.** Only hosts listed in `ATM_ALLOWED_HOSTS` can be contacted. The default is `localhost,127.0.0.1`. | Blocks both risks above. An allowlist (list what *is* allowed) is safer than a blocklist (list what isn't), because a blocklist always forgets something. |
| S2 | **Only `http` and `https` URLs.** | Rejects `file://`, `ftp://` and other schemes. |
| S3 | **Only `GET` requests.** | Replay must be read-only. A `POST` or `DELETE` replayed against a real API could create orders or delete data. |
| S4 | **Redirects are not followed.** | A redirect could send the request to a host that isn't allowed, bypassing S1. A redirect shows up as its 3xx status code instead. |
| S5 | **10-second timeout.** | A slow or hung server can't make the tool (or the web server) wait forever. |
| S6 | **5 MB response limit.** | A huge response can't exhaust memory. The download stops as soon as the limit is passed. |

Any rule violation, network failure or non-JSON response raises a `FetchError` with a message saying what went wrong and which URL.

**Configuration:** settings come from **environment variables**, values set outside the code (in the terminal, or by the server's host). This keeps machine-specific and sensitive settings out of the source code. Phase 3 adds a database password the same way.

```powershell
$env:ATM_ALLOWED_HOSTS = "localhost,127.0.0.1,api.staging.example.com"
```

---

## 5. Replay

```python
async def replay(old_url: str, new_url: str, client: httpx.AsyncClient) -> ReplayResult
```

1. Fetch both URLs **at the same time** with `asyncio.gather`, so waiting on two servers takes as long as the slower one, not the sum of both.
2. Compare the two bodies with `compare()` from Phase 1.
3. Compare the two **status codes**.

```python
@dataclass(frozen=True)
class FetchedResponse:
    url: str
    status_code: int
    body: JsonValue

@dataclass(frozen=True)
class ReplayResult:
    old: FetchedResponse
    new: FetchedResponse
    status_severity: Severity | None   # None if the status codes are equal
    changes: list[Change]             # differences between the bodies
```

The `client` is passed in rather than created inside `replay`. Tests can then pass a client with a fake transport. This is called **dependency injection**: a function receives the things it depends on instead of building them itself.

### Status code rule

This lives in `rules.py` with the other severity rules.

| # | Status change | Severity | Why |
|---|---|---|---|
| R10 | Same status code | (no change) | |
| R11 | Success (2xx) → anything else | **breaking** | The endpoint used to work and now doesn't, e.g. `200 → 404`. |
| R12 | Any other difference | **info** | e.g. `200 → 201`, or `500 → 200` (it got fixed). |

A replay counts as breaking if the status change or any body change is breaking.

**Limitation:** both responses must have JSON bodies. If one returns HTML (say, a proxy error page), replay reports a `FetchError` with that response's status code instead of a comparison. FastAPI's own errors, like 404, are JSON, so they compare normally.

---

## 6. Mock API

`python -m uvicorn api_time_machine.mock_api:app --port 8001`

| Endpoint | Returns |
|---|---|
| `GET /v1/products/{id}` | A product in the v1 format |
| `GET /v2/products/{id}` | The same product in the v2 format |
| `GET /v1/products`, `GET /v2/products` | All products |

Products `101` and `102` exist; any other ID returns `404`. The v2 changes are the same ones as `examples/product_v2.json`, and a test keeps the two in sync. So the CLI on files and a replay against the mock API give the same report.

It's development tooling: it lives in the package so it's one command to run, but it is not part of the product.

---

## 7. Web API

`python -m uvicorn api_time_machine.api:app --port 8000`, with interactive docs at http://localhost:8000/docs.

| Method & path | Body | Returns |
|---|---|---|
| `GET /health` | | `{"status": "ok"}`. Lets tools (and Docker in Phase 6) check the server is alive. |
| `POST /compare` | `{"old": <any JSON>, "new": <any JSON>}` | The changes and a summary. No network involved. |
| `POST /replay` | `{"old_url": "...", "new_url": "..."}` | Both status codes, the changes and a summary |

**Response shape** (both endpoints):

```json
{
  "changes": [
    {"path": "$.price", "kind": "type_changed", "severity": "breaking",
     "old_value": 250, "new_value": "250"}
  ],
  "summary": {"total": 1, "breaking": 1, "safe": 0, "info": 0, "has_breaking": true}
}
```

`/replay` also includes `"old": {"url", "status_code"}`, `"new": {...}` and `"status_severity"`.

**Errors:** HTTP status codes tell the caller what kind of problem happened.

| Situation | Status | Why this code |
|---|---|---|
| Request body is malformed or missing fields | `422 Unprocessable Content` | FastAPI's automatic validation |
| URL breaks a safety rule (e.g. host not allowed) | `400 Bad Request` | The caller asked for something not permitted |
| The target server failed, timed out, or didn't return JSON | `502 Bad Gateway` | We're acting as a gateway, and the server behind us misbehaved; it's not the caller's fault |

---

## 8. CLI

```
python -m api_time_machine replay http://localhost:8001/v1/products/101 http://localhost:8001/v2/products/101
```

The same report as `compare`, preceded by both status codes, and the same exit codes: `0` no breaking changes, `1` breaking, `2` error (including safety-rule violations).

---

## 9. Testing strategy

- **No real network in unit tests.** `fetch_json` and `replay` are tested with `httpx.MockTransport`, a fake that answers requests from a Python function. These tests are fast, deterministic, and work offline.
- **FastAPI apps are tested with `TestClient`**, which calls the app in-process without starting a server.
- **One manual end-to-end check** per step: start the mock API, replay against it, and look at the result.

---

## 10. Implementation plan

1. **Mock API:** install FastAPI and Uvicorn, serve `/v1` and `/v2` products, test with `TestClient`, open `/docs` in a browser
2. **Safe fetching:** `config.py` and `fetch.py` with rules S1–S6, tested with `MockTransport`
3. **Replay:** `replay()`, status rules R10–R12, and the CLI `replay` command; try it against the running mock API
4. **Web API:** `/health`, `/compare`, `/replay`, request/response validation and error mapping
5. **Wrap-up:** README instructions for running both servers, then merge
