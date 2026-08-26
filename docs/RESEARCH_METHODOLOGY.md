# Research methodology

## The cycle

```
observation → question → hypothesis → test → critic → result → memory → next hypothesis
```

Nothing skips the critic, and nothing skips memory.

## What counts as a hypothesis

A hypothesis must be measurable, testable, falsifiable and reproducible. The
schema enforces the parts:

| Field | Why it is required |
| --- | --- |
| `statement` | the claim, stated so it can be wrong |
| `question` | the thing actually being asked |
| `variables` | independent, dependent, controls |
| `population` | who is eligible |
| `sample_definition` | who is included, and the minimum data required |
| `timeframe` | exposure window and outcome window |
| `baseline` | what the treated group is compared against |
| `expected_result` | stated *before* the test |
| `falsification_condition` | what result would kill it |

Not a hypothesis: "lore is important."

A hypothesis: "tokens showing sustained independent social propagation during
their first 6 hours have a higher probability of remaining active after 7 days
than matched tokens without sustained propagation."

## Experiments

Stored with everything needed to re-run them: `dataset_version`, `dataset_hash`
(content hash of the exact data), `features`, `parameters`, `method`,
`sample_size`, `train_period`, `validation_period`, `out_of_sample_period`,
`limitations`.

Biases to design against, and to state which apply:

- **look-ahead** — using information that did not exist at decision time
- **data leakage** — outcome information reaching the features
- **survivorship** — sampling only what still exists
- **selection** — the label built from the same window used to find the anomaly
- **multiple testing** — trying enough splits that one becomes significant

## What PHASE 4-6 actually implements

The engines are deterministic: templates, thresholds and statistics. No model is
called, and `llm_calls` on every research run is `0`.

**Unit of analysis: the token-hour.** One token at one measurement. Exposure is
evaluated on the trailing window ending at that hour; the outcome is read
strictly `horizon_hours` later. A row whose outcome cannot be measured is
excluded under a named reason, never defaulted.

**Six question templates** (`app/services/research/templates.py`), one per anomaly
type that has a testable follow-up. Each declares its population, sample
definition, timeframe, baseline, expected result, falsification condition,
`min_effect_pp`, and — the part that makes falsification real — an
`expected_direction` of `+1` or `-1`.

> Without a declared direction a hypothesis is unfalsifiable in practice: an
> effect pointing the opposite way to the prediction would otherwise count as a
> confirmation as long as it was large enough. The engine therefore compares
> `difference_pp × expected_direction` against the threshold, and an effect in
> the wrong direction is *rejected*, not celebrated.

**The comparison.** Exposed against control, pooled and per liquidity stratum,
with a two-proportion z-test (`app/services/research/stats.py`, normal
approximation, no dependency). Effect size is reported as Cohen's h. The same
rows are then split chronologically and the sign of the difference is compared
across halves. A sign that reverses across strata falsifies.

**Decision order** (`experiments.evaluate`), applied in this order and no other:

1. empty dataset → `INCONCLUSIVE` ("nothing was tested")
2. one empty group → `INCONCLUSIVE`
3. smallest group under `MIN_CELL` (30 token-hours) → `INCONCLUSIVE`
4. falsification condition met → `REJECTED`
5. `p > 0.05` → `INCONCLUSIVE` ("not distinguishable from noise")
6. otherwise → `SUPPORTED`

Step 3 sits *above* step 4 on purpose. A group of one row can satisfy a
falsification rule by accident; calling that `REJECTED` would dress noise up as a
verdict. The result says so in words: the falsification rule is not applied to a
sample that cannot support it.

**Reproducibility.** Every experiment stores `dataset_version`
(`token-hours-v1`) and `dataset_hash` — a SHA-256 over the sorted rows, stable
under row order and sensitive to any changed outcome — plus the parameters and
features used. Two runs producing the same hash compared the same data.

**The ten critic checks** (`critic-checks-v1`): `sample_size`, `independence`,
`look_ahead_bias`, `data_leakage`, `survivorship_bias`, `selection_bias`,
`confounding`, `stability`, `multiple_testing`, `data_quality`. Every check runs
on every result and its verdict is stored, so a reader sees what was inspected
rather than a single word.

**Known limitation, stated rather than hidden:** token-hours from the same token
are not independent observations, so the effective sample is smaller than the row
count. The `independence` check reports this on every result built from fewer
than ten distinct tokens, which — on the current synthetic series — is all of
them. This is why the demo produces `INCONCLUSIVE` and not findings.

## The critic gate

Verdicts: `PASS`, `FAIL`, `NEEDS_MORE_DATA`.

A hypothesis cannot reach `SUPPORTED` without a `PASS`. A `FAIL` does not erase
the result — it is published alongside it, which is how the demo experiment
appears: rejected by its own falsification rule, with a critic that says the
sample was too small for the subgroup split it ran.

## Results

Three outcomes, all first-class:

- `SUPPORTED` — the effect held, and the critic passed.
- `REJECTED` — the falsification condition was met.
- `INCONCLUSIVE` — the data cannot distinguish the hypothesis from the baseline.

Every published result shows sample size, period, sources, method, limitations,
confidence and status. "AI predicts…" without a methodology is not publishable.

## Traces

Every cycle writes an immutable `research_trace` with ordered steps
(`OBSERVATION → ANOMALY → MEMORY_SEARCH → HYPOTHESIS → DATASET → EXPERIMENT →
CRITIC → RESULT → MEMORY_UPDATE`). The trace is shown at the bottom of the public
experiment page. It is the audit trail: it shows what was known, when, and in
what order it was decided.

## Memory

Memory retrieval happens *before* hypothesis generation. Stored memory types:
OBSERVATION, HYPOTHESIS, EXPERIMENT, RESULT, FAILURE, PATTERN, NARRATIVE, TOKEN,
WALLET, SOCIAL_EVENT, SOURCE.

The system should be able to answer: what did I previously learn about AI
memecoins? what failed? what recurred? what assumptions changed? which
experiments contradict each other? — from stored rows, not from the model's
impression.

As of PHASE 2 memory is stored with a vector, ranked by cosine, clustered by
threshold and digested structurally. Two honesty constraints ride along:

- The embedder is lexical, so `semantic: false` is reported everywhere. Ranking
  by wording is useful — "regime" finds the regime lesson — but it will not find
  a differently-worded version of the same idea, and the system must not pretend
  it can.
- The digest counts and quotes; it does not interpret. A written synthesis of
  "what I have learned" requires a model, and that comes with the external
  integrations.

The consequence for research: when a hypothesis cites memory, it cites rows with
ids and scores, not a summary someone might have imagined.
