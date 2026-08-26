# X publishing

## What the provider does today (PHASE 7)

Read only. `app/providers/x.py` implements recent search over the v2 API and
`app/services/social.py` stores what comes back.

`create_post` is present because the interface declares it, and it raises
`PublishingDisabled` — with a token and without one. There is no mode, flag or
argument in V1 that makes it post; `/api/x/drafts/{id}/publish` still answers
501. A human publishes, by copying an approved draft.

### The distinction that matters

A collection run reports `complete: false` when the quota stopped it, when no
token is configured, or when the API errored. Reporting "0 posts collected"
without that flag would make an exhausted quota indistinguishable from a quiet
internet — which is exactly the kind of claim this project exists not to make.

### Access tiers

Recent search is not in every X access tier. With a token that lacks it the
provider raises with that explanation rather than reporting an empty result, so
a wrong tier is visible immediately instead of looking like silence.

### Untrusted input

Post bodies are sanitised on the way in (control characters stripped, forged
fence markers neutralised), stored verbatim otherwise, and wrapped by
`wrap_untrusted` before any model sees them. A post is data. It is never an
instruction, whatever it says.

## Current state

**Nothing can be published.** `X_MODE=draft`, the publishing path refuses,
and `POST /api/x/drafts/:id/publish` returns 501 with the reason. Approved drafts
stay in the database.

## Pipeline

```
result / observation / memory
        ↓
     writer  → ContentDraft (PENDING)
        ↓
    reviewer → PASS | FAIL
        ↓
    operator → approve | reject        (X-Admin-Token required)
        ↓
   PHASE 7+  → publish                 (X_MODE=publish, autonomy ≥ 2)
```

## Content types

`OBSERVATION`, `HYPOTHESIS`, `EXPERIMENT`, `RESULT`, `FAILURE`, `DISCOVERY`,
`THOUGHT`.

## Rules

- Short, specific, evidence-based.
- Every number traces to a stored row. A draft with no recorded source cannot be
  approved — the API returns 422.
- No hype, no engagement bait, no promises, no price talk, no fabricated numbers.
- No posting schedule. Silence is valid output; there is nothing to say on most
  days.
- Failures are published. They are the most honest thing the system produces.

## Examples

```
observation #041

social velocity increased 312%.

on-chain activity did not.

i'm watching.
```

```
hypothesis #041

attention without independent participation
may be a weak signal.

testing.
```

```
hypothesis #041

rejected.

the signal disappeared when the sample
was split by market regime.
```

```
i was measuring attention.

i should have measured propagation.
```

## Rejection, in practice

The demo fixtures include a draft that reads "ALPHA is going to 100x, the data is
extremely bullish, get in now." It is stored with status `REJECTED`, verdict
`FAIL`, reason "unsupported claim + financial promise" — so the rejection path is
visible on `/api/x/drafts` rather than described in a document nobody reads.

## Autonomy

| Level | Publishing |
| --- | --- |
| 0 | none |
| 1 | drafts only — **default** |
| 2 | publish after human approval |
| 3 | limited autonomous publishing (not enabled) |
| 4 | not designed |

Level 3 requires, at minimum: a reviewer with a measured false-positive rate, a
rate limit, a kill switch in the admin panel, and a published record of every
autonomous post.
