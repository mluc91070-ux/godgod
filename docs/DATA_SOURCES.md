# Data sources

## What is actually read (PHASE 8)

| Source | Endpoint | Cost | What it gives |
| --- | --- | --- | --- |
| Chain | `SOLANA_RPC_URL` | free (shared) | supply, largest token accounts, signatures |
| Market | `MARKET_API_URL` | free | liquidity, 24h volume, trade counts, token discovery |
| X | `X_BEARER_TOKEN` | paid tier | recent posts |

Neither URL names a vendor anywhere in the code. Swapping data sources is an
environment change.

### What cannot be measured, and is therefore null

- **Holder counts.** A public RPC node does not expose one; it needs an indexer.
  `token_snapshots.holders` stays `NULL` on every live row and the detectors
  that need it return no verdict. Estimating from the largest accounts would be
  inventing a measurement.
- **Holder concentration, on a shared endpoint.** `getTokenLargestAccounts` is
  throttled on the free public RPC — measured, not assumed: `getTokenSupply`
  answers and the largest-accounts call does not, twice in a row. The field
  stays null and the run reports `holder_distribution_rate_limited`, which is a
  different problem from an unconfigured node and is named differently. A
  dedicated RPC url fixes it.

### Why discovery reads the promotion feed

Searching by name on a permissionless chain returns clones of whatever was
typed. A query for "solana" returned pools holding **$1.8bn of liquidity against
$102 of daily volume** — a parked balance, not a market. `CHAIN_MIN_VOLUME_USD`
exists because of that measurement.

The promotion feed is a real sampling frame: tokens someone is actively pushing,
which is the population this system studies. Being promoted is not evidence of
anything, and every experiment records that frame as its population rather than
pretending the sample is neutral.

### Which chains, and what changes when there are two

`MARKET_CHAINS` names them. The promotion feed was never single-chain — it
returns whatever was paid for, on every network the market source indexes — so
"solana" was a filter in the collector rather than a property of the system.

What the second chain changes, and what it must never be allowed to change:

- **`Token.chain` is recorded, never inferred.** It comes from the pair the
  market source returned, not from the shape of the address.
- **A token is an address *and* a chain.** `tokens` is unique on the pair
  (migration `0007`); the same string on two networks is two assets, and one
  row holding both would interleave two series into one.
- **The Solana RPC is not asked about other chains.** Holder concentration is
  read where it can be read; anywhere else it stays null under
  `holder_distribution_chain_unsupported`. That drop is named apart from a
  throttled or unconfigured node because the fix is different — there is no fix,
  it is a limit of what a Solana client can answer.
- **The migration frame reaches one chain.** It is read from a launchpad that
  reports completed bonding curves, and that launchpad covers Solana. A token
  anywhere else enters through the promotion feed or not at all. That is a
  property of the source, and `/api/status` says so rather than leaving an empty
  cohort to be read as "none found".
- **No comparison is held across two chains.** Every stratum in
  `research/dataset.py` is prefixed with the chain, so a "liquidity band" is a
  band within one network. A memecoin off a bonding curve and a token on an
  execution layer built for tokenised equities are not one population, and the
  average of the two answers a question nobody asked.
- **The split between chains is the feed's, not ours.** Discovery keeps the
  promotion feed's own order and does not rebalance towards either network.
  Whatever share of the promotions a chain holds this hour is the share of the
  sample it gets.

### Why some tokens are kept under measurement

A token used to be measured only while the promotion feed still named it. The
result was measured, not guessed: **12,284 readings across 3,732 tokens — a
mean of 3.3 each, against an `OBSERVATION_MIN_SNAPSHOTS` of 6.** Most of the
dataset never qualified to be looked at, because it left the feed first. A
series with holes in it is not a shorter series; it is a different one.

Above `CHAIN_RETAIN_MIN_MARKET_CAP_USD` a token is re-measured every run
regardless of the feed. It reaches the observation threshold in six consecutive
slots — an hour at the current ten-minute cadence — and keeps accumulating
after that.

- The floor is read from the live distribution — market cap p50 $8.4k, p75
  $659k, p90 $8.4m — so a million sits just above the third quartile.
- The cap is **per chain** (`CHAIN_RETAIN_MAX_TOKENS`), never in total. In
  total the larger caps on one network would fill every slot and the other
  would never be retained at all, which is a budget rule deciding which
  population gets studied.
- The cohort is read from the **latest snapshot**, not from
  `Token.market_cap_usd` — that column is a cached value with no timestamp, and
  a selection rule has to be reconstructible from a measurement that says when
  it was taken.
- A retained token **skips the liquidity and volume floors**. Those floors
  decide what is worth entering the dataset; a retained token is already in it,
  and the question about it is what happens next — including the pool draining,
  which is exactly what the floors reject. Dropping it there would be
  survivorship bias built into the collector.
- Every row records `selected_by` (`discovery` / `migration` / `retention`), so
  two selection rules never sit in one column unlabelled. Rows written before
  the distinction existed are NULL, which is "not recorded", not "discovery".

### Reading a bonding curve off a chain

