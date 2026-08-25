# Data sources

## Today (PHASE 1)

One source: `data/fixtures/*.json`, loaded into the database with `is_demo=true`
on every row. Nothing else is connected. `/api/sources` and `/data` show this.

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
