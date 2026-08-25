# Deployment

## Local, no dependencies

```bash
python -m venv backend/.venv
backend/.venv/Scripts/python -m pip install -r backend/requirements-dev.txt
cd backend && .venv/Scripts/python -m uvicorn app.main:app --reload --port 8000
```

SQLite is created on first start and the demo fixtures are loaded
(`GODGOD_AUTO_SEED=0` disables that).

```bash
cd frontend && npm install && npm run dev
```

## Docker

```bash
cp .env.example .env
docker compose up
```

Starts `pgvector/pgvector:pg16`, runs `alembic upgrade head`, serves the API on
:8000 and the frontend on :3000.

> Note: `docker-compose.yml` was written and YAML-validated, but has not been run
> on this machine (no Docker daemon available). Treat the first `docker compose
> up` as unverified.

## PostgreSQL

```bash
export DATABASE_URL=postgresql+psycopg://user:pass@host:5432/godgod
pip install -r backend/requirements-postgres.txt
cd backend && python -m alembic upgrade head
```

The initial migration issues `CREATE EXTENSION IF NOT EXISTS vector` when it
detects PostgreSQL, so the `memories.embedding` column is created as a real
`vector(1536)`; migration `0002` adds the HNSW `vector_cosine_ops` index that
memory search orders against.

> The pgvector ranking path has not been executed on the development machine
> (no PostgreSQL available). The Python fallback is the tested one. Run
> `scripts/check_phase2.py` against the Postgres instance after the first
> deploy — it exercises search, related, cluster and digest end to end.

If you change `EMBEDDING_MODEL`, run `python scripts/backfill_embeddings.py`.
Search ignores vectors produced by a different model, so skipping the backfill
makes memory look empty rather than wrong — quietly.

Supabase works as-is: enable the `vector` extension in the dashboard, then point
`DATABASE_URL` at the connection string.

## Frontend on Vercel

- Root directory: `frontend`
- Build: `npm run build`
- Environment: `NEXT_PUBLIC_API_URL=https://<your-api-host>`

All pages are server-rendered on demand (`force-dynamic`) because they read live
system state. No API key ever reaches the browser.

## Backend hosting

Any container host works; the image is `python:3.12-slim` plus requirements.
Target cost is $10–30/month for a single small instance running the API and,
from PHASE 3, the research worker.

Required environment in production:

```
DATABASE_URL=postgresql+psycopg://...
DEMO_MODE=false
AUTONOMY_LEVEL=1
X_MODE=draft
ADMIN_TOKEN=<long random value>
CORS_ORIGINS=https://<your-frontend-host>
```

`DEMO_MODE=false` with no providers configured is a legitimate state: the system
reports empty rather than serving fixtures. Demo and real data are never mixed —
`is_demo` separates them at the row level and the seeder only ever deletes rows
it owns.

## Checks before deploying

```bash
backend/.venv/Scripts/python -m pytest
backend/.venv/Scripts/python -m ruff check backend tests scripts
cd frontend && npm run typecheck && npm run build
backend/.venv/Scripts/python scripts/check_phase1.py
```
