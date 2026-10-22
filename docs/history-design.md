# Comparison History: Design

**Status:** proposed (Phase 3)

Until now, every comparison disappears as soon as it is printed. Phase 3 **saves replay runs in a PostgreSQL database**, so you can answer questions like:

- *When* did `/products/101` start returning `price` as a string?
- Which runs had breaking changes this week?
- What exactly did the API return at the time? (the "time machine" part)

The comparison engine, replay and safety rules from Phases 1–2 are reused unchanged.

---

## 1. Goals and non-goals

**Goals**

- Save a replay run, including both responses, all changes and a summary
- List past runs (newest first), optionally filtered by a **label** such as `products-detail`
- Fetch one past run with all its details
- Expose this through the web API and the CLI
- **History is optional:** without a database configured, everything from Phases 1–2 keeps working exactly as before

**Non-goals for Phase 3**

- Saving file comparisons (`compare`). History is about API versions over time, which is what replay measures.
- Scheduling runs automatically (Phase 6 can run them from CI)
- Deleting runs or retention policies, users and authentication

---

## 2. New technologies

| Tool | What it is | Why we need it |
|---|---|---|
| **PostgreSQL** | A relational database server | Stores data permanently and lets us query it with SQL. It has a native `JSONB` type, ideal for storing API responses. |
| **SQLAlchemy 2** | Python's standard database toolkit, including an **ORM** (Object-Relational Mapper) | Lets Python code work with table rows as typed Python objects, and builds safe SQL for us (no string-pasted SQL, so no SQL injection). |
| **psycopg 3** | The PostgreSQL driver for Python | The low-level connection SQLAlchemy uses to talk to PostgreSQL. The `[binary]` variant bundles everything needed on Windows. |
| **Alembic** | Database migrations for SQLAlchemy | Records every change to the table structure as a versioned script in Git, so any database can be brought up to date with one command. |
| **python-dotenv** | Loads a `.env` file into environment variables | So the database password lives in a local `.env` file (ignored by Git) instead of being typed in every terminal or written in code. |

---

## 3. Data model

Two tables. A **run** is one replay; it has many **changes**.

```
runs                                       changes
──────────────────────────────            ─────────────────────────────
id              bigint  PK  ◀────────┐    id          bigint  PK
created_at      timestamptz          └────run_id      bigint  FK → runs.id
label           text    (nullable)        position    integer   (order in the report)
old_url         text                      path        text      "$.price"
new_url         text                      kind        text      "type_changed"
old_status      integer                   severity    text      "breaking"
new_status      integer                   old_value   jsonb
status_severity text    (nullable)        new_value   jsonb
old_body        jsonb
new_body        jsonb
total           integer
breaking        integer
safe            integer
info            integer
has_breaking    boolean
```

**Decisions:**

- **Changes get their own table** rather than being stuffed into one JSON column on `runs`. This is called **normalization**. It makes questions like "every breaking change to `$.price`, ever" a simple query.
- **Response bodies are stored (`old_body`, `new_body`)** as `JSONB`. This is the "time machine": you can see exactly what the API returned, and Phase 5's AI explanations will need that context. The cost is space: up to 5 MB per body (the replay size limit). Retention is a non-goal for now.
- **Summary counts are stored**, even though they could be recalculated from `changes`. Listing runs is the most common query, and it shouldn't have to count thousands of change rows each time. This deliberate duplication is called **denormalization**, a trade of storage for read speed.
- **`kind` and `severity` are `text` with `CHECK` constraints,** not PostgreSQL `ENUM` types. Adding a value to a PostgreSQL enum needs a special migration; changing a `CHECK` constraint is ordinary. The database still rejects invalid values.
- **`created_at` is `timestamptz`** (timestamp *with* time zone), set by the database, stored in UTC. Times without time zones are a classic source of bugs.
- **`ON DELETE CASCADE`** on `changes.run_id`: deleting a run deletes its changes, so no orphans are left behind.

**Indexes** (they make lookups fast, at a small cost on every insert):

