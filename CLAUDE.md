# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Contribution workflow (project rule)

Local work is unrestricted, but **anything that lands on GitHub goes through a Pull Request — never push directly to `main`**. Branch off `origin/main` for unrelated work; do not pile unrelated changes onto an existing feature branch. Keep `zebra.__version__` (`zebra/__init__.py`) in sync with `version` in `pyproject.toml`, and document user-facing changes in `CHANGELOG.md`.

## Commands

The project is managed with **uv** (lockfile-based). There is **no automated test or lint suite** — verification is done with smoke checks.

```bash
uv sync --extra mssql-pure          # install runtime deps (+ pure-Python SQL Server driver)
uv run python app.py                # web-only dev server → http://127.0.0.1:5000
uv run python desktop.py            # native pywebview window (uses ~/.comandante_zebra/ for data)

# Backend smoke check (catches import/config errors without binding a port):
uv run python -c "from zebra import create_app; create_app(); print('OK')"

# Frontend: static JS is served as-is (no bundler). Verify syntax with:
node --check static/app.js

# Package the binary (PyInstaller cannot cross-compile — .exe must be built on Windows):
uv sync --extra mssql-pure --group build
uv run pyinstaller --noconfirm --clean build_desktop.spec   # → dist/ComandanteZebra.{exe,app}
```

Dev-only diagnostic routes (`/_routes`) register only when `ZEBRA_DEV_ROUTES=1`. CI lives in `.github/workflows/`: `build-windows.yml` (builds the `.exe` on push to `main`) and `screenshots.yml` (regenerates `docs/screenshots/` via Playwright + `scripts/take_screenshots.py`).

## Architecture — the big picture

**Code is read-only/bundled; all mutable state is profile-scoped and lives outside the repo.** This is the central mental model. `create_app(base_dir=...)` (`zebra/__init__.py`) calls `profiles.bootstrap`/`resolve_paths` to pick the *active* profile under `<base>/profiles/<name>/` (each profile owns its own `config.cfg`, `secrets.cfg`, `labels.db` and `templates_zpl/`). `app.py` defaults `base` to the repo root (so a `profiles/` dir appears locally); `desktop.py` passes `~/.comandante_zebra/` so user data survives `.exe` upgrades. `seed_profiles/default/` is the template copied into a fresh user dir on first run — editing seed templates (e.g. `seed_profiles/default/templates_zpl/*.zpl`) only affects *new* installs, not existing ones.

**Two entry points, same factory.** `app.py` = pure WSGI (browser dev). `desktop.py` = pywebview native window that injects the external `base_dir` and the discovery port. Both call `zebra.create_app()`.

**Label pipeline.** A template is a `.zpl` file plus a sidecar field spec parsed by `zebra/fields.py`. Flow: form values → `zebra/zpl.py` `render()` (token substitution; empty fields render as `{key}` so layout is visible) → `zebra/preview.py` `zpl_to_png()` which POSTs to the **external Labelary API** for the PNG preview (so preview needs network + that service) → `zebra/printer.py` sends raw ZPL to the Zebra over USB / Windows spooler / IP socket. Copies use ZPL `^PQ`, not N re-sends.

**Offline-first lookups.** Lookup fields resolve against `zebra/lookup_cache.py` (a per-profile SQLite cache) **first** — instant and works with no network. Only if the cache returns 0 rows does the request fall through to a live `DataSource.search()` so freshly-added records are still found. `zebra/cache_scheduler.py` refreshes the cache in the background. Endpoint: `GET /api/lookup/<template>/<field>?q=`.

**Pluggable datasources.** `zebra/datasources/`: `base.py` defines the connector interface, `registry.py` the type registry, `mssql.py` the SQL Server implementation with two interchangeable driver backends selected via the `mssql-pure` (pymssql) or `mssql-odbc` (pyodbc) extras.

**Routes are Flask blueprints** (`zebra/routes/`): `labels` (print/preview/lookup), `config`, `tmpl` (template CRUD + history), `network`. The print page (`templates/form.html` + `static/app.js`) has a debounced auto-preview that fires on the preview form's `input` events, plus a hidden "mirror" form that syncs preview field values into the actual print form.

**LAN sharing.** `zebra/discovery.py` announces the instance over mDNS (`_comandante-zebra._tcp.local.`); `zebra/network.py` handles peer pull with a 6-digit PIN. Templates share by default; connection definitions are opt-in and **never carry passwords**.

**i18n.** `zebra/i18n.py` loads the JSON catalogs in `i18n/` at startup; language is resolved per request from a cookie / `Accept-Language` and injected into templates via a context processor.
