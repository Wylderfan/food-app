# Explicit cooking and immutable history

Cook → choose servings → Cook this → inspect planned quantities → Confirm.
Cancel does not change stock. The confirmation token is durable and retryable,
including after undo. Any change to the snapshot requires a fresh preview and
explicit confirmation. Unknown, missing, insufficient and incompatible stock
blocks confirmation. Recent cooking shows the saved quantities and undo state.

CookEvent and CookPreview snapshots retain ingredient names, IDs, stock units,
quantities, before/after totals and correction epochs. CookUndo is a separate
append-only record. History has no deletion cascade to mutable recipes or
pantry. Application ORM updates/deletes of history are rejected. Direct SQL and
external database writers remain outside these guarantees.

Undo adds the original deductions to current stock, preserving subsequent cooks
and explicit Add Stock actions. A correction (even away and back), uncertainty,
unit change or ingredient deletion blocks undo with no partial effects. Correct
stock manually in that case; history remains visible. Legacy shopping toggle
stock changes are conservatively treated as corrections in this increment.

All app write requests lock before reading: SQLite BEGIN IMMEDIATE serializes
writers across workers; PostgreSQL uses a transaction advisory lock. Readers
remain ordinary reads. Keep the PostgreSQL default READ COMMITTED isolation.
Unsupported dialect writes fail closed. SQLite lock contention returns a retry
message without changing stock. Keep all future stock writers inside this
protocol; it is deliberately coarse for this small shared-pantry app.

Eating log creation/deletion no longer changes inventory, including with optional
nutrition enabled. Old logs retain their values; removing an old log no longer
reconstructs stock from a possibly edited recipe. Reconcile legacy stock manually
if needed. Cooking creates no meal log, purchase or nutrition record.

## Additive schema and safe retest

New tables: stock_epochs, cook_previews, cook_events, cook_undos. Existing columns
and rows are retained. Startup create_all creates missing tables only; it does
not repair arbitrary old schemas. The ingredient-creation 500 cause on the real
database remains unconfirmed.

Before using existing data: stop app writers, take a restorable database backup
(SQLite backup API or stopped-file backup; pg_dump for PostgreSQL), restore it
to a separate test location, inspect schema with scripts/check_sqlite_schema.py
for SQLite, and point a test instance only at that copy. Never reset the real DB.
A Git checkout is not a database rollback; restore backups deliberately while
writers are stopped. Do not run old branches concurrently against the new DB.

From a fresh checkout, without configuring any real database:

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q app scripts tests
PYTHONPATH=. .venv/bin/python scripts/demo_cooking.py
```

Open http://127.0.0.1:5057/cook?servings=2. The server always uses a new temporary
SQLite DB with demo egg fried rice, never DATABASE_URL or instance/app.db. Stop
with Ctrl-C. Verify rice 500 → 300 g, cancel, confirm, recent event, undo → 500 g.
Tests separately verify duplicates, concurrency, changed previews, edited recipe
undo, later additions/cooks, corrections, uncertainty, missing/incompatible units,
immutable history and separate eating logs.

## Verification and limits

67 tests passed with disposable SQLite databases, including production config
and file-backed concurrent requests (independent sessions). Desktop Chromium
and a narrow 455 CSS-pixel actual Chromium window passed serving selection,
preview, cancel, confirm (500 → 300 g), recent event and undo (→ 500 g).
DevTools device emulation was unavailable; narrow desktop is not iPhone Safari
or physical-phone touch QA. PostgreSQL advisory-lock path is implemented but
not integration-tested here (no PostgreSQL server). The existing Pantry regression tests workflow runs tests and compileall on Python 3.11 and 3.12.
No real data, merge or deployment. Existing prototype authentication/CSRF/secret
limitations in README still apply; profile selection is not authentication.
