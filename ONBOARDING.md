# Onboarding — Comandante Zebra

Welcome 👋 This guide gets a new collaborator (and their Claude Code) productive fast. For the always-loaded technical reference, see `CLAUDE.md` — Claude Code reads it automatically every session, so you don't have to paste anything.

## What this project is

A small desktop app (Flask + pywebview, shipped as a single Windows `.exe`) that prints Zebra **ZPL** labels: type/scan a code, it pulls description/price/EAN from the ERP, fills a ZPL template, and the printer prints. It keeps working offline from a local SQLite cache. Multi-profile (one binary runs Store A / Store B / Warehouse).

## Get it running (from source)

Requires [`uv`](https://docs.astral.sh/uv/). `node` is optional (only to syntax-check frontend JS).

```bash
git clone https://github.com/fcopuerto/comandante_zebra.git
cd comandante_zebra
uv sync --extra mssql-pure

uv run python app.py        # browser dev → http://127.0.0.1:5000
# or: uv run python desktop.py   (native window)
```

No database or printer? It still boots — lookups fall back to the empty cache and the label preview renders via the external Labelary API.

## The one rule that matters

**Everything that reaches GitHub goes through a Pull Request — never push directly to `main`.** Local experimentation is free; branch off `origin/main` and open a PR for anything you want merged. Don't stack unrelated changes on someone else's feature branch.

## Mental model (so you don't get lost)

- **Code is bundled/read-only; data is profile-scoped and lives outside the repo.** Running from source, a `profiles/` folder appears locally (gitignored); as an `.exe` it's `~/.comandante_zebra/`. Editing `seed_profiles/` only affects *new* installs.
- The label flow is: field spec (`zebra/fields.py`) → `zebra/zpl.py` renders the `.zpl` → `zebra/preview.py` calls Labelary for the PNG → `zebra/printer.py` sends raw ZPL to the Zebra.
- Lookups hit the local SQLite cache first (offline-first), live DB only as fallback.

## Where to look

| You want to… | Start in |
| --- | --- |
| Print / preview / lookup logic | `zebra/routes/labels.py`, `static/app.js` |
| Template CRUD & history | `zebra/routes/tmpl.py`, `zebra/template_history.py` |
| Add/adjust a datasource | `zebra/datasources/` (`base.py`, `registry.py`, `mssql.py`) |
| Offline cache behaviour | `zebra/lookup_cache.py`, `zebra/cache_scheduler.py` |
| App wiring / profiles | `zebra/__init__.py`, `zebra/profiles.py` |

## Verifying changes

There's **no test/lint suite**. Before opening a PR:

- Backend: `uv run python -c "from zebra import create_app; create_app(); print('OK')"`
- Frontend JS: `node --check static/app.js`
- For UI-affecting changes, the `screenshots.yml` CI workflow regenerates `docs/screenshots/`.

Ask your Claude Code session anything about the architecture — it has `CLAUDE.md` loaded and can navigate the codebase for you.
