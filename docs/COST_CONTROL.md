# Cost control

Target ceiling: **$250/month**, and PHASE 1 spends $0.

| Line | Target |
| --- | --- |
| Anthropic | $50–100 |
| Solana RPC | $0–30 |
| Database | $0–25 |
| Hosting | $0–20 |
| X / data | $20–50 |
| Worker | $10–30 |
| Reserve | remainder |

## The architectural decision that matters

```
raw data → deterministic filter → novelty score → anomaly detection → LLM
```

The model is the last step. A meme-observation system that sends every chain
event to a model has an unbounded bill, and most of those events are noise a
threshold can reject for free.

Every observation carries `novelty_score`, `importance` and `confidence`. Only
observations that clear those bars may trigger reasoning. `llm_reviewed` on the
observation row records whether a model was ever involved — it is `false`
everywhere today, because no model has been called.

**Measured on the demo dataset (PHASE 3).** One full replay of the 24-hour synthetic
series: 18 cycles, 108 subject-examinations, **134 candidates dropped**, 9
observations recorded, 11 anomalies, 5 memories written, **0 model calls**, about
1.6 seconds total. Every rejection is counted under a named reason
(`insufficient_history`, `below_liquidity_floor`, `duplicate_anomaly`,
`not_novel_no_anomaly`, …) and returned in the run report, so the filter's work is
visible rather than assumed.

That ratio is the whole argument: if all 108 examinations had gone to a model at
even a fraction of a cent each, a single day of six tokens would cost more than the
month's budget for the entire system.

## Mechanisms

- **Event filtering** — deterministic detectors decide what is even a candidate.
- **Duplicate detection** — the same anomaly on the same subject is not re-reasoned.
- **Model routing** — `MODEL_FAST` for extraction and normalization,
  `MODEL_REASONING` for hypotheses and experiments, `MODEL_WRITER` for drafts,
  `MODEL_CRITIC` for review. Never hard-code a model name; all four are
  environment variables.
- **Prompt minimization** — send the rows needed, not the table.
- **Memory retrieval limits** — `MEMORY_RETRIEVAL_LIMIT` (default 20) caps how
  much context a hypothesis may pull.
- **Batching** — provider reads are grouped; snapshots are periodic, not per-tick.
- **Caching** — repeated prompts hit a cache before a provider.
- **Experiment scheduling** — experiments run on a cadence, not on every anomaly.
- **Budget** — `LLM_DAILY_BUDGET_USD` (default 3.0) is the daily ceiling.

## Accounting

`agent_runs` stores model, duration, token counts and `estimated_cost_usd` per
run. `metrics_snapshots` aggregates daily / weekly / monthly. `/api/metrics`
exposes the totals, and the admin cost dashboard reads from there.

In PHASE 1 the cost total is `null` — not zero-because-we-guessed, but null
because no run has happened.

## Infrastructure choices

- SQLite locally, Supabase PostgreSQL (free tier) first in production.
- Vercel free tier for the frontend.
- A single small worker process for research cycles.
- pgvector inside the same PostgreSQL instance — no separate vector database.
