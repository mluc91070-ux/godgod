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
| Agents | `backend/app/agents` | Model-backed agents; scheduled last. Empty today. |
| Workers | `backend/app/workers` | `observe` and `research` cycles, runnable from the CLI. |
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

## Observation (PHASE 3)

```
ObservationSource ─▶ window ─▶ filter ─▶ detectors ─▶ scoring ─▶ observation + anomalies
                                  │                                    │
                            named drop reasons                   events, memory, agent_run
```

`app/providers/source.py` defines `ObservationSource`, one level above the raw
RPC/API providers: the pipeline consumes normalized measurements over time, not
RPC calls. Today the only implementation reads the synthetic time series; a live
implementation fills the same interface later and the pipeline does not change.

**Windows.** A window is a trailing series plus the newest measurement. Nothing is
interpolated: a field missing from a snapshot is missing from the series, and a
detector that needs it returns no verdict.

**Filter.** Cheap gates run before any scoring: minimum history, minimum liquidity,
minimum holders, and a cooldown that treats a repeat of the same anomaly on the same
subject as a duplicate. Standing conditions (survival, cluster appearance) get a
24-hour cooldown because they describe a state that persists, not an event.

**Detectors.** Ten deterministic functions (`DETECTOR_NAMES`), each returning the
baseline it compared against, the measurement that fired it, and the thresholds it
used. Same window in, same verdict out. Scores are bounded to [0.1, 1.0] — a fired
detector that reported 0.00 would read as a bug.

**Scoring.** `novelty` is 1 − max cosine against recent observations (the memory
embedder, reused). `importance` is 0.6 × strongest anomaly + 0.4 × a bounded log of
liquidity. `confidence` is the completeness of the measurement — confidence in the
data, not in a conclusion.

**Anchoring.** The window ends at `as_of`, defaulting to the newest measurement the
source has rather than the wall clock. A frozen dataset stays observable, and
`run_backfill` walks the series hour by hour exactly the way a live loop would.

**Output.** An `Observation` (+ `Anomaly` rows), a `SystemEvent` per observation and
per anomaly, a memory entry when importance clears the floor, and one `AgentRun` row
per cycle with `model=null` and `estimated_cost_usd=0.0` — because nothing was
called, not because nothing was measured.

## Research (PHASE 4-6)

```
anomalies ─▶ templates ─▶ hypothesis ─▶ build_dataset ─▶ evaluate ─▶ review ─▶ result
                 │            │                                        │         │
          memory searched  trace step                            critic checks  memory, draft, pattern
```

`app/services/research/` holds five modules with one job each:

| Module | Responsibility |
| --- | --- |
| `templates.py` | six question templates: trigger, outcome, horizon, direction, threshold |
| `dataset.py` | token-hour rows, strata, no-look-ahead, content hash, named exclusions |
| `stats.py` | two-proportion z-test and Cohen's h, no scientific dependency |
| `experiments.py` | the decision order, pooled and per-stratum comparison, stability |
| `critic.py` | ten design checks and the `SUPPORTED` gate |
| `cycle.py` | wires them together and writes hypothesis, experiment, trace, memory, draft |

**Why templates and not a model.** The same reason detectors are not prompts: a
hypothesis whose falsification condition was written by a model *after* seeing the
data is not falsifiable. Templates fix the question and its threshold in advance,
and are versioned so an old result stays interpretable. The model layer, when it
arrives, proposes new templates for a human to accept — it does not judge the run.

**Direction is part of the hypothesis.** `expected_direction` (+1 / −1) is compared
against the observed difference. Without it, a hypothesis predicting a *decrease*
would be confirmed by a large *increase*, which is how a system convinces itself it
found something.

**Where the sample is too small to speak.** `MIN_CELL = 30` per group. Below it the
result is `INCONCLUSIVE` with the reason stated, ranked *above* the falsification
check in the decision order so noise cannot masquerade as a rejection.

**Output.** A `Hypothesis` (with the memory ids consulted before it was written), an
`Experiment` (dataset version + hash + parameters), an `ExperimentResult` (metrics,
p-value, effect size, all ten critic checks, limitations), trace steps for every
stage, a `Memory` entry, a `Pattern` update, a templated `ContentDraft` marked
`PENDING`, and one `AgentRun` with `model=null` and `estimated_cost_usd=0.0`.

## Live stream (PHASE 9)

```
system_events ──seq cursor──▶ event_stream ──SSE──▶ terminal page
```

`GET /api/live/stream` is server-sent events over rows the pipeline and research
cycle already commit. There is no message bus: the writers and the reader share
one database, and a queue would be a second source of truth for no gain at this
scale.

- Frames: `open` (version, cursor, what this connection will do), `log` (one
  event row), `state` (derived state changed), `close` (ageing out). Heartbeats
  are `:` comments so they fire no client handler.
- `replayed: true` marks history. A demo database holds events with past
  timestamps; showing them as if they had just arrived would be dishonesty
  introduced by the transport.
- Every frame carries `id: <seq>`. The browser resends it as `Last-Event-ID`, so
  a reconnect resumes exactly where it stopped — nothing skipped, nothing twice.
- `STREAM_MAX_SECONDS` caps a connection's life; the client reconnects with its
  cursor, so a forgotten tab does not poll forever.
- Each poll opens its own short-lived session. An idle transaction pinned for the
  life of a connection is how a pool dies.

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

Read: `/health`, `/api/status`, `/api/live`, `/api/live/stream` (SSE),
`/api/observations[/:id]`,
`/api/hypotheses[/:id]`, `/api/experiments[/:id]`, `/api/traces[/:id]`,
`/api/patterns`, `/api/memory[/:id]`, `/api/memory/search`,
`/api/memory/:id/related`, `/api/memory/:id/cluster`, `/api/memory/summary`,
`/api/events`,
`/api/metrics`, `/api/agents`, `/api/agents/runs`, `/api/sources`,
`/api/tokens[/:address]`, `/api/x/drafts`.

Write (operator token required): `/api/admin/research/run`,
`/api/x/drafts/:id/approve`, `/reject`.
`/publish` exists and refuses with 501 — see `X_PUBLISHING.md`.

## Deferred by design

The model-backed agents, the live providers and every
model call (scheduled last, by decision). Each is reported as unimplemented by
`/api/status` rather than stubbed with fake behaviour.

One branch ships **unverified**: the pgvector ordering in `_rank_postgres`. No
PostgreSQL instance was available on the development machine, so only the Python
path is covered by tests. It is marked as such in the source, and a Postgres
deployment exercises it on its first search.
