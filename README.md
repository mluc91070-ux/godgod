# GODGOD

An autonomous research system that studies how meme narratives propagate on Solana.

It observes, filters, remembers, forms falsifiable hypotheses, tests them, tries to
break its own results, and publishes what it found — including what failed.

It is not a trading bot. There is no wallet execution anywhere in this codebase.

**Live:** [godgod.vercel.app](https://godgod.vercel.app) · API [godgod-api.onrender.com](https://godgod-api.onrender.com/api/status)

**Status: PHASE 1-6, 9, 10 and the model layer complete, deployed.** The repository, database, API, frontend, memory
system, observation pipeline and the hypothesis / experiment / critic engines exist
and are tested. All of it is deterministic — no model is called anywhere yet. Every
external integration (Anthropic, X, Solana RPC) is deliberately scheduled last.
`/api/status` reports exactly what is implemented, and the UI says so on every page.

---

## Deploy it

```bash
backend/.venv/Scripts/python scripts/preflight.py     # refuses an unsafe config
```

It is deployed: API and PostgreSQL on Render, frontend on Vercel, the hourly
research cycle on GitHub Actions. `render.yaml` is a blueprint for the API and a
free PostgreSQL. The frontend
goes to Vercel with one variable, `NEXT_PUBLIC_API_URL`. The hourly research
cycle runs from GitHub Actions rather than a paid scheduler. Total to launch:
nothing. The full runbook is in `docs/DEPLOYMENT.md`.

It launches in demo mode, and says so on every page. Serving the synthetic
dataset with `is_demo` on every row is the honest launch state; turning it off
before the Solana and X providers exist produces a correct, empty system rather
than a better one.

---

## What runs today

| Capability | State |
| --- | --- |
| Database schema + migrations for the full research chain (22 tables) | implemented |
| Read API: observations, hypotheses, experiments, traces, patterns, memory, events, metrics | implemented |
| Demo mode over fixtures, every row flagged `is_demo` | implemented |
| Memory: store, embed, rank by cosine, related, cluster, digest | implemented |
| Embeddings | local deterministic hashing — **lexical, not semantic**, and reported as such |
| Observation pipeline: ingest → filter → score → 10 anomaly detectors → store | implemented, deterministic |
| Draft approval / rejection behind an operator token | implemented |
| Publishing to X | deliberately refuses (501) — external integrations come last |
| Frontend: 14 routes + public hypothesis, experiment, findings and memory pages | implemented |
| Hypothesis engine: 6 templates, memory consulted before each question | implemented, deterministic |
| Experiment engine: token-hour cohorts, two-proportion tests, strata, chronological split | implemented, deterministic |
| Critic: 10 design checks + the gate blocking `SUPPORTED` without a `PASS` | implemented, deterministic |
| Researcher / data scientist / critic / writer / reviewer *agents* (model-backed) | not implemented — scheduled last |
| Model client + writer and reviewer agents, behind a budget guard | implemented; refuse to run until a key, roles and prices are set |
| Solana + X providers | interfaces only — scheduled last |
| SSE live streaming: `GET /api/live/stream`, resumable by cursor | implemented |

### About the research engine

```
anomaly → memory search → hypothesis → dataset → experiment → critic → result → memory → draft
```

The unit of analysis is a **token-hour**. Exposure is read on a trailing window;
the outcome strictly later. Each hypothesis declares its falsification condition
*and its direction* before the data is seen, so an effect pointing the opposite way
falsifies rather than confirms. A group under 30 token-hours returns `INCONCLUSIVE`
— a sample that cannot settle a question is not allowed to look like a verdict.
Every experiment stores the dataset version and a content hash of its exact rows.

On the demo series this produces 5 hypotheses, 5 experiments and 5 `INCONCLUSIVE`
results, with the critic reporting why: six tokens is not enough independent data.
That is the honest answer, and it is the one published.

### About the observation pipeline

```
source → normalize → deterministic filter → detectors → novelty/importance/confidence → store
```

No model is called anywhere in it. Every observation it writes carries
`llm_reviewed=False`, every anomaly names a versioned detector and records the
thresholds it used, and each run reports how many candidates it dropped and why. On
the demo dataset one full replay drops 134 candidates and records 9 observations —
that ratio *is* the cost architecture.

The dataset (`scripts/generate_demo_timeseries.py` → `data/fixtures/timeseries.json`)
plants one pattern per token and one control that must stay silent:

| Token | Planted | Detector that must fire |
| --- | --- | --- |
| SURGE | volume ×6 at hour 12 | volume acceleration |
| DRAIN | liquidity −62% at hour 15 | liquidity change |
| WHALE | top-10 concentration 0.28 → 0.71 | concentration change |
| BUZZ | mentions ×8, participation flat | social/on-chain divergence |
| OLD | 7 days old, liquid, quiet | survival anomaly |
| **FLAT** | **nothing** | **none — a detector that fires here is broken** |

### About the embedder

Memory ranks by cosine over vectors from a local hashing embedder: deterministic,
free, and reproducible across machines. It matches **wording, not meaning** — so
`semantic` is `false` everywhere it is reported, and it stays false until a learned
model is wired in. The similarity threshold (0.12) was measured, not guessed: on the
demo corpus unrelated queries top out near 0.06 and the weakest true match scores
about 0.15.

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
backend/.venv/Scripts/python -m pytest          # 154 tests
backend/.venv/Scripts/python -m ruff check backend tests scripts
cd frontend && npm run typecheck && npm run build
backend/.venv/Scripts/python scripts/check_phase1.py
backend/.venv/Scripts/python scripts/check_phase2.py
backend/.venv/Scripts/python scripts/check_phase3.py
```

Run the pipeline by hand:

```bash
cd backend && .venv/Scripts/python -m app.workers.observe             # one cycle
cd backend && .venv/Scripts/python -m app.workers.observe --backfill  # replay the series
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
  agents/      model-backed agents (scheduled last)
  workers/     observe + research CLI cycles
frontend/      Next.js app router, one route per public surface
data/fixtures/ the only data source in demo mode
docs/          architecture, methodology, identity, security, cost, publishing
tests/         78 tests over the API, seeding, fixtures and security invariants
```

## Rules this codebase enforces

- A measurement that no source provided is `null`. It is never filled in.
- A stored vector names the model that produced it, or it is not used for ranking.
- Storing the same memory twice is not learning: content hashes deduplicate.
- A detector that cannot measure a field returns no verdict — never a verdict of zero.
- Every rejected candidate is counted under a named reason, so "nothing found" is
  distinguishable from "nothing looked at".
- A hypothesis without a falsification condition is rejected by the schema.
- A result cannot be `SUPPORTED` without a passing critic verdict.
- External text — posts, token names, wallet labels, metadata — is data, never
  instruction (`app/core/untrusted.py`, enforced by tests).
- No private keys, no signing, no transaction construction. A test fails the build
  if any such symbol appears in `backend/app`.

See `CLAUDE.md` for working conventions and `docs/` for the long form.
