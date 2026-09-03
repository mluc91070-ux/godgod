"""Runtime configuration for GODGOD.

Everything is environment driven. No secret and no model name is ever
hard-coded anywhere else in the codebase.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

AutonomyLevel = Literal[0, 1, 2, 3, 4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- identity -----------------------------------------------------
    app_name: str = "GODGOD"
    app_version: str = "0.1.0"
    environment: Literal["local", "staging", "production"] = "local"

    # --- modes --------------------------------------------------------
    demo_mode: bool = True
    """When true the API only serves clearly marked fixture data."""

    autonomy_level: int = 1
    """0 read-only, 1 research+draft (default), 2 approval+publish, 3 limited auto, 4 future."""

    x_mode: Literal["draft", "approval", "publish"] = "draft"
    """V1 never publishes automatically."""

    external_content_is_untrusted: bool = True
    """External social/on-chain text is DATA, never an instruction."""

    # --- database -----------------------------------------------------
    database_url: str = "sqlite+pysqlite:///./godgod.db"
    database_echo: bool = False

    # --- data ---------------------------------------------------------
    fixtures_dir: str | None = None
    """Defaults to <repo>/data/fixtures when unset."""

    # --- providers (unset in demo mode) -------------------------------
    solana_rpc_url: str | None = None
    solana_ws_url: str | None = None
    x_bearer_token: str | None = None
    anthropic_api_key: str | None = None
    anthropic_workspace_id: str | None = None
    """Required by keys that are linked to an identity rather than a workspace.

    Such a key authenticates the person, not the place the request acts in, and
    the API refuses it with HTTP 400 until the workspace is named. It is an
    identifier, not a credential — it grants nothing on its own."""

    # --- model routing (never hard-code model names elsewhere) --------
    model_fast: str | None = None
    model_reasoning: str | None = None
    model_writer: str | None = None
    model_critic: str | None = None

    # --- memory (PHASE 2) ---------------------------------------------
    embedding_provider: Literal["local", "none"] = "local"
    """"local" is a deterministic hashing embedder that needs no API key.
    A learned model becomes available when the provider work lands."""

    embedding_model: str = "local-hashing-v1"
    """Recorded on every stored vector. A vector whose model is unknown is
    a vector nobody can reproduce."""

    embedding_dim: int = 1536
    memory_scan_limit: int = 5000
    """Rows loaded by the Python cosine fallback used when the database is
    not PostgreSQL. PostgreSQL ranks with pgvector instead."""

    memory_similarity_threshold: float = 0.12
    """Minimum cosine for a hit to be returned.

    Measured on the demo corpus with the local hashing embedder: unrelated
    queries top out around 0.06 (hash collisions), while the weakest genuine
    match scores about 0.15. 0.12 sits between the two. Re-measure this when
    the embedder changes — it is a property of the embedder, not a taste.
    """

    # --- observation pipeline (PHASE 3) -------------------------------
    observation_window_hours: int = 6
    """Trailing window each detector compares its latest measurement against."""

    observation_min_snapshots: int = 6
    observation_min_liquidity_usd: float = 5_000.0
    observation_min_holders: int = 50
    """Deterministic floors. A subject below them is dropped before any
    scoring — this is the cheap gate that keeps model cost bounded."""

    observation_novelty_floor: float = 0.55
    """A candidate with no anomaly is only recorded if it is this novel."""

    observation_memory_importance_floor: float = 0.5
    """Below this, an observation is stored but not written to memory."""

    observation_cooldown_minutes: int = 180
    """Same subject + same anomaly type inside this window is a duplicate."""

    # --- live stream (PHASE 9) ----------------------------------------
    stream_poll_seconds: float = 1.0
    """How often the SSE endpoint looks for rows newer than the cursor.

    Polling, not a message bus: the writers are the pipeline and the research
    cycle, both of which commit to the same database the reader is watching.
    A queue would be a second source of truth for no gain at this scale.
    """

    stream_replay_events: int = 60
    """Events sent on connect so a new tab is not staring at an empty log."""

    stream_heartbeat_seconds: float = 15.0
    """Comment frame keeping proxies from closing an idle connection."""

    stream_max_seconds: float = 900.0
    """Hard lifetime for one connection. The client reconnects with its cursor;
    a forgotten tab does not poll the database forever."""

    # --- chain and market (PHASE 8) ------------------------------------
    solana_timeout_seconds: float = 20.0

    solana_retry_seconds: float = 1.5
    """Backoff before one retry of a rate-limited call. Zero disables it.

    Measured against the shared public endpoint: `getTokenSupply` answers,
    `getTokenLargestAccounts` throttles. One retry is worth trying; more would
    be pretending a shared endpoint is a dedicated one.
    """

    market_api_url: str | None = None
    """Where liquidity, volume and trade counts are read from.

    A URL rather than a vendor name, for the same reason SOLANA_RPC_URL is:
    swapping data sources must be an environment change, not a code change.
    """

    market_timeout_seconds: float = 20.0

    market_chains: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["solana", "robinhood"]
    )
    """Which chains the market source is read for.

    The promotion feed is not single-chain — it returns whatever was paid for,
    on every chain the source indexes — so the chain was never a property of
    the code, only an unexamined filter in it. Naming the chains here makes the
    population a configuration decision that is written down, and `Token.chain`
    records which one every row came from.

    Adding a chain changes the population every past experiment drew from, so
    the chain is carried into the stratum: comparisons are held within one
    chain, never pooled across two. See `research/dataset.py`.

    A chain identifier is not a vendor: it names the network, the way "solana"
    already did. What the identifiers must match is whatever the configured
    MARKET_API_URL calls them.
    """

    chain_watch_queries: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["solana"]
    )
    """Search terms the collector uses to find tokens worth measuring."""

    chain_max_tokens: int = 40
    """Tokens tracked per collection run. The deterministic floors drop most of
    them before anything is stored; this caps the work before that."""

    chain_min_liquidity_usd: float = 50_000.0
    """A token below this is not worth a row. Distinct from the pipeline's own
    floor, which decides what is worth *observing* once it is stored.

    Raised from $10,000 against the measured population: of 1,400 tokens held,
    646 cleared ten thousand and 406 clear fifty. The old floor admitted the
    median token at $5,885 of depth, which is a pool three trades wide — most
    of what it let in was never going to be a subject, only a row.
    """

    chain_min_volume_usd: float = 100_000.0
    """Liquidity alone says nothing.

    Measured on the live feed: pools holding over a billion dollars of wrapped
    SOL reported about a hundred dollars of daily volume. That is a parked
    balance, not a market, and tracking it would fill the dataset with tokens
    nothing ever happens to.

    Raised from $25,000 because at that level it was not a filter: 1,348 of
    1,400 tokens cleared it. The median is $135,513, so a hundred thousand is
    the point where the floor starts doing the job it was written for.
    """

    scheduler_enabled: bool = False
    """Let the application keep its own time instead of an external cron.

    Off by default so tests, local runs and one-off scripts never start a
    background loop. On in production, where the instance is always-on.

    It exists because GitHub Actions' scheduler is best-effort and was measured
    on this repository delivering eight runs in eleven hours against a
    fifteen-minute cron — gaps of 208, 162 and 124 minutes. A skipped run is
    not a late run: a detector needs several measurements of the *same* token,
    so history that is never collected is never recoverable.

    The GitHub workflow stays as a backstop. The two cannot collide — the
    collector stores one measurement per token per slot.
    """

    scheduler_interval_seconds: int = 600
    """How often the collector runs. The measurement slot follows it.

    Ten minutes rather than fifteen: six readings an hour instead of four, so a
    token clears `OBSERVATION_MIN_SNAPSHOTS` in an hour rather than ninety
    minutes, and a six-hour window holds thirty-six points instead of
    twenty-four.

    The cost is on the shape of `volume_usd`, which is an hourly rolling
    figure: two consecutive readings now overlap by 83% instead of 75%. That is
    still far from the 96% that made the 24h window useless, and the trade is
    worth stating rather than hiding — the sampling got denser, the measurement
    did not change.
    """

    @property
    def snapshot_slot_minutes(self) -> int:
        """The grid measurements are keyed to, derived from the interval.

        Derived rather than configured because the two must not drift apart. A
        loop running faster than the slot spends requests landing in a slot
        already measured; a loop running slower leaves the grid half empty and
        the gaps look like a market that went quiet.

        Snapped to a divisor of sixty so slots tile the hour. Without that, a
        seven-minute interval would put every hour's boundary in a different
        place and no two days would be comparable.
        """
        minutes = max(1, self.scheduler_interval_seconds // 60)
        divisors = (1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60)
        return max(value for value in divisors if value <= min(minutes, 60))

    evm_rpc_url: str | None = None
    """A read-only JSON-RPC endpoint for the EVM chain being measured.

    A url rather than a vendor name, for the third time and the same reason.
    The chain it points at is a deployment decision; nothing in the code names
    one.

    What it buys is the only fact a market API cannot supply about a token on
    that chain: whether its bonding curve finished. That lives in a launchpad
    contract, and a contract is readable by anyone with a node — no key, no
    account, no cost.
    """

    evm_chain: str = "robinhood"
    """Which `Token.chain` the EVM reads describe.

    Named rather than derived from the node's chain id, because the id is a
    number and `Token.chain` is the market source's own label for the same
    network. Tying the two together by hand is the only place they can be
    reconciled, and getting it wrong would file one chain's migrations under
    another's — which is why `EVM_CHAIN_ID`, when set, is checked against the
    node before a single log is read.
    """

    evm_chain_id: int | None = None
    """The chain id the node must report. Unset means unchecked.

    Set it and a node pointed at the wrong network refuses loudly instead of
    quietly writing another chain's tokens into this one's rows.
    """

    evm_timeout_seconds: float = 20.0

    evm_retries: int = 1
    """Retries after a rate-limited call. Measured on the public endpoint: a
    burst of reads returns HTTP 429, and one backoff clears it. More would be
    pretending a shared endpoint is a dedicated one."""

    evm_retry_seconds: float = 3.0

    evm_launchpad_factories: Annotated[list[str], NoDecode] = Field(
        default_factory=list
    )
    """Contract addresses whose launch events are read. Empty means none.

    Empty by default and never guessed. Three addresses published as "the"
    factory for this launchpad were checked against the chain and none of them
    emitted the event: two had not emitted anything for hours, and the third
    emitted a different set of topics entirely. The addresses that do emit it
    were found by asking the chain — a topic-filtered `eth_getLogs` with no
    address at all — which is the only method here that cannot be out of date.

    More than one is expected: a launchpad redeploys its factory, and the old
    one keeps its history.
    """

    evm_launchpad_event: str = (
        "TokenLaunched(address,address,address,address,address,"
        "uint256,uint256,uint256,uint256,uint256)"
    )
    """The launch event, written out rather than hashed into a constant.

    `topics[0]` is the keccak of this string, and a 32-byte constant pasted
    into the source is a thing nobody can check. The first indexed parameter is
    the token.
    """

    evm_launchpad_status_call: str = "graduationStatus(address)"
    """The view function asked whether a curve finished.

    It returns `(uint256 pairedPrincipal, uint256 threshold, bool graduated)`,
    and only the third word is read as the claim. A contract that reverts on
    this call has not said "no" — it has said nothing, and it is recorded that
    way.
    """

    evm_log_chunk_blocks: int = 2_000
    """Blocks per `eth_getLogs` request.

    Measured, not chosen: the node answers a wider range with "requested logs
    from 5000 blocks but only allowed to search 2000 blocks per request". A
    range wider than this is split into chunks rather than truncated, because
    silently reading the last two thousand blocks of a ten-thousand block
    request would report a launchpad where nothing happens.
    """

    evm_scan_max_blocks_per_run: int = 6_000
    """Furthest the launch scan advances its cursor in one run.

    Three requests at the chunk size. At roughly four blocks a second, six
    thousand blocks is about twenty-five minutes of chain — comfortably more
    than the collection interval, so the cursor gains on the head instead of
    falling behind, and a restart after an outage catches up over several runs
    rather than asking for a range the node will refuse.
    """

    evm_scan_start_blocks_back: int = 20_000
    """Where the cursor starts on a database that has never scanned.

    Deliberately short. The alternative is starting at the launchpad's first
    block, which is hundreds of requests before the first useful answer; this
    starts near the head and the history fills in going forward. What the
    system has not scanned it does not claim, and the cursor is stored, so the
    gap is visible rather than implied.
    """

    evm_launchpad_max_calls: int = 25
    """Ceiling on status calls per run, across new and re-checked launches.

    The endpoint is shared and rate-limited — measured: a burst returns 429 —
    and a curve finishes hours or days after the launch that started it, so
    every launch has to be re-asked more than once. This is the cost control:
    everything past the ceiling is left for the next run and counted, never
    read as unmigrated.
    """

    evm_recheck_hours: int = 6
    """How long an unresolved launch keeps being re-asked.

    A token whose curve has not finished this long after launching is left
    alone rather than marked as failed: `graduated` stays NULL, which is "not
    known to have finished". Measured on this chain, roughly one launch an hour
    and none of nine graduated within ten hours, so a window this size is where
    the calls are worth spending — not a claim about when curves finish.
    """

    launchpad_api_url: str | None = None
    """Where completed bonding curves are read from.

    A URL rather than a vendor name, same rule as SOLANA_RPC_URL and
    MARKET_API_URL. Unset means migrations are unavailable and every token
    keeps `bonding_curve_state` NULL — never "unmigrated" by default.
    """

    launchpad_timeout_seconds: float = 20.0

    launchpad_migrations: bool = True
    """Add recently migrated tokens to each collection run.

    A second sampling frame, and deliberately a different one: the promotion
    feed is tokens somebody paid to show, this is tokens that filled a curve.
    Every token records which frame found it, because a result that holds in
    one and not the other is a result about the frame, not about the market.
    """

    launchpad_max_tokens: int = 25
    """Migrations added per run, on top of the promotion feed. Capped because
    the market API is then asked to measure each of them."""

    launchpad_min_liquidity_usd: float = 1_000.0
    """A far lower floor than the promotion feed's, and deliberately so.

    The $10k floor exists to reject a parked balance: a deep pool nobody
    trades. A token that migrated twenty minutes ago cannot be a parked
    balance, and applying the same floor to it rejects the opposite thing.
    Measured on a live run: of 25 fresh migrations, the $10k floor dropped 21
    — including one 18 minutes old doing $343k of volume on a $6k pool, which
    is precisely the event this system exists to study.

    This floor only rejects a pool with nothing left in it.
    """

    launchpad_min_volume_usd: float = 25_000.0
    """Same question as the promotion feed's floor — is anything happening —
    and the same answer, so the same number. On a token under an hour old the
    24h figure is simply everything that has traded since it launched."""

    attention_api_url: str | None = None
    """Where a search-ranking feed is read from.

    This is what replaced the social collector. A ranking is a position, not a
    mood: a token is in the list at a rank at a time, which is a series anyone
    can count. No key, no account, and no model anywhere near it.
    """

    attention_timeout_seconds: float = 20.0

    attention_max_resolutions: int = 6
    """Coin-to-address lookups per run.

    A ranking entry is useless until it is tied to a contract address, and that
    is a second request per coin. The mapping does not change, so it is looked
    up once and read back from the rows afterwards; this caps how many *new*
    names a single run will resolve. The keyless tier is rate-limited, and a
    run that spent its budget says so rather than reporting a short list.
    """

    watchlist_notes_path: str = "data/watchlist/robinhood-runners.json"
    """Where the operator's notes about watched tokens are read from.

    A path rather than a fixture: these are not `is_demo` rows and nothing
    generates them. Absent is a valid state and the loader says so rather than
    failing — a deployment with no notes simply has none.
    """

    theses_path: str = "data/theses/chain-structure.json"
    """Where the posed theses live.

    A thesis is an argument written before the data exists to settle it, and it
    is kept apart from hypotheses for the same reason the watchlist is kept
    apart from the sampling frames: it was written by a person, and nothing in
    it was produced by an experiment. What the site shows beside each link of a
    thesis is derived from the database, never from this file — the file may
    claim a mechanism, it may not claim the mechanism was measured.

    Absent is a valid state. A deployment with no theses has none, and the
    endpoint says so rather than failing.
    """

    chain_watchlist: Annotated[list[str], NoDecode] = Field(default_factory=list)
    """Tokens named by hand, as `chain:address`, measured every run.

    This is a third sampling frame and by far the most biased one: the other
    two are populations — whatever the feed promoted, whatever curve filled —
    and this one is a list somebody wrote after seeing which tokens did well.
    Every entry is a survivor by construction.

    That is fine for watching and useless for inference, so the two uses are
    separated rather than blurred: the rows are measured, stored and shown like
    any other, and `research/dataset.py` drops them under a named reason. A
    "top runners" list in a comparison is survivorship bias with extra steps.

    Addresses are recorded exactly as given and never trusted as metadata: the
    symbol and name still come from the market source, and nothing a list says
    about a token is stored as a fact about it.
    """

    chain_retain_min_market_cap_usd: float = 1_000_000.0
    """Above this market cap a token is measured every run, whether or not the
    promotion feed still names it.

    The problem this solves is measured, not imagined: at the time of writing
    the collector held 12,284 measurements across 3,732 tokens — a mean of 3.3
    each, against an `OBSERVATION_MIN_SNAPSHOTS` of 6. Most tokens rotate out
    of the promotion feed before any detector is allowed to speak about them,
    and a series with holes in it is not a shorter series, it is a different
    one. A retained token reaches the threshold in six consecutive quarter
    hours and keeps accumulating after that.

    The floor is set from the live distribution: market cap p50 $8.4k, p75
    $659k, p90 $8.4m. A million sits just above the third quartile — 283 of
    1,200 tokens qualified — which is the point where "big" stops being a
    rounding error on a fresh pool.
    """

    chain_retain_max_tokens: int = 40
    """Retained tokens per chain, not in total.

    Forty rather than twenty: the cohort is the part of the dataset that can
    actually be researched — a retained token is measured every run and reaches
    the observation threshold — so it is the number to spend on. Forty per
    chain against a floor of a million is roughly the top decile of each
    population.

    In total, the largest caps on the older chain would fill every slot and the
    newer one would never be retained at all — a budget rule quietly deciding
    which network gets studied. Per chain, each population keeps its own top,
    which is also the only form comparable with everything else here: every
    comparison in this system is held within one chain.
    """

    equity_quote_marker: str = "• Robinhood Token"
    """How the chain names its tokenised-equity wrappers.

    A meme quoted against a tokenised equity is a different instrument from a
    meme quoted against the gas token: its chart is not separable from the
    equity's without the pair data, and the depth on one side is a constraint
    on the other. Whether that changes how the token behaves is a question, and
    a question needs the two groups told apart before it can be asked.

    The chain tells them apart itself. Every equity wrapper the market source
    reports carries this marker in the quote token's *name* — "NVIDIA •
    Robinhood Token", "Eli Lilly • Robinhood Token" — so the classification is
    read off the source rather than guessed from a symbol, which is the one
    field an attacker controls freely.

    It is configuration because it is a property of the source, not of this
    system. If the chain renames its wrappers, the classifier must go quiet and
    record `unknown`, not keep matching a string that stopped meaning anything.
    """

    gas_quote_symbols: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["SOL", "WSOL", "ETH", "WETH"]
    )
    """Quote symbols that are the chain's own unit of account, wrapped or not.

    The baseline arm of the pairing question. Everything that is neither this
    nor an equity wrapper is `other` — a stablecoin quote, a meme-against-meme
    pool — and stays out of both arms rather than being forced into one.
    """

    equity_quote_query: str = "Robinhood Token"
    """What the collector searches to find the tokenised-equity cohort.

    The frame this opens is the only one on this chain that is not a leftover
    of how Solana is sampled: the promotion feed answers with whoever paid, and
    a filled bonding curve answers with whoever bought. This answers with a
    structural fact about the pool — what it is quoted in — which is exactly
    the population the pairing hypothesis needs and the one neither other frame
    reliably reaches.
    """

    equity_quote_max_tokens: int = 30
    """Tokens taken from the equity-quote frame per run.

    Its own budget rather than a share of the promotion feed's: the two frames
    compete for slots, and on measurement the promotion feed on the older chain
    fills them all. A cohort that is the subject of a hypothesis cannot be
    sampled out of existence by an unrelated feed being busy.
    """

    equity_quote_min_liquidity_usd: float = 5_000.0
    """A lower floor than the promotion frame's, for the same reason the
    launchpad frame has one: this cohort is selected by a structural property
    and not by size, so applying a fifty-thousand-dollar floor to it would keep
    only the four tokens already known and leave the comparison with one arm.

    Five thousand is still a pool, not a dust pair — measured on the live
    cohort, it admits the long tail of equity-quoted memes while dropping the
    pairs holding a few hundred dollars.
    """

    chain_discover: bool = True
    """Read the promotion feed instead of searching by name.

    Name search on a permissionless chain returns clones of whatever was typed.
    The promotion feed is a real sampling frame — of tokens someone is pushing,
    which is exactly the population this system studies, and which every
    experiment records as its population rather than pretending it is neutral.
    """

    # --- X (PHASE 7) ---------------------------------------------------
    x_timeout_seconds: float = 30.0

    x_api_key: str | None = None
    x_api_secret: str | None = None
    x_access_token: str | None = None
    x_access_token_secret: str | None = None
    """Posting needs user context; the bearer token can only read.

    A deployment can hold a valid X_BEARER_TOKEN, on a paid tier, and still be
    unable to publish a single post. These four are what writing requires.
    """

    @property
    def x_can_publish(self) -> bool:
        """Is publishing switched on *and* possible.

        Two conditions, and both are load-bearing. `X_MODE=publish` is the
        decision; the four OAuth values are the capability. A deployment with
        the switch on and no credentials cannot post a single time, so any
        label derived from the mode alone would announce a capability that
        does not exist.
        """
        return self.x_mode == "publish" and all(
            (
                self.x_api_key,
                self.x_api_secret,
                self.x_access_token,
                self.x_access_token_secret,
            )
        )

    @property
    def x_stage(self) -> str:
        """What to call the X integration on a page: `live` or `beta`.

        `live` is only ever returned when a post could actually go out. Every
        other state — no credentials, the switch off, or both — is `beta`,
        which describes the integration without claiming anything about what
        it has done.
        """
        return "live" if self.x_can_publish else "beta"

    x_min_minutes_between_posts: int = 45
    """Floor between two published posts.

    A research system that posts whenever it finishes a cycle is a bot, and it
    exhausts a 500-post month in under a week."""

    x_search_terms: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["solana meme coin", "pump.fun"]
    )
    """Comma-separated search queries the collector runs.

    Deliberately narrow: the recent-search quota is the binding constraint on
    every paid tier, so a broad query buys noise with the budget that a specific
    one spends on signal.
    """

    x_max_posts_per_run: int = 100
    """Ceiling per collection run. The quota is monthly; a runaway loop that
    spends it in an afternoon leaves the system blind for four weeks."""

    x_min_likes: int = 0
    x_exclude_reposts: bool = True
    """A repost is amplification, not an independent observation. Counting them
    as separate posts is how a single account looks like a movement."""

    # --- model calls --------------------------------------------------
    model_timeout_seconds: float = 60.0

    model_price_input_usd_per_mtok: float | None = None
    model_price_output_usd_per_mtok: float | None = None
    """Per-million-token prices for the configured models.

    Unset means unpriced, and an unpriced call records `estimated_cost_usd=None`
    rather than 0.0 — a fabricated zero would defeat the budget it is meant to
    protect. The budget guard refuses to spend what it cannot measure, so these
    must be set alongside the MODEL_* roles before any agent runs.
    """

    # --- cost control -------------------------------------------------
    llm_daily_budget_usd: float = 3.0
    memory_retrieval_limit: int = 20

    # --- api ----------------------------------------------------------
    api_prefix: str = "/api"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    """Comma-separated in the environment.

    NoDecode is load-bearing: without it pydantic-settings JSON-decodes a list
    field before any validator runs, and `CORS_ORIGINS=https://site.example`
    crashes the process at startup instead of being read as one origin.
    """
    admin_token: str | None = None

    @field_validator("autonomy_level")
    @classmethod
    def _check_autonomy(cls, v: int) -> int:
        if v not in (0, 1, 2, 3, 4):
            raise ValueError("autonomy_level must be between 0 and 4")
        return v

    @field_validator(
        "cors_origins",
        "x_search_terms",
        "chain_watch_queries",
        "market_chains",
        "chain_watchlist",
        "gas_quote_symbols",
        "evm_launchpad_factories",
        mode="before",
    )
    @classmethod
    def _split_list(cls, v: object) -> object:
        """Comma-separated in the environment; a list everywhere else."""
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgresql")

    @property
    def wallet_execution_enabled(self) -> bool:
        """V1 has no wallet execution path at all. Kept explicit for auditability."""
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
