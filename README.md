# Food App: pantry first

A small Flask application for a shared household ingredient catalogue, pantry,
recipes, and shopping list. Designed for a phone browser on a trusted private
network. This branch takes calorie tracking out of the default workflow so that
adding an ingredient does not require a nutrition database or USDA account.

**Status:** a working prototype being refactored, not a completed meal-planning
product. Existing nutrition data is retained. No database tables are dropped.

## What works now

- Create and edit ingredients manually, using a consistent stock unit.
- Record stock on hand and low-stock thresholds.
- Save recipes, including nested sub-recipes, quantities, portions and instructions.
- Add individual ingredients or recipe shortfalls to a shopping list.
- Mark purchases to add stock; unmarking reverses that addition.
- Use the pantry-first home page without calorie targets or a nutrition API.

**Not yet implemented:** favorite ratings and ranked cookable recipes; a dedicated
“Cook this recipe” event with snapshot-based undo; unit conversion; purchase prices
and spending history. Stock is manually adjusted in the default workflow. See
[the staged roadmap](PROJECT.md) rather than assuming these features exist.

## Quick start (a new, disposable local database)

Python 3.11 or newer is recommended for the documented development workflow.
From this repository:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`: set a private random `FLASK_SECRET_KEY`, retain
`TAILSCALE_IP=127.0.0.1` for local development, and choose a free `PORT`. Leave
`ENABLE_NUTRITION=false`. Do not commit `.env` or database files.

```sh
python run.py
```

Open the address printed at startup. Flask-SQLAlchemy creates missing tables on
startup. With the default `sqlite:///app.db`, the file is `instance/app.db` relative
to the app's instance directory, **not** a file in the shell's current directory.
For an existing installation, read the backup section before running this branch
against its database.

## Configuration

Environment variables take precedence over `.env` values. Restart the process
after changing configuration.

| Variable | Purpose |
| --- | --- |
| `FLASK_ENV` | `development` or `production`; selects application configuration. |
| `FLASK_SECRET_KEY` | Session signing key. Replace the development placeholder. |
| `APP_NAME` | Name displayed in the interface. |
| `TAILSCALE_IP` | Bind address for `run.py`; default is loopback `127.0.0.1`. |
| `PORT` | Port for `run.py`; default is `5000` unless `.env` overrides it. |
| `DATABASE_URL` | SQLAlchemy URL; default `sqlite:///app.db`. Absolute SQLite paths use `sqlite:////absolute/path/app.db`. |
| `ENABLE_NUTRITION` | Default `false`. `true`, `yes` or `1` explicitly enables the retained legacy nutrition workflows. |
| `PROFILES` | Comma-separated labels for legacy nutrition logs/goals, not separate pantry accounts. |
| `USDA_API_KEY` | Only needed for optional legacy USDA search; not needed by the pantry-first workflow. |

Profiles are **not authentication**. Ingredients, recipes, pantry and shopping
are shared across profiles. See [architecture and data flow](docs/ARCHITECTURE.md).

## Phone access and deployment boundaries

For a private test, choose the server's actual Tailscale IP and connect the phone
to the same permitted tailnet. A bind address controls where a process listens;
it does not create accounts, authorization, encryption or firewall rules. Access
also depends on Tailscale policy and network configuration.

For a longer-running process, use a WSGI server rather than Flask's development
server. Example, after setting production configuration in `.env`:

```sh
gunicorn --bind 100.x.x.x:5000 'app:create_app()'
```

Replace the address with a real address on the server. Gunicorn's bind argument,
not `TAILSCALE_IP` or `PORT`, controls this example. Stop a foreground process with
Ctrl-C; do not kill unrelated Gunicorn processes by name.

**Security limits:** this prototype has no login/authorization system and no
CSRF protection for mutations. Anyone who can reach it can change shared data;
a private network alone does not eliminate browser-based request risks. Do not
expose it to the public internet. Use test data until these gaps are addressed.
The interface currently loads Tailwind from a CDN, so completely offline styling
is not guaranteed. Serving compiled local CSS is a future packaging improvement.

## Existing data, backups and rollback

1. Stop the running app before copying its SQLite database so the backup is
   consistent. For another database engine, use that engine's backup procedure.
2. Preserve the complete database, `.env` securely, current Git commit, and current
   dependency versions. Never commit the backup or credentials.
3. Test this branch against a **copy** of the database first by setting a separate
   `DATABASE_URL`. Confirm ingredient, recipe, pantry and shopping records remain.
4. Nutrition columns, goal records and meal history remain in the schema while
   the feature is disabled. Disabling the interface does not undo old stock
   deductions, delete logs, or rewrite existing quantities.
5. `db.create_all()` creates missing tables; it is **not** a migration framework
   and will not upgrade arbitrary old schema layouts. There is no destructive
   migration in this refactor. If a legacy schema differs, stop and prepare an
   explicit migration instead of deleting the database.

Do not treat switching Git branches as a database rollback. Keep the pre-change
backup and restore only deliberately, while the app is stopped. Existing data
has not been inspected or migrated on your server by this project change.

## Development checks

```sh
python -m unittest discover -s tests -v
python -m compileall -q app config.py run.py
```

Tests use isolated databases, not your `.env` database. They cover default-mode
routing and nutrition boundaries, core flows and preservation of legacy values.
Passing HTTP/template tests is not a substitute for phone-browser visual testing.

## Repository guide

- [Architecture and data flows](docs/ARCHITECTURE.md): where features live and what changes stock.
- [API and feature boundaries](docs/API.md): current routes and disabled legacy behavior.
- [Pantry-first roadmap](PROJECT.md): next increments and acceptance checks.
- [Archived nutrition-first plan](docs/archive/nutrition-plan.md): historical design, **not current instructions**.

The scope of this refactor is a simpler foundation and clear reference material,
not a rewrite or a complete implementation of the roadmap.
