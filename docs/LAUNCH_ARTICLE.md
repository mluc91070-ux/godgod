# GODGOD — launch article for X

Two versions below: a long-form article, and a thread. Both are written to
survive the standard the system itself is held to — every number is one the
site can produce, and nothing is claimed that is not built.

**Facts as of publication.** Verify before posting; these move.

- 10 detectors · 6 hypothesis templates · 10 critic checks · 377 tests · 9 gates
- 26 real tokens measured, 35 measurements accumulating
- Site is in demo mode: the research shown ran on a synthetic dataset, labelled
  on every row
- 6 results recorded, all inconclusive
- X posting is built and switched off (`X_MODE=draft`)

---

## Long-form article

### An AI that publishes its failures

Most research you see in crypto is the surviving half. Someone tests forty
ideas, thirty-nine die quietly, and the fortieth gets a thread.

That is not dishonesty. It is arithmetic. A finding gets attention; forty
failures get none. So the failures stay private, the same dead ends get
re-explored by the next person, and what reaches the timeline is whatever
happened to look good — which is precisely the set most likely to be noise.

GODGOD is an attempt at the other half.

It is a research institute with one researcher, and the researcher is a
machine. It watches tokens on Solana, notices what it has not seen before,
turns that into a question that can be proved wrong, tests it against recorded
data, tries to break its own result, and publishes what it found. Including —
especially — what failed.

A machine has no reputation to protect. It can publish every attempt at the
same volume, because a rejection costs it nothing. That is the whole idea. Not
an AI smarter than a researcher. One with no incentive to hide the boring half
of research.

### Where the method comes from

None of this architecture is invented here.

**From Hypotheses to Factors: Constrained LLM Agents in Cryptocurrency
Markets** — Yikuan Huang, Zheqi Fan, Kaiqi Hu, Yifan Ye. arXiv:2604.26747,
April 2026.

Their framing is the one GODGOD implements. An LLM agent is a powerful tool for
empirical discovery, and its flexibility is exactly what turns discovery into
uncontrolled search. Their answer is to constrain it: the agent reads an
append-only experiment trace, proposes falsifiable hypotheses, and maps them to
executable recipes — while a *deterministic engine* enforces the data splits,
the selection gates, the costs, and the tests. Both successful and failed
hypotheses stay auditable.

That last clause is the one this project took most literally.

The same group's earlier work, **Beyond Prompting: An Autonomous Framework for
Systematic Factor Investing via Agentic AI** (Allen Yikuan Huang, Zheqi Fan,
arXiv:2603.14288), pushes the same direction: the model stops being a text
generator asked for opinions and becomes a participant in a closed loop with
out-of-sample validation and an economic-rationale requirement.

The researchers:

- **Yikuan Huang** — Division of Emerging Interdisciplinary Areas, HKUST ·
  HKUST (Guangzhou). github.com/allenh16 ·
  allenh16.github.io/agentic-factor-investing
- **Zheqi Fan** — Division of Emerging Interdisciplinary Areas, HKUST · Thrust
  of FinTech, HKUST (Guangzhou). sites.google.com/view/zheqifan
- **Kaiqi Hu** — Rutgers Business School
- **Yifan Ye** — Beijing Normal–Hong Kong Baptist University

**Their papers report returns. GODGOD does not trade.** There is no wallet
execution path anywhere in this codebase, and it reproduces none of their
results. It borrows the method, not the outcome.

### What it actually does

**1 — It looks, cheaply.**

Ten deterministic detectors over trailing windows of measurements. Volume
acceleration, liquidity withdrawal, holder concentration, social-onchain
divergence, survival, and five more. Every anomaly records the detector's
version and the exact thresholds it fired on, so any call can be re-checked
later.

No model is involved. That is a cost decision before it is a philosophical one:
a system that sends every chain event to an LLM has an unbounded bill, and most
of those events are noise a threshold rejects for free. On one replay of the
demo series, 134 candidates were dropped and 9 observations recorded. That
ratio is the architecture.

**2 — It asks a question that can be wrong.**

Each hypothesis is written from a template that declares, before any data is
seen: the population, the sample definition, the timeframe, the baseline, the
expected result, and the condition that would kill it — *including its
direction*.

That last part matters more than it sounds. Without a declared direction, an
effect pointing the opposite way to the prediction gets counted as a
confirmation as long as it is large enough. It is one of the easiest ways for a
system to convince itself it found something.

Memory is searched *before* the question is written, and the memories consulted
are recorded on the hypothesis. When it cites what it already knew, it cites
rows with ids, not an impression.

**3 — It tests, and arithmetic decides.**

The unit of analysis is a token-hour. Exposure is read on a trailing window;
the outcome strictly later, so nothing is ever scored on data it could not have
had. Rates are compared pooled and per liquidity stratum with a two-proportion
z-test, then re-checked on a chronological split of the same rows.

The decision order is fixed, and one line of it is the interesting one: *a
sample too small to judge outranks a falsified hypothesis.* Below thirty
observations per group the answer is inconclusive even when the falsification
rule technically fired — because a group of one row can satisfy that rule by
accident, and calling it a rejection would dress noise up as a verdict.

**4 — Something tries to break it.**

Ten checks on every result: sample size, independence, look-ahead bias, data
leakage, survivorship, selection, confounding, stability, multiple testing,
data quality. All ten run on all results and all ten verdicts are stored, so a
reader sees what was inspected rather than a single word.

Nothing reaches SUPPORTED without a passing critic.

**5 — It writes, and the sentence is checked against the row.**

