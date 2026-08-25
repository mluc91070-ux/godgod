# AGENTS.md

Six agents. Each answers exactly one question and holds only the tools that
question requires. None of them is implemented in PHASE 1 — the roster in
`data/fixtures/agents.json` is loaded into the `agents` table with
`implemented: false`, and `/agents` on the site says so.

The subagent definitions used when developing this repository live in
`.claude/agents/`.

---

## observer — "What happened?"

- **Inputs**: Solana RPC (read-only), X search results, token/social fixtures.
- **Outputs**: `Observation`, `Anomaly`.
- **Tools**: `solana_provider.read`, `x_provider.read`, write access to
  `observations` and `anomalies` only.
- **Model role**: `MODEL_FAST`.
- **Rules**: normalizes only fields a provider actually returned; a missing field
  stays missing. Runs *after* deterministic filtering — it must never be handed
  the raw firehose.

## researcher — "What could explain this?"

- **Inputs**: observations, anomalies, memory search results, previous experiments.
- **Outputs**: `Hypothesis`.
- **Tools**: `memory.search`, write access to `hypotheses`.
- **Model role**: `MODEL_REASONING`.
- **Rules**: memory retrieval happens *before* hypothesis generation. Every
  hypothesis must define population, sample, timeframe, baseline, expected result
  and a falsification condition. "Lore is important" is not a hypothesis.

## data_scientist — "Does the data support it?"

- **Inputs**: a hypothesis, token snapshots, social posts.
- **Outputs**: `Experiment`, `ExperimentResult`.
- **Tools**: database read, write access to `experiments` / `experiment_results`, compute.
- **Model role**: `MODEL_REASONING`.
- **Rules**: records dataset version and content hash, sample size, train /
  validation / out-of-sample periods, and limitations. No look-ahead, no leakage,
  no survivorship or selection bias, no multiple-testing abuse.

## critic — "Why might this be wrong?"

- **Inputs**: experiment, result, dataset metadata.
- **Outputs**: `PASS` | `FAIL` | `NEEDS_MORE_DATA` plus per-check notes.
- **Tools**: database read, write to the `critic_*` fields only.
- **Model role**: `MODEL_CRITIC`.
- **Checks**: sample size, bias, data quality, selection, leakage, overfitting,
  confounders, stability.
- **Rule**: a hypothesis cannot become `SUPPORTED` without a passing critic.

## writer — "Is there something worth communicating?"

- **Inputs**: observations, hypotheses, results, memories.
- **Outputs**: `ContentDraft` (OBSERVATION, HYPOTHESIS, EXPERIMENT, RESULT,
  FAILURE, DISCOVERY, THOUGHT).
- **Tools**: database read, write to `content_drafts`.
- **Model role**: `MODEL_WRITER`.
- **Rules**: short, specific, evidence-based. No hype, no engagement bait, no
  promises, no invented numbers. Silence is a valid output — there is no posting
  schedule.

## reviewer — "Is every claim supported by a stored result?"

- **Inputs**: a draft and the row it derives from.
- **Outputs**: `PASS` | `FAIL` with a reason.
- **Tools**: database read, write to the `reviewer_*` fields only.
- **Model role**: `MODEL_CRITIC`.
- **Rejects**: unsupported claims, fabricated statistics, misleading wording,
  duplicates, hype, financial promises. A draft with no recorded source cannot be
  approved — the API enforces this too (422).

---

## Autonomy levels

| Level | Meaning | V1 |
| --- | --- | --- |
| 0 | read only | available |
| 1 | research + draft | **default** |
| 2 | human approval + publish | after PHASE 7 |
| 3 | limited autonomous publishing | not enabled |
| 4 | future experimental actions | not designed |

No level grants wallet execution. That path does not exist in the codebase.
