# Flask Web App Starter

A minimal Flask scaffold with SQLAlchemy, multi-profile support, and Tailscale-aware binding. Fork this for every new project — nothing to strip out, nothing missing.

---

## Structure

```
app/
├── __init__.py          # App factory — db, blueprints, context processor, error handlers
├── models.py            # Empty — add your models here
├── blueprints/
│   └── main.py          # Dashboard (/) + POST /switch-profile
├── utils/
│   └── helpers.py       # current_profile(), _int(), _float()
└── templates/
    ├── base.html        # Dark Tailwind layout, nav, flash messages, profile switcher
    ├── main/index.html  # Placeholder dashboard
    └── errors/          # 404 and 500 pages
config.py                # Dev/Prod configs, all env vars with defaults
run.py                   # Dev entry point — binds to TAILSCALE_IP
requirements.txt
.env.example
```

---

## Forking this for a new project

1. Copy or clone this repo into a new directory.
2. Create and activate a virtualenv:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in your values:
   ```bash
   cp .env.example .env
   ```
4. Set `APP_NAME` to your project name — it appears in the nav and page titles.
5. Add your models to `app/models.py`. Every model needs a `profile_id` column (see the comment there).
6. Add a blueprint for your feature under `app/blueprints/`, register it in `app/__init__.py`.
7. Replace `app/templates/main/index.html` with your real dashboard.

The database (`instance/app.db`) is created automatically on first run.

---

## Environment variables

| Variable           | Default       | Description                        |
|--------------------|---------------|------------------------------------|
| `FLASK_SECRET_KEY` | `change-me`   | Session signing key                |
| `FLASK_ENV`        | `development` | `development` or `production`      |
| `APP_NAME`         | `My App`      | Shown in nav and page titles       |
| `TAILSCALE_IP`     | `127.0.0.1`   | IP to bind to                      |
| `PORT`             | `5000`        | Port to bind to                    |
| `PROFILES`         | `Default`     | Comma-separated profile names      |

---

## Running

### Loopback only (local development, no Tailscale)

Leave `TAILSCALE_IP` unset or set it to `127.0.0.1`:

```bash
source .venv/bin/activate
python run.py
```

The app binds to `127.0.0.1:5000`. Open `http://127.0.0.1:5000` in your browser. Only your machine can reach it.

### Tailscale binding (accessible from your Tailscale network)

Find your Tailscale IP:

```bash
tailscale ip -4
```

Set it in `.env`:

```
TAILSCALE_IP=100.x.x.x
```

Then run:

```bash
source .venv/bin/activate
python run.py
```

The app binds to your Tailscale IP on port 5000. Any device on your Tailscale network can reach it at `http://100.x.x.x:5000`. Your machine's LAN and the public internet cannot.

---

## Verifying the binding

After starting the server, check what address it actually bound to — the Flask dev server prints this on startup:

```
 * Running on http://100.x.x.x:5000
```

To confirm from the terminal without a browser:

```bash
# Loopback
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/

# Tailscale
curl -s -o /dev/null -w "%{http_code}" http://100.x.x.x:5000/
```

Both should return `200`. A `Connection refused` on the Tailscale address means the IP in `.env` doesn't match what `tailscale ip -4` returns.

To verify the app is **not** reachable on `0.0.0.0` (it never should be):

```bash
curl -s -o /dev/null -w "%{http_code}" http://0.0.0.0:5000/
```

This should fail or return a connection error — if it succeeds, check that `TAILSCALE_IP` is set and `run.py` isn't overriding it.

---

## Multi-profile setup

Set `PROFILES` to a comma-separated list:

```
PROFILES=Alice,Bob
```

A dropdown appears in the nav. Selecting a profile stores it in the session. Use `current_profile()` (available in all templates via the context processor, and importable from `app.utils.helpers`) to scope queries to the active profile.

---

## Stopping the server

**Dev server (`run.py`):** Press `Ctrl+C` in the terminal where it's running.

**Gunicorn:** Also `Ctrl+C` if running in the foreground. If you started it in the background, find and kill the process:

```bash
pkill -f "gunicorn"
# or more precisely:
lsof -ti :5000 | xargs kill
```

---

## Production

Use gunicorn instead of `run.py`:

```bash
gunicorn -b 100.x.x.x:5000 "app:create_app()"
```

Set `FLASK_ENV=production` and use a real `FLASK_SECRET_KEY`.
