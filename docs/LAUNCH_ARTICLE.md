# GODGOD — launch article for X

Long-form article and a thread. Both say the same three things: the system
works, here is what it does, here is what you can do on the site.

**Numbers to re-check before posting** — they move.

- 10 detectors · 6 hypothesis templates · 10 critic checks · 377 tests · 9 gates
- 26 real Solana tokens measured, every 15 minutes
- 6 results recorded, all inconclusive
- The research on the site ran on a synthetic dataset (demo mode), labelled on
  every row
- X posting is built and switched off (`X_MODE=draft`)

---

## Long-form article

### GODGOD is live

An autonomous research system that studies how meme narratives propagate on
Solana. It runs end to end, on its own, and everything it produces is on the
site.

It is not a trading bot. There is no wallet execution path anywhere in the
codebase — no keys, no signing, no transaction construction.

**godgod.vercel.app**

### What it does

Five steps, running on a loop every fifteen minutes.

**It measures.** Real tokens on Solana, through a public RPC node and a market
API. Liquidity, volume, trade counts, holder concentration. Anything it cannot
measure stays empty — a public node cannot count token holders, so that field
is null rather than estimated.

**It notices.** Ten deterministic detectors watch trailing windows of those
measurements: volume acceleration, liquidity withdrawal, holder concentration
shifts, social-onchain divergence, survival, and five more. No model is
involved at this stage. Every anomaly records which detector fired, its
version, and the exact thresholds used — so any call can be re-checked later.

**It asks.** Each anomaly becomes a question written from a template that
declares, before any data is seen: who is in the sample, over what timeframe,
compared against what, what result is expected, and what result would prove it
wrong — including the direction. Memory is searched before the question is
written, and the rows consulted are recorded on it.

**It tests.** The unit is a token-hour. Exposure is read on a trailing window,
the outcome strictly later, so nothing is scored on data it could not have had.
Two-proportion z-test, pooled and per liquidity stratum, then re-checked on a
chronological split. Below thirty observations per group the answer is
inconclusive — a sample that small cannot settle anything, whichever way it
points.

**It criticises itself.** Ten checks on every result: sample size,
independence, look-ahead bias, data leakage, survivorship, selection,
confounding, stability, multiple testing, data quality. All ten run, all ten
verdicts are stored. Nothing is marked supported without a passing critic.

Then it writes what it found — including what failed — and every number in what
it writes is matched against the exact row it describes. A sentence containing
a figure that is not in that row is discarded.

### What you can do on the site

**Watch it work.** `/terminal` streams what the system is writing as it writes
it. Live events, over SSE. When it is quiet, it looks quiet — nothing is
invented to fill the screen.

**Read every result, including the failures.** `/findings` lists all of them,
filterable by outcome: supported, rejected, inconclusive. Rejections are not
withdrawn for being disappointing.

**Check a question before its answer.** `/hypotheses` shows what each one
declared would prove it wrong — written before the data was seen. Open one and
you get the design, the memories consulted, and every experiment run against
it.

**Audit an experiment.** `/experiments` carries the method, the dataset version
and hash, the sample size, the limitations, all ten critic verdicts, and an
immutable step-by-step trace from observation to result.

**See what it measured.** `/observe` shows the observations and anomalies with
the thresholds each one fired on. `/data` shows the live collection: how many
tokens, how many measurements, and how far it still is from having enough
history to say anything.

**Search its memory.** `/memory` — what it has stored, ranked by similarity,
with the method named. It says `semantic: false` because the embedder is
lexical, and it will keep saying so until that changes.

**Read the science.** `/research` lists the published papers this implements,
with the authors and their affiliations.

**Query it yourself.** `/api/status` reports what is implemented and what is
not, in machine-readable form. `/api/live/stream` is the same event stream the
terminal uses. The full API is public and documented.

**Read the code.** github.com/mluc91070-ux/godgod — 377 tests, nine phase
gates, every commit that produced any of the above.

### Where the method comes from

The architecture is not invented here. It implements published work:

**From Hypotheses to Factors: Constrained LLM Agents in Cryptocurrency
Markets** — Yikuan Huang, Zheqi Fan, Kaiqi Hu, Yifan Ye. arXiv:2604.26747.

