# Architecture

## Shape

```
                    ┌─────────────── deterministic ───────────────┐
solana rpc ───┐     │                                             │
x search   ───┼──▶ raw events ─▶ filter ─▶ novelty ─▶ anomaly ─────┼─▶ observation
fixtures   ───┘     │            (cheap, no model calls)          │
                    └─────────────────────────────────────────────┘
                                                                   │
                                              memory search ◀──────┤
                                                     │             │
                                                     ▼             ▼
                                                 hypothesis ──▶ experiment ──▶ critic
                                                     │                          │
                                                     └────────▶ result ◀────────┘
                                                                  │
                                                    memory update ┴─▶ draft ─▶ (human) ─▶ X
```

The model is the last step in each row, never the first. Everything that can be
decided by a threshold, a z-score or a SQL query is decided that way.

## Components

| Layer | Path | Responsibility |
| --- | --- | --- |
| API | `backend/app/api` | HTTP surface only. No business logic. |
| Schemas | `backend/app/schemas` | Pydantic contracts shared with the frontend. |
| Services | `backend/app/services` | Fixtures, seeding, derived state. |
| Models | `backend/app/models` | SQLAlchemy tables. |
| DB | `backend/app/db` | Async engine, portable column types. |
| Providers | `backend/app/providers` | Vendor-neutral Solana / X interfaces. |
| Agents | `backend/app/agents` | PHASE 3–6. Empty today. |
| Workers | `backend/app/workers` | Scheduled research cycles. PHASE 3+. |
| Frontend | `frontend/` | Next.js app router, server components, no keys. |

## Data model

22 tables. Every table has `id` (UUID string), `created_at`, `updated_at` and
`is_demo`.

- **On-chain**: `tokens`, `token_snapshots`, `wallets`, `wallet_clusters`
- **Social**: `social_accounts`, `social_posts`
- **Research**: `observations`, `anomalies`, `hypotheses`, `experiments`,
  `experiment_results`, `patterns`, `research_sources`, `research_traces`,
  `trace_steps`
- **Memory**: `memories` (with a `vector` column on PostgreSQL)
- **Content**: `content_drafts`, `published_posts`
- **System**: `agents`, `agent_runs`, `system_events`, `metrics_snapshots`

Blockchain identifiers (token mints, wallet addresses, post ids) are stored as
strings in dedicated columns. They are never used as primary keys and never
coerced into UUIDs.

`token_snapshots` exists because an experiment needs measurements *at a point in
time*; the latest value on `tokens` is a convenience, not evidence.

## Memory (PHASE 2)

`app/services/memory.py` exposes five operations:

| Operation | What it does |
| --- | --- |
| `store_memory` | embeds, hashes and writes one memory; refuses exact duplicates |
| `search_memory` | ranks by cosine (`mode="vector"`) or substring (`mode="lexical"`) |
| `retrieve_related_memories` | neighbours of one memory, seed excluded |
| `get_memory_cluster` | seed plus everything above a similarity threshold |
| `summarize_memory` | structural digest: counts, recurring terms, recent failures |

Ranking takes one of two paths, and always reports which one in `method`:

- **PostgreSQL** → `ORDER BY embedding <=> :query` with an HNSW
  `vector_cosine_ops` index (migration `0002`).
- **anything else** → a bounded Python cosine pass over at most
  `MEMORY_SCAN_LIMIT` rows, with `truncated: true` when the cap was hit.

The embedder (`app/services/embeddings.py`) is a signed-hash bag of unigrams and
bigrams, L2 normalized, built on blake2b so the same text produces the same vector
on any machine forever. That property is what makes a stored vector reproducible —
and it is why `embedding_model` is written next to every vector, and why
`search_memory` ignores rows embedded by a different model.

It is **lexical**: it matches wording, not meaning. `EmbeddingProvider.semantic`
carries that fact into `/api/memory/search` and `/api/status`, and nothing may
report `semantic: true` until a learned model is wired in. Swapping one in means
implementing `EmbeddingProvider`, setting `EMBEDDING_MODEL`, and running
`scripts/backfill_embeddings.py`.

## Portability

`app/db/types.py` defines two column types:

- `JSONDict` → `JSONB` on PostgreSQL, `JSON` elsewhere.
- `Embedding` → `vector(1536)` on PostgreSQL (pgvector), JSON-encoded text on
  SQLite. The SQLite path stores vectors but cannot rank by distance — which is
  why PHASE 2 vector search is a PostgreSQL feature, and the API reports
  `semantic: false` until it exists.

Migrations are dialect-neutral: the initial migration enables the `vector`
extension when it detects PostgreSQL and skips it otherwise.

## State machine

`IDLE → OBSERVING → ANALYZING → HYPOTHESIZING → TESTING → {REJECTED | SUPPORTED}
→ LEARNING`

`app/services/state.py` derives the current state from the most recent
`system_events` row. The homepage field visualization binds ring count and speed
to activity, distortion to novelty, and core radius to confidence. There is no
random animation: a frozen system draws a frozen field.

## API surface

Read: `/health`, `/api/status`, `/api/live`, `/api/observations[/:id]`,
`/api/hypotheses[/:id]`, `/api/experiments[/:id]`, `/api/traces[/:id]`,
`/api/patterns`, `/api/memory[/:id]`, `/api/memory/search`,
`/api/memory/:id/related`, `/api/memory/:id/cluster`, `/api/memory/summary`,
`/api/events`,
`/api/metrics`, `/api/agents`, `/api/agents/runs`, `/api/sources`,
`/api/tokens[/:address]`, `/api/x/drafts`.

Write (operator token required): `/api/x/drafts/:id/approve`, `/reject`.
`/publish` exists and refuses with 501 — see `X_PUBLISHING.md`.

## Deferred by design

SSE streaming (PHASE 9), the six agents (PHASE 3–6), the live providers and every
model call (scheduled last, by decision). Each is reported as unimplemented by
`/api/status` rather than stubbed with fake behaviour.

One branch ships **unverified**: the pgvector ordering in `_rank_postgres`. No
PostgreSQL instance was available on the development machine, so only the Python
path is covered by tests. It is marked as such in the source, and a Postgres
deployment exercises it on its first search.
