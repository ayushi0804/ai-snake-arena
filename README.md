# AI Snake Arena

Snake with a safety-aware AI, packaged as a desktop game (Pygame), a mobile-friendly installable web app (Canvas + PWA), a Flask REST API with SQLite persistence, an analytics dashboard, and a reproducible AI benchmarking lab.

Your original game is preserved: `legacy/python_original.py` is the untouched original, `highscore.txt` is untouched (its score of **43** is imported once into the database, never modified), and the desktop game keeps the original controls (arrows, **M**, **A**=A*, **B**=BFS, Enter = restart, Esc = quit) and original defaults (AI on, A*, 8 ticks/s, 25×12).

## What is verified (and what is not)

| Area | Status |
|---|---|
| Pathfinding, engine, safety, AI, Hamiltonian cycle (Python) | **Tested** - unit tests, run in the build sandbox |
| Browser engine + AI (JavaScript) | **Tested** with Node against the *same* shared test vectors as Python |
| Database, migrations, legacy import, API, leaderboard, stats, benchmarks, CSV | **Tested** (unit + Flask test client + a real server process restarted to confirm persistence) |
| PWA manifest, icons, service-worker generation, every precache URL returns 200 | **Tested** server-side |
| Desktop Pygame game | **Compiled and smoke-tested against a stub pygame only.** Real `pygame` was not installable in the build sandbox (no network), so the window, fonts and sound have **not been run**. |
| Browser UI: rendering, touch/swipe, layouts, service-worker offline behaviour, install prompt | **Not run in a real browser** (none available). Code is written for it and syntax-checked, but please test on your phone/Chrome - see the checklist below. |
| Windows PowerShell commands | Written for Windows; the build sandbox was Linux. |

## Quick start (Windows PowerShell)

```powershell
cd path\to\ai-snake-arena
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # if blocked: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
copy .env.example .env                # optional
python tools\init_db.py               # creates data\arena.db, imports highscore.txt once
```

Run the desktop game (independent of the web backend; records matches into the same DB):

```powershell
python play_desktop.py                # menu; add --no-menu for the original defaults
```

Run the web app + API (independent of the desktop game):

```powershell
python run_web.py                     # then open http://127.0.0.1:5000
```

Run the tests (standard library only; `pytest` also works if installed):

```powershell
python -m unittest discover -s tests -t . -v
node --test tests/test_js.mjs         # requires Node 20+
```

### Desktop controls
Arrows steer (manual mode) · **M** manual⇄AI · **A** A* · **B** BFS · **D** Dijkstra · **S** adaptive · **H** Hamiltonian · **P/Space** pause · **V** path overlay · **N** mute · **+/-** speed · **R** restart · **Enter** restart after game over · **Backspace** menu · **Esc** quit. Menu: difficulty, board size, wrap-around, obstacles, power-ups, speed, mode, strategy.

### Browser controls
Arrows, swipe on the board, or the on-screen D-pad (shown on touch devices). The page never scrolls while you touch the board (`touch-action: none` only on the board).

## Architecture

```
snake_core/   pure Python rules + AI (no pygame/Flask): grid, engine, pathfinding, safety, ai, hamilton, benchmark
desktop/      Pygame front end (app = loop/input, render, audio)
storage/      SQLite layer: db (migrations, transactions), services, legacy import, highscore file, desktop recorder
webapp/       Flask app: api (/api/v1), views, templates, static css/js, PWA assets
tests/        unittest suites + shared vectors/pathfinding.json (used by Python AND JavaScript)
tools/        init_db.py, make_icons.py
legacy/       your original files, untouched
```

The browser game is a separate presentation layer with its own loop (`static/js/engine.js`, `ai.js`, `game.js`). It mirrors the Python rules and is checked against the same test vectors; it makes **no network request per frame** - only one request when a match ends.

## AI

* **A\*** (Manhattan heuristic, scaled by the minimum step cost so it stays admissible), **BFS** (unweighted only), **Dijkstra** (supports per-cell entry costs).
* **Raw strategies** (A*, BFS, Dijkstra) follow the shortest path and only refuse a step that is immediately fatal.
* **Adaptive** validates the path with a virtual snake (growth-aware, moving-tail-aware), requires the snake to be able to reach its tail afterwards, otherwise follows its tail / picks the move with the most reachable space. Dead ends are detected (`area < length` and tail unreachable). If no legal move exists it reports that instead of looping; matches also end as `stalled` if an AI goes `4 × cells` steps without an apple.
* **Hamiltonian** follows a verified cycle (`is_valid_cycle`), with safe shortcuts. It exists for boards with at least one even dimension and **no obstacles**; otherwise it falls back to adaptive and says so. A plain serpentine (what the original code called a "Hamiltonian cycle") is *not* a cycle and is tested as such.
* Limits: path planning treats only the tail as free (slightly conservative); the adaptive AI is very safe but not provably perfect with obstacles/bonus items - measured outcomes are in the Benchmark Lab, not claimed here.

