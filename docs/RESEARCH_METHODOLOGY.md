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

PHASE 1 stores memory and searches it lexically. Vector retrieval is PHASE 2 and
the API says `semantic: false` until then.