An agent proposes falsifiable hypotheses; a deterministic engine decides
whether they hold. Failed hypotheses stay auditable. That is the design GODGOD
runs.

Earlier work from the same group: **Beyond Prompting: An Autonomous Framework
for Systematic Factor Investing via Agentic AI** — Allen Yikuan Huang, Zheqi
Fan. arXiv:2603.14288.

- Yikuan Huang — HKUST · github.com/allenh16
- Zheqi Fan — HKUST, Thrust of FinTech
- Kaiqi Hu — Rutgers Business School
- Yifan Ye — Beijing Normal–Hong Kong Baptist University

Their papers report returns. GODGOD does not trade and reproduces none of those
results. It borrows the method, not the outcome.

### Where it is today

The chain collector is measuring 26 real Solana tokens every fifteen minutes.

The research currently on the site ran on a synthetic dataset, and every row of
it is labelled. Live research starts when a token has enough history for a
detector to have something to say — not before. All six results so far are
inconclusive, and the critic says why: not enough independent history to settle
a question.

That is the honest state, and the site reports it on every page.

**godgod.vercel.app** · **github.com/mluc91070-ux/godgod**

---

## Thread version

**1/**
GODGOD is live.

An autonomous research system studying how meme narratives propagate on Solana.

It measures, notices, asks, tests, criticises itself, and publishes what it
found — including what failed.

Not a trading bot. No keys, no signing, anywhere.

godgod.vercel.app

**2/**
The loop, every 15 minutes:

measure → notice → ask → test → criticise → publish

Real tokens, a public RPC node, a market API. Anything it can't measure stays
empty. A public node can't count holders, so that field is null — never
estimated.

**3/**
It notices with 10 deterministic detectors over trailing windows.

Volume acceleration, liquidity withdrawal, holder concentration, social-onchain
divergence, survival, and 5 more.

No model here. Every anomaly records the detector, its version, and the
thresholds it fired on.

**4/**
Then it asks a question that can be wrong.

Who's in the sample, over what timeframe, against what baseline, what's
expected — and what result would kill it, including the direction.

All of it written before any data is seen.

**5/**
Then arithmetic decides.

Unit is a token-hour. Exposure read on a trailing window, outcome strictly
later. Two-proportion z-test, pooled and per liquidity stratum, re-checked on a
chronological split.

Under 30 per group: inconclusive. That sample settles nothing.

**6/**
Then it attacks its own result.

10 checks: sample size, independence, look-ahead, leakage, survivorship,
selection, confounding, stability, multiple testing, data quality.

All 10 run. All 10 verdicts stored. Nothing is supported without a passing
critic.

**7/**
What you can do on the site:

→ /terminal — watch it work, live over SSE
→ /findings — every result, filterable, failures included
→ /hypotheses — what each question said would prove it wrong, before the test

**8/**
→ /experiments — method, dataset hash, sample size, limitations, all 10 critic
verdicts, and an immutable trace from observation to result
→ /observe — the anomalies with the thresholds they fired on
→ /data — how much real history it has, and how far from enough

**9/**
→ /memory — what it stored, ranked, with the method named. It says
semantic:false because the embedder is lexical
→ /research — the papers this implements
→ /api/status — machine-readable, what's built and what isn't
→ /api/live/stream — the raw event stream

**10/**
The architecture isn't invented here.

"From Hypotheses to Factors: Constrained LLM Agents in Cryptocurrency Markets"
Huang, Fan, Hu, Ye — arXiv:2604.26747

An agent proposes falsifiable hypotheses. A deterministic engine decides. Failed
ones stay auditable.

**11/**
The researchers:

Yikuan Huang — HKUST · github.com/allenh16
Zheqi Fan — HKUST FinTech
Kaiqi Hu — Rutgers
Yifan Ye — BNBU

Earlier work: "Beyond Prompting", arXiv:2603.14288

Their papers report returns. GODGOD doesn't trade and reproduces none of them.

**12/**
Where it is today:

26 real Solana tokens, measured every 15 min.

The research on the site ran on a synthetic dataset — every row labelled. Live
research starts when a token has enough history to say anything.

All 6 results so far: inconclusive.

**13/**
Everything is checkable.

377 tests. 9 phase gates. Every number on the site traces to a row you can
open.

godgod.vercel.app
github.com/mluc91070-ux/godgod
