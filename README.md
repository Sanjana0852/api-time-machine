# API Time Machine

A developer tool that compares API responses across versions and detects breaking changes, even when the API still returns HTTP 200.

For example, if an API used to return `"price": 250` and now returns `"price": "250"`, any app that does arithmetic on `price` will break. API Time Machine reports that as a **breaking** type change.

> **Status:** Phase 2 complete. Compare JSON files, replay live requests against two API versions, and use everything through a web API.

## Features

- **Comparison engine:** field-by-field diff of two JSON documents, classifying each change as breaking, safe or info ([design](docs/comparison-engine-design.md))
- **API replay:** fetch the same endpoint from an old and a new API version and compare bodies and status codes ([design](docs/api-replay-design.md))
- **Web API** (FastAPI): `/compare` and `/replay` over HTTP, with interactive docs
- **Safe by default:** replay only contacts hosts you allow, with read-only `GET` requests, a timeout and a size limit
- **Mock shop API** with `/v1` and `/v2` versions, for trying everything out locally

## Development setup (Windows PowerShell)

Requires Python 3.12+ and Git.

```powershell
# Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install the project in editable mode, plus development tools (pytest)
python -m pip install -e ".[dev]"

# Run the tests
python -m pytest
```

If activation fails with "running scripts is disabled on this system", run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then try again.

## Usage

### 1. Compare two JSON files

```powershell
python -m api_time_machine compare examples\product_v1.json examples\product_v2.json
```

```
BREAKING  $.price              type changed: integer -> string  (250 -> "250")
INFO      $.stock              value changed: 12 -> 9
SAFE      $.rating             type changed: float -> integer  (4.5 -> 4)
SAFE      $.discount           type changed: null -> integer  (null -> 10)
BREAKING  $.seller.id          field removed
BREAKING  $.seller.verified    type changed: boolean -> null  (true -> null)
INFO      $.tags[2]            item added (string)
BREAKING  $.variants[0].price  type changed: integer -> float  (250 -> 250.5)
SAFE      $.delivery_days      field added (integer)

9 changes: 4 breaking, 3 safe, 2 info
```

### 2. Replay requests against two API versions

Start the mock shop API in one terminal (leave it running):

```powershell
python -m uvicorn api_time_machine.mock_api:app --port 8001
```

In a second terminal (with the virtual environment activated):

```powershell
python -m api_time_machine replay http://localhost:8001/v1/products/101 http://localhost:8001/v2/products/101
```

```
Old: HTTP 200  http://localhost:8001/v1/products/101
New: HTTP 200  http://localhost:8001/v2/products/101

BREAKING  $.price              type changed: integer -> string  (250 -> "250")
...
9 changes: 4 breaking, 3 safe, 2 info
```

A status code that goes from success to failure (e.g. `200 -> 404`) is also reported as breaking.

### 3. Web API

With the mock API still running on port 8001, start the web API in another terminal:

```powershell
python -m uvicorn api_time_machine.api:app --port 8000
```

Interactive documentation, where you can try every endpoint: http://localhost:8000/docs

| Endpoint | Body | Returns |
|---|---|---|
| `GET /health` | | `{"status": "ok"}` |
| `POST /compare` | `{"old": <JSON>, "new": <JSON>}` | The changes and a summary |
| `POST /replay` | `{"old_url": "...", "new_url": "..."}` | Both status codes, the changes and a summary |

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/compare `
  -ContentType "application/json" `
  -Body '{"old": {"price": 250}, "new": {"price": "250"}}' | ConvertTo-Json -Depth 5
```

Errors: `422` malformed request, `400` URL refused by a safety rule, `502` the target server failed or didn't return JSON.

### Exit codes (CLI)

| Code | Meaning |
|---|---|
| `0` | No breaking changes |
| `1` | At least one breaking change |
| `2` | Could not compare (missing file, invalid JSON, blocked URL, unreachable server, wrong arguments) |

The exit code lets scripts and CI pipelines fail a build when an API change would break clients.

## Configuration

| Environment variable | Default | Meaning |
|---|---|---|
| `ATM_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hosts that replay may contact. Set but empty means none. |

```powershell
$env:ATM_ALLOWED_HOSTS = "localhost,127.0.0.1,api.staging.example.com"
```

Only add hosts you have permission to send requests to. The allowlist also protects the web API from being used to reach internal addresses (SSRF). See the [safety rules](docs/api-replay-design.md#4-safety-rules-for-outgoing-requests).

## Project structure

```
src/api_time_machine/
├── models.py      data types and json_type()
├── rules.py       severity rules (breaking / safe / info)
├── diff.py        compare(): the recursive comparison
├── report.py      text reports
├── jsonparse.py   strict JSON parsing shared by every input
├── config.py      settings from environment variables
├── fetch.py       safe HTTP fetching (the security boundary)
├── replay.py      fetch two URLs concurrently and compare
├── api.py         FastAPI web API
├── mock_api.py    mock shop API with v1 and v2 (development only)
└── cli.py         command line: compare and replay
```

## Roadmap

- [x] Phase 1: comparison engine and CLI
- [x] Phase 2: API replay, mock API and web API
- [ ] Phase 3: store comparison history in PostgreSQL
- [ ] Phase 4: React + TypeScript dashboard
- [ ] Phase 5: AI explanations of the impact of changes
- [ ] Phase 6: Docker and GitHub integration

The full plan is in [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md).