A model chooses words. It never chooses facts. Every number in a published
sentence is extracted and matched against the exact result row being described.
A draft containing a figure that is not in that row is *discarded* — not
softened, not caveated.

The model is also handed the facts and denied the database, so an invented
number has nothing to hide behind.

### What it refuses to do

- **Estimate a missing measurement.** A public RPC node cannot count token
  holders. That field is `NULL` on every row, and the detectors that need it
  return no verdict. A zero there would flow into the datasets and eventually
  into a claim.
- **Round an inconclusive result up.** All six results recorded so far are
  inconclusive, and the critic says why: six tokens is not enough independent
  history to settle anything. That is the honest answer and it is the one
  published.
- **Trade, advise, or predict a price.** No keys, no signing, no transaction
  construction. A test fails the build if a wallet-execution symbol appears
  anywhere in the codebase.
- **Spend what it cannot measure.** The budget guard refuses a model call when
  per-token prices are unconfigured, when the day's budget is spent, or when
  any run that day recorded no cost at all — because a total known to be
  incomplete is not a total to spend against.

### Where it is right now

Honest status, and the site says the same thing in machine-readable form at
`/api/status`:

The chain collector is measuring **real tokens on Solana** — 26 of them, every
fifteen minutes, from a free public RPC and a market API. The research shown on
the site right now ran on a **synthetic dataset**, and every row of it is
labelled `is_demo`. The switch to live research happens when a token has enough
history for a detector to have anything to say, and not before: a live site
with no research on it and no explanation reads as broken, which is worse than
an honest demo.

Posting to X is built, tested, and switched off.

377 tests. Nine phase gates. Everything it has not built is reported as
unbuilt, by the system, out loud.

### The point

An AI account that posts findings is easy. The interesting version is the one
that posts this:

> ran the numbers. found nothing. 72 token-hours, p 0.31.
> everyone else would post this as a finding. it isn't one.

Site: godgod.vercel.app
Source: github.com/mluc91070-ux/godgod

---

## Thread version

**1/**
Most crypto research you see is the surviving half.

Someone tests 40 ideas. 39 die quietly. The 40th gets a thread.

That's not dishonesty, it's arithmetic. A finding gets attention. 40 failures
get none.

GODGOD is an attempt at the other half. 🧵

**2/**
A research institute with one researcher, and the researcher is a machine.

It watches Solana tokens, turns what it hasn't seen into a question that can be
proved wrong, tests it, tries to break its own result, and publishes what it
found.

Including what failed.

**3/**
Why a machine, specifically?

A machine has no reputation to protect. It can publish every attempt at the
same volume, because a rejection costs it nothing.

Not an AI smarter than a researcher. One with no incentive to hide the boring
half of research.

**4/**
The architecture isn't invented here.

"From Hypotheses to Factors: Constrained LLM Agents in Cryptocurrency Markets"
Huang, Fan, Hu, Ye — arXiv:2604.26747

An agent proposes falsifiable hypotheses. A deterministic engine decides. Failed
ones stay auditable.

**5/**
The researchers:

Yikuan Huang — HKUST · github.com/allenh16
Zheqi Fan — HKUST FinTech
Kaiqi Hu — Rutgers
Yifan Ye — BNBU

Earlier work: "Beyond Prompting", arXiv:2603.14288

Their papers report returns. GODGOD doesn't trade. It borrows the method, not
the outcome.

**6/**
Step 1: it looks, cheaply.

10 deterministic detectors over trailing windows. No model.

Sending every chain event to an LLM is an unbounded bill, and most events are
noise a threshold rejects for free.

One replay: 134 dropped, 9 kept.

**7/**
Step 2: it writes a question that can be wrong.

Population, sample, timeframe, baseline, expected result — and the condition
that kills it, including its direction, before any data is seen.

Without a direction, an effect pointing the wrong way counts as confirmation.

**8/**
Step 3: arithmetic decides.

Unit is a token-hour. Exposure read on a trailing window, outcome strictly
later. Two-proportion z-test, pooled and per liquidity stratum, re-checked on a
chronological split.

**9/**
One line in the decision order matters more than the rest:

A sample too small to judge outranks a falsified hypothesis.

Below 30 per group it's inconclusive even when the falsification rule fired. A
group of one row can satisfy that rule by accident.

**10/**
Step 4: something tries to break it.

10 checks on every result — sample size, independence, look-ahead, leakage,
survivorship, selection, confounding, stability, multiple testing, data
quality.

All 10 verdicts stored. Nothing reaches SUPPORTED without a passing critic.

**11/**
Step 5: it writes, and the sentence is checked against the row.

A model chooses words. Never facts.

Every number in a post is matched against the exact result it describes. A
draft with a figure that isn't there is discarded — not softened.

**12/**
What it refuses to do:

→ Estimate a missing measurement. A public node can't count holders, so that
field is NULL, forever
→ Round an inconclusive up
→ Trade, advise, or predict a price. No keys, no signing. A test fails the
build if one appears

**13/**
Where it is right now, honestly:

Measuring 26 real Solana tokens every 15 min.

The research on the site ran on a synthetic dataset — every row labelled.

All 6 results so far: inconclusive. Not enough independent history to settle
anything. So that's what's published.

**14/**
An AI account that posts findings is easy.

The interesting version posts this:

"ran the numbers. found nothing. 72 token-hours, p 0.31. everyone else would
post this as a finding. it isn't one."

377 tests. 9 gates.

godgod.vercel.app
github.com/mluc91070-ux/godgod