## API (`/api/v1`)

Responses: `{"ok": true, "data": ...}` or `{"ok": false, "error": {"code", "message", "details"?}}`. Guests identify with `X-Guest-Id` (8-64 chars `A-Za-z0-9_-`).

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness + DB check |
| POST | `/matches` | submit a finished match (201 created / 200 duplicate / 422 invalid) |
| GET | `/matches?limit&offset` | your history |
| GET | `/players/me/stats` | dashboard figures |
| GET | `/leaderboard?difficulty&mode&limit` | best score per player |
| GET | `/metrics/algorithms` | per-algorithm metrics from played matches + latest benchmark rows |
| GET/PUT | `/settings` | validated settings sync |
| POST | `/benchmarks/run` | run seeded benchmark (`pathfinding` or `survival`) |
| GET | `/benchmarks`, `/benchmarks/export.csv` | stored runs / CSV export |

## Trust model (important)

Nothing is "server-verified". Matches come from the player's own browser/desktop, so every row carries a `trust` label (`client_reported`, `local_desktop`, `legacy_import`). The server only rejects *implausible* data (e.g. more apples than steps, a score above what those apples allow, durations too short for the step count). Leaderboards and dashboards say so on screen. Server-side replay verification would need a deterministic shared RNG and move log - not implemented. Benchmark rows are different: they are measured by the server's own Python engine and labelled with provenance.

## Data

* Database: `data/arena.db` (SQLite, override with `ARENA_DB_PATH`). Tables: `players`, `matches`, `benchmark_runs`, `settings`, `meta`, `schema_migrations`.
* Legacy `highscore.txt`: imported once (`meta.legacy_highscore_migrated`), invalid contents are reported not imported, the file is never changed by the importer. The desktop game still writes `highscore.txt` in the original format (atomic write).
* Guest play only; there are no passwords or accounts, so nothing sensitive is stored. The "guest ID" is a random value in the browser's local storage.

## Progressive Web App

* Installable (manifest, 192/512/maskable icons, service worker at `/sw.js`). Chrome/Edge: Install button; Android: menu → *Install app*; iOS Safari: Share → *Add to Home Screen*.
* **Production installation requires HTTPS**; `http://localhost` / `127.0.0.1` work for development.
* **Offline:** the game (manual + AI), settings, local high score. After the first online visit all pages and assets are precached. **Online-only:** dashboard, history, leaderboard, benchmarks, settings sync. Matches finished offline are queued in local storage and uploaded (idempotently) when you reconnect.
* **Updates:** `/sw.js` embeds a hash of every static file and template; any change creates a new cache and deletes the old one, and `/sw.js` is served `no-cache`. Reload twice (or close/reopen the app) to switch to a new version.

### Browser checklist for you to run (not done in the sandbox)
1. Open `http://127.0.0.1:5000/play`, play manual and AI; try each strategy and board.
2. Phone (same Wi-Fi, run with `ARENA_HOST=0.0.0.0`): swipe on the board, check portrait/landscape; the page must not scroll over the board. (Install on a phone needs HTTPS.)
3. DevTools → Application → Service Workers: confirm it's activated, then tick *Offline* and reload `/play`; the game must still run.
4. Finish a game, open Dashboard/History/Leaderboard.

## Design decisions
* **`sqlite3` repository layer instead of SQLAlchemy.** The build sandbox had no network, so SQLAlchemy could not be installed or tested, and I will not ship untested ORM code. All SQL is parameterised and confined to `storage/`; moving to PostgreSQL means replacing `Database.connect()/init()` and `?` placeholders (or swapping this package for SQLAlchemy models behind the same service functions).
* No `flask-cors`/`python-dotenv`: tiny built-in equivalents (CORS restricted to `ARENA_CORS_ORIGINS`, `.env` loader).
* `requests` from the old requirements was unused and was dropped (`legacy/requirements_original.txt` kept).
* Charts are hand-drawn on canvas (no CDN) so they work offline.

## Production notes
Use a real WSGI server (`pip install waitress`, then `waitress-serve --listen=0.0.0.0:8000 --call webapp:create_app`), put it behind HTTPS, set `ARENA_ENV=production`, `ARENA_SECRET_KEY`, `ARENA_DB_PATH`, and `ARENA_CORS_ORIGINS` if the front end is on another origin. SQLite is fine for one small instance; use PostgreSQL for multiple workers/hosts. Add rate limiting at the proxy.

## Troubleshooting
* `Activate.ps1 cannot be loaded` → `Set-ExecutionPolicy -Scope Process Bypass`.
* `ModuleNotFoundError: pygame` → activate the venv and `pip install -r requirements.txt` (very new Python versions may lack pygame wheels; use Python 3.10-3.12).
* Port 5000 busy → set `ARENA_PORT=5001` in `.env`.
* Stale web app after changing files → hard-reload, or DevTools → Application → *Unregister* the service worker.
* No sound on desktop → no audio device; the game continues silently.
* Database locked → close other programs that have `data\arena.db` open.