| Index | Speeds up |
|---|---|
| `runs (created_at DESC)` | Listing the newest runs |
| `runs (label, created_at DESC)` | Listing the newest runs for one label |
| `changes (run_id)` | Loading a run's changes. PostgreSQL does **not** index foreign keys automatically. |

---

## 4. Modules

```
src/api_time_machine/
├── db.py        SQLAlchemy models (Run, ChangeRecord) and engine/session setup
├── history.py   save_run(), list_runs(), get_run(): all database access lives here
migrations/      Alembic migration scripts (versioned in Git)
alembic.ini      Alembic configuration
```

**Dependencies still point one way:** `api`/`cli` → `history` → `db`, `replay`, `models`. The comparison engine knows nothing about databases.

`history.py` takes a SQLAlchemy `Session` as a parameter (dependency injection again), so tests can run each test inside a transaction and roll it back.

**Synchronous database access.** SQLAlchemy also has an async mode, but it adds complexity for little gain here: a database insert takes milliseconds, while replay waits on remote servers. Database work in the web API runs in FastAPI's thread pool, so it never blocks the event loop that handles other requests.

---

## 5. Configuration

| Environment variable | Example | Meaning |
|---|---|---|
| `ATM_DATABASE_URL` | `postgresql+psycopg://atm:<password>@localhost:5432/api_time_machine` | Where the history database is. Unset means history is off. |
| `ATM_TEST_DATABASE_URL` | `...@localhost:5432/api_time_machine_test` | A **separate** database for tests. Never point it at real data: tests create and roll back rows. |

These live in a **`.env`** file in the project folder, loaded automatically at startup:

- `.env` holds your real password and is **never committed** (it's already in `.gitignore`).
- `.env.example` **is** committed, with placeholder values, so others know which settings exist.

**The database password never appears in code, in Git, or in this conversation.** You choose it and type it into `.env` yourself.

---

## 6. Web API

New endpoints, following REST conventions: `/runs` is a collection of saved runs.

| Method & path | Body / query | Returns |
|---|---|---|
| `POST /runs` | `{"old_url", "new_url", "label"?}` | Replays, saves, and returns the run with its `id`. Status **201 Created**. |
| `GET /runs` | `?label=...&limit=50` | Run summaries, newest first (no bodies or changes, to keep it small) |
| `GET /runs/{id}` | | One run with its changes and both bodies. **404** if it doesn't exist. |

`/compare` and `/replay` stay as they are: quick, stateless, nothing saved.

If `ATM_DATABASE_URL` isn't set, the `/runs` endpoints return **503 Service Unavailable** with a message explaining how to enable history. The rest of the API works normally.

---

## 7. CLI

```
python -m api_time_machine replay OLD_URL NEW_URL --save --label products-101
python -m api_time_machine history [--label products-101] [--limit 20]
```

- `--save` stores the run after printing the report, then prints `Saved as run 42`. Without a database configured, `--save` is an error (exit code 2).
- `history` prints one line per run: id, time, label, status codes, and counts.

---

## 8. Testing strategy

- **Tests use a real PostgreSQL database** (`ATM_TEST_DATABASE_URL`), not SQLite. SQLite doesn't have `JSONB`, and testing on a different database than you run on hides real bugs.
- **Migrations are tested too:** the test session builds the test database by running the Alembic migrations, the same way a real database is set up.
- **Each test runs inside a transaction that is rolled back,** so tests don't affect each other and the test database stays empty.
- **If `ATM_TEST_DATABASE_URL` isn't set, database tests are skipped** with a clear reason, so the other ~200 tests still run on any machine. In Phase 6, CI will provide a database so these tests always run there.

---

## 9. Implementation plan

1. **Database setup:** install PostgreSQL, create a user and two databases, `.env` / `.env.example`, a connection check
2. **Models and first migration:** `db.py`, Alembic, `alembic upgrade head`, look at the tables
3. **History functions:** `save_run`, `list_runs`, `get_run`, tested against the test database
4. **Web API:** `POST /runs`, `GET /runs`, `GET /runs/{id}`, and 503 when not configured
5. **CLI and wrap-up:** `replay --save`, `history`, README, merge
