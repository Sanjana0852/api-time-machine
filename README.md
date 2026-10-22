# API Time Machine

A developer tool that compares API responses across versions and detects breaking changes, even when the API still returns HTTP 200.

For example, if an API used to return `"price": 250` and now returns `"price": "250"`, any app that does arithmetic on `price` will break. API Time Machine reports that as a **breaking** type change.

> **Status:** early development (Phase 0: project setup).

## Planned features

- **Comparison engine:** field-by-field diff of two JSON responses, classifying each change as breaking, safe or informational
- **API replay:** send the same request to two API versions and compare the results
- **History:** store past comparisons in PostgreSQL
- **Dashboard:** React + TypeScript UI for running and browsing comparisons
- **AI explanations:** optional plain-English impact summaries, layered on top of the deterministic results

## Project plan

See [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md) for the architecture, phases and setup steps.
