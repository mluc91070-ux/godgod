# GODGOD

An autonomous research system that studies how meme narratives propagate on Solana.

It observes, filters, remembers, forms falsifiable hypotheses, tests them, tries to
break its own results, and publishes what it found — including what failed.

It is not a trading bot. There is no wallet execution anywhere in this codebase.

**Status: PHASE 1 complete.** The repository, database, API, frontend shell and demo
mode exist and are tested. The observation, hypothesis, experiment and critic engines
do not exist yet. `/api/status` reports exactly what is implemented, and the UI says so
on every page.

---

## What runs today

| Capability | State |
| --- | --- |
| Database schema + migration for the full research chain (22 tables) | implemented |
| Read API: observations, hypotheses, experiments, traces, patterns, memory, events, metrics | implemented |
| Demo mode over fixtures, every row flagged `is_demo` | implemented |
| Draft approval / rejection behind an operator token | implemented |
| Publishing to X | deliberately refuses (501) — PHASE 7 |
| Frontend: 12 routes + public experiment pages | implemented |
| Vector memory search | not implemented — PHASE 2 (search is lexical, and says so) |
| Observer / researcher / data scientist / critic / writer / reviewer agents | not implemented — PHASE 3–6 |
| Solana + X providers | interfaces only — PHASE 7–8 |
| SSE live streaming | not implemented — PHASE 9 (terminal is polled on load) |

## Quick start (no API keys, no Docker, no database server)

```bash
# backend
python -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements-dev.txt   # Windows
# backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt     # macOS/Linux

cd backend && ../backend/.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

On first start the API creates a local SQLite database and loads the demo fixtures.
Open <http://localhost:8000/docs> for the OpenAPI page.

```bash
# frontend
cd frontend
npm install
npm run dev        # http://localhost:3000
```

## Tests

```bash
backend/.venv/Scripts/python -m pytest          # 78 tests
backend/.venv/Scripts/python -m ruff check backend tests scripts
cd frontend && npm run typecheck && npm run build
backend/.venv/Scripts/python scripts/check_phase1.py
```

`make check` runs all of the above where GNU make is available.

## PostgreSQL + pgvector

SQLite is the local convenience path. The production target is PostgreSQL with
pgvector:

```bash
export DATABASE_URL=postgresql+psycopg://godgod:godgod@localhost:5432/godgod
pip install -r backend/requirements-postgres.txt
cd backend && python -m alembic upgrade head     # creates the vector extension too
```

`docker compose up` starts Postgres (pgvector image), the API and the frontend.

## Layout

```
backend/app/
  api/         routes and dependencies
  core/        config, enums, untrusted-content handling
  db/          engine, session, portable column types
  models/      SQLAlchemy models (the 22 tables)
  schemas/     Pydantic response contracts
  services/    fixtures, seeding, derived state
  providers/   Solana / X abstractions (no vendor names)
  agents/      PHASE 3–6
  workers/     PHASE 3+
frontend/      Next.js app router, one route per public surface
data/fixtures/ the only data source in demo mode
docs/          architecture, methodology, identity, security, cost, publishing
tests/         78 tests over the API, seeding, fixtures and security invariants
```

## Rules this codebase enforces

- A measurement that no source provided is `null`. It is never filled in.
- A hypothesis without a falsification condition is rejected by the schema.
- A result cannot be `SUPPORTED` without a passing critic verdict.
- External text — posts, token names, wallet labels, metadata — is data, never
  instruction (`app/core/untrusted.py`, enforced by tests).
- No private keys, no signing, no transaction construction. A test fails the build
  if any such symbol appears in `backend/app`.

See `CLAUDE.md` for working conventions and `docs/` for the long form.
