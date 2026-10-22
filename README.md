# API Time Machine

A developer tool that compares API responses across versions and detects breaking changes, even when the API still returns HTTP 200.

For example, if an API used to return `"price": 250` and now returns `"price": "250"`, any app that does arithmetic on `price` will break. API Time Machine reports that as a **breaking** type change.

> **Status:** Phase 1 complete: the comparison engine and command-line tool work.

## Usage

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

| Exit code | Meaning |
|---|---|
| `0` | No breaking changes |
| `1` | At least one breaking change |
| `2` | Could not compare (missing file, invalid JSON, wrong arguments) |

The exit code lets scripts and CI pipelines fail a build when an API change would break clients. The severity rules are explained in [docs/comparison-engine-design.md](docs/comparison-engine-design.md#5-severity-rules).

## Features

- **Comparison engine** (done): field-by-field diff of two JSON responses, classifying each change as breaking, safe or informational

## Planned

- **API replay:** send the same request to two API versions and compare the results
- **History:** store past comparisons in PostgreSQL
- **Dashboard:** React + TypeScript UI for running and browsing comparisons
- **AI explanations:** optional plain-English impact summaries, layered on top of the deterministic results

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

## Project plan

See [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md) for the architecture, phases and setup steps.