The Solana launchpad publishes an API. The other one does not — the indexers
that cover it want a key — so its contracts are read directly over a public
node. No key, no account, no cost. Read-only by construction: the client has
four methods (`eth_chainId`, `eth_blockNumber`, `eth_getLogs`, `eth_call`) and
not one of them can sign or send.

The fact wanted is whether a curve finished. It arrives in two halves, from two
places, at different times:

- the **launch** is a log entry, and this node refuses a range wider than 2,000
  blocks — about eight minutes of chain. It says so: *"requested logs from 5000
  blocks but only allowed to search 2000 blocks per request"*.
- the **graduation** is contract state that flips hours or days later, readable
  one token at a time.

No window holds both, so the launch is written to `launchpad_launches`, a
cursor in `chain_cursors` records how far the logs have been read, and the
unresolved launches are re-asked on later runs. `graduated` is three-valued:
true, false, and NULL for *nobody managed to ask* — a rate-limited node, a
contract that reverted, a run that hit its call budget. **NULL is never
rendered as "did not migrate."**

Everything here was verified against the chain rather than taken from a page:

- The event signature was matched by hashing it locally and comparing with what
  the chain puts in `topics[0]`. `hashlib.sha3_256` is not Keccak, so
  `app/core/keccak.py` implements the real one; a wrong hash would filter to
  nothing and report a chain where nothing happens.
- **The published factory addresses were wrong.** Three were checked; none
  emitted the launch event. The two that do were found by asking the chain — a
  topic-filtered `eth_getLogs` with no address — and only one of them answers
  the status call. The other reverts, which is why a revert is its own outcome
  and not a "no". The addresses are configuration and default to empty.
- Measured limits, not guesses: 2,000 blocks per log query, HTTP 429 on a burst
  of reads, and timeouts on repeated wide queries. A failed scan leaves the
  cursor where it was — a gap stepped over is indistinguishable from a quiet
  launchpad.

What this frame will *not* be is large. Measured: roughly one launch an hour
from these contracts, and of nine found in ten hours none had graduated, at a
threshold of 4.2 ETH. That is a fact about the launchpad, and an empty cohort
here is reported with the block range that produced it rather than on its own.

## Today

Two fixture sets, both `is_demo=true` on every row, and nothing else connected.
`/api/sources`, `/api/status` and `/data` all say so.

1. **Hand-written demo chain** (`tokens.json`, `social.json`, `research.json`,
   `memories.json`, `content.json`, `events.json`) — the worked example of a
   research cycle from observation to rejected hypothesis.
2. **Synthetic time series** (`timeseries.json`, 6 tokens × 24 hourly
   measurements, 170 posts) — generated by
   `scripts/generate_demo_timeseries.py`, with one pattern planted per token and
   one control token that must produce nothing. It exists so the observation
   pipeline can be tested against known answers. Regenerating it reproduces the
   file byte for byte: the generator uses fixed arithmetic, no randomness.

The pipeline reads the time series through `ObservationSource`
(`app/providers/source.py`), which sits above the raw providers:

```
SolanaProvider + market reads ─┐
                               ├─▶ ObservationSource ─▶ observation pipeline
XProvider search ─────────────┘
```

When the live providers land, a second implementation of that interface replaces
`FixtureObservationSource` and the pipeline is untouched.

Fixture rules:

- Placeholder identifiers only (`DEMO1aaa…`). No real token or wallet address
  appears in fixture data, so no invented statistic can ever be attached to a
  real asset.
- Every fixture file declares `_meta.is_demo` and a note explaining what it is.
- `dataset_hash()` is the SHA-256 of the fixture files in a fixed order. The demo
  experiment stores that hash, so "which data produced this result" has a real
  answer even in demo mode.

## Planned

### Solana (PHASE 8)

Configured through `SOLANA_RPC_URL` / `SOLANA_WS_URL`. The provider interface is
vendor-neutral by design — no RPC vendor name appears in the code, so switching
providers is a configuration change.

Read-only methods: `get_account`, `get_transaction`, `get_token_accounts`,
`get_signatures`, `subscribe_logs`, `subscribe_account`, `subscribe_program`.

Fields normalized when available: token address, name, symbol, decimals, market
cap, liquidity, volume, holders, holder concentration, transactions, buys, sells,
age, liquidity change, holder change, launch time, bonding-curve state,
migration, DEX. **A field the provider does not return stays null.**

### X (PHASE 7)

Configured through `X_BEARER_TOKEN`. Methods: `search_recent_posts`, `get_user`,
`get_user_posts`, `get_mentions`, `create_post` (gated — see `X_PUBLISHING.md`).

Search terms are configuration, not code: memecoin, meme coin, Solana, AI agent,
AI memecoin, Pump.fun, Raydium, GOAT, Fartcoin, ACT, Zerebro, autonomous agent,
AI economy, meme narrative. They are collected as observations, never as
instructions.

## Provenance

`research_sources` records every source with kind (`RPC`, `API`, `DATASET`,
`FIXTURE`, `MANUAL`), name, URL, description, reliability and last use. Every
observation carries the `source` it came from. A claim whose source cannot be
named does not get published.

## Rate limits and cost

Provider calls are batched and cached; see `COST_CONTROL.md`. Free tiers first,
pay-as-you-go second, scale only when a measurement says it is necessary.
