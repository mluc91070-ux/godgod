"""The observation pipeline.

    source ─▶ normalize ─▶ deterministic filter ─▶ detectors ─▶ scoring ─▶ store

No model is called anywhere in this file, and `llm_reviewed` stays False on
every observation it writes. That is the cost architecture from the spec: the
cheap deterministic layer decides what is even worth looking at.

Anchoring: the window ends at `as_of`, which defaults to the newest
measurement the source has rather than the wall clock. A frozen dataset stays
observable, and a backfill can walk the series hour by hour exactly the way a
live loop would.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.enums import AnomalyType, EventType, ObservationKind
from app.models import (
    AgentRun,
    Anomaly,
    Observation,
    SocialAccount,
    SocialPost,
    SystemEvent,
    Token,
    TokenSnapshot,
    WalletCluster,
)
from app.models.base import as_utc, utcnow
from app.providers.source import ObservationSource, TokenRef, get_observation_source
from app.services.memory import store_memory
from app.services.observation.detectors import (
    ONCHAIN_DETECTORS,
    AnomalyCandidate,
    DetectorParams,
    narrative_acceleration,
    new_wallet_cluster,
    social_onchain_divergence,
    social_velocity,
)
from app.services.observation.scoring import confidence_score, importance_score, novelty_score
from app.services.observation.windows import (
    TokenWindow,
    build_social_window,
    build_token_window,
)

PIPELINE_RUN_NAME = "observation-pipeline"
"""Not "observer": the agent is the model layer, this is the cheap stage."""

STANDING_ANOMALIES = frozenset(
    {
        str(AnomalyType.TOKEN_SURVIVAL_ANOMALY),
        str(AnomalyType.NEW_WALLET_CLUSTER),
    }
)
"""Conditions that persist, rather than events that happen."""


@dataclass
class RunReport:
    as_of: datetime | None = None
    subjects_examined: int = 0
    dropped: Counter[str] = field(default_factory=Counter)
    observations_created: int = 0
    anomalies_created: int = 0
    memories_written: int = 0
    events_emitted: int = 0
    duration_ms: int = 0
    snapshots_ingested: int = 0
    posts_ingested: int = 0

    def as_dict(self) -> dict:
        return {
            "as_of": self.as_of.isoformat() if self.as_of else None,
            "subjects_examined": self.subjects_examined,
            "dropped": dict(self.dropped),
            "observations_created": self.observations_created,
            "anomalies_created": self.anomalies_created,
            "memories_written": self.memories_written,
            "events_emitted": self.events_emitted,
            "snapshots_ingested": self.snapshots_ingested,
            "posts_ingested": self.posts_ingested,
            "duration_ms": self.duration_ms,
            "llm_calls": 0,
        }


async def _next_seq(session: AsyncSession, model: type) -> int:
    current = await session.scalar(select(func.max(model.seq)))
    return int(current or 0) + 1


class ObservationPipeline:
    def __init__(
        self,
        source: ObservationSource | None = None,
        settings: Settings | None = None,
        params: DetectorParams | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._explicit_source = source
        # Resolved per run rather than here: the live source reads from the
        # session, and a pipeline built once must not be pinned to fixtures.
        self.source = source or get_observation_source(settings=self.settings)
        self.params = params or DetectorParams()

    def _resolve_source(self, session: AsyncSession) -> ObservationSource:
        if self._explicit_source is not None:
            return self._explicit_source
        self.source = get_observation_source(session=session, settings=self.settings)
        return self.source

    # -- ingestion ---------------------------------------------------------

    async def _upsert_token(self, session: AsyncSession, ref: TokenRef) -> Token:
        """Fill what is missing. Never rewrite what the collector recorded.

        This once assigned every field on every run, including `source`. That
        was harmless while fixtures were the only writer of tokens, and became
        a silent data loss the moment this pipeline started running live every
        quarter hour: it read the collector's own tokens back through
        `DatabaseObservationSource` and stamped `source = "database-live"` over
        the sampling frame that said whether the token came from the promotion
        feed or from a completed bonding curve. Measured on production: 144 of
        144 tokens had lost their frame, so every experiment that stratifies on
        it had nothing to stratify on.

        `TokenRef` carries no frame, so there is nothing here to write it back
        with. The rule is therefore the same one the collector follows — the
        frame is written once, by whoever created the row.
        """
        token = await session.scalar(select(Token).where(Token.address == ref.address))
        if token is None:
            token = Token(
                address=ref.address,
                is_demo=self.source.is_demo,
                # Only a creator names the frame. For a fixture replay that is
                # the fixture; for a live run the collector got here first and
                # this branch is never taken.
                source=self.source.name,
            )
            session.add(token)
        # Fill-if-empty: a later run may learn a symbol the first one lacked,
        # but must not replace a recorded value with a null or a newer guess.
        for attribute in ("symbol", "name", "decimals", "launch_time", "launchpad"):
            learned = getattr(ref, attribute, None)
            if learned is not None and getattr(token, attribute, None) is None:
                setattr(token, attribute, learned)
        await session.flush()
        return token

    async def _store_snapshots(
        self, session: AsyncSession, token: Token, snapshots: list[dict]
    ) -> int:
        existing = {
            as_utc(value)
            for value in (
                await session.scalars(
                    select(TokenSnapshot.observed_at).where(TokenSnapshot.token_id == token.id)
                )
            ).all()
        }
        written = 0
        for snapshot in snapshots:
            if as_utc(snapshot["observed_at"]) in existing:
                continue
            existing.add(as_utc(snapshot["observed_at"]))
            session.add(
                TokenSnapshot(
                    token_id=token.id,
                    observed_at=snapshot["observed_at"],
                    market_cap_usd=snapshot.get("market_cap_usd"),
                    liquidity_usd=snapshot.get("liquidity_usd"),
                    volume_usd=snapshot.get("volume_usd"),
                    holders=snapshot.get("holders"),
                    holder_concentration_top10=snapshot.get("holder_concentration_top10"),
                    transactions=snapshot.get("transactions"),
                    buys=snapshot.get("buys"),
                    sells=snapshot.get("sells"),
                    age_seconds=snapshot.get("age_seconds"),
                    source=self.source.name,
                    is_demo=self.source.is_demo,
                )
            )
            written += 1

        latest = snapshots[-1] if snapshots else None
        if latest:
            token.market_cap_usd = latest.get("market_cap_usd")
            token.liquidity_usd = latest.get("liquidity_usd")
            token.volume_24h_usd = latest.get("volume_usd")
            token.holders = latest.get("holders")
            token.holder_concentration_top10 = latest.get("holder_concentration_top10")
            token.last_seen_at = latest["observed_at"]
            token.first_seen_at = token.first_seen_at or snapshots[0]["observed_at"]
        await session.flush()
        return written

    async def _store_posts(self, session: AsyncSession, posts: list[dict]) -> int:
        if not posts:
            return 0
        known = set(
            (
                await session.scalars(
                    select(SocialPost.external_id).where(
                        SocialPost.external_id.in_([post["external_id"] for post in posts])
                    )
                )
            ).all()
        )
        accounts: dict[str, str] = {}
        written = 0
        for post in posts:
            if post["external_id"] in known:
                continue
            handle_id = post.get("account_external_id")
            account_id = None
            if handle_id:
                if handle_id not in accounts:
                    account = await session.scalar(
                        select(SocialAccount).where(SocialAccount.external_id == handle_id)
                    )
                    if account is None:
                        account = SocialAccount(
                            external_id=handle_id, is_demo=self.source.is_demo
                        )
                        session.add(account)
                        await session.flush()
                    accounts[handle_id] = account.id
                account_id = accounts[handle_id]

            session.add(
                SocialPost(
                    external_id=post["external_id"],
                    account_id=account_id,
                    posted_at=post.get("posted_at"),
                    text=post["text"],
                    lang=post.get("lang"),
                    likes=post.get("likes"),
                    reposts=post.get("reposts"),
                    replies=post.get("replies"),
                    matched_terms=post.get("matched_terms"),
                    mentions_token_address=post.get("mentions_token_address"),
                    source=self.source.name,
                    is_demo=self.source.is_demo,
                )
            )
            written += 1
        await session.flush()
        return written

    # -- filtering ---------------------------------------------------------

    def _filter_window(self, window: TokenWindow, report: RunReport) -> bool:
        """The cheap gate. Every rejection is counted and named."""
        if window.size < self.settings.observation_min_snapshots:
            report.dropped["insufficient_history"] += 1
            return False

        liquidity = window.value("liquidity_usd")
        if liquidity is None:
            report.dropped["liquidity_unknown"] += 1
            return False
        if liquidity < self.settings.observation_min_liquidity_usd:
            report.dropped["below_liquidity_floor"] += 1
            return False

        holders = window.value("holders")
        if holders is not None and holders < self.settings.observation_min_holders:
            report.dropped["below_holder_floor"] += 1
            return False

        return True

    def _cooldown(self, anomaly_type: str) -> timedelta:
        """Standing conditions get a longer cooldown than events.

        "Volume spiked" is an event: worth reporting each time it happens.
        "Still liquid and quiet a week in" is a state that persists for days —
        re-reporting it every few hours is noise, not observation.
        """
        if anomaly_type in STANDING_ANOMALIES:
            return timedelta(hours=self.params.standing_cooldown_hours)
        return timedelta(minutes=self.settings.observation_cooldown_minutes)

    async def _is_duplicate(
        self, session: AsyncSession, subject_ref: str, anomaly_type: str, as_of: datetime
    ) -> bool:
        cutoff = as_of - self._cooldown(anomaly_type)
        found = await session.scalar(
            select(Anomaly.id)
            .join(Observation, Anomaly.observation_id == Observation.id)
            .where(
                Observation.subject_ref == subject_ref,
                Anomaly.anomaly_type == anomaly_type,
                Anomaly.detected_at >= cutoff,
            )
            .limit(1)
        )
        return found is not None

    # -- persistence -------------------------------------------------------

    async def _emit_event(
        self,
        session: AsyncSession,
        *,
        event_type: EventType,
        message: str,
        occurred_at: datetime,
        ref_type: str | None = None,
        ref_id: str | None = None,
        detail: dict | None = None,
        level: str = "INFO",
    ) -> None:
        session.add(
            SystemEvent(
                seq=await _next_seq(session, SystemEvent),
                event_type=str(event_type),
                message=message,
                level=level,
                ref_type=ref_type,
                ref_id=ref_id,
                detail=detail,
                occurred_at=occurred_at,
                is_demo=self.source.is_demo,
            )
        )
        await session.flush()

    async def _record_observation(
        self,
        session: AsyncSession,
        *,
        kind: ObservationKind,
        summary: str,
        subject_type: str,
        subject_ref: str,
        payload: dict,
        candidates: list[AnomalyCandidate],
        confidence: float,
        liquidity: float | None,
        as_of: datetime,
        report: RunReport,
    ) -> Observation:
        novelty = await novelty_score(session, summary, kind=str(kind))
        importance = importance_score([c.score for c in candidates], liquidity)

        observation = Observation(
            seq=await _next_seq(session, Observation),
            kind=str(kind),
            summary=summary,
            subject_type=subject_type,
            subject_ref=subject_ref,
            payload=payload,
            novelty_score=novelty,
            importance=importance,
            confidence=confidence,
            observed_at=as_of,
            source=self.source.name,
            llm_reviewed=False,
            is_demo=self.source.is_demo,
        )
        session.add(observation)
        await session.flush()
        report.observations_created += 1

        await self._emit_event(
            session,
            event_type=EventType.OBSERVATION,
            message=f"#{observation.seq} {summary}",
            occurred_at=as_of,
            ref_type="observation",
            ref_id=observation.id,
            detail={"novelty": novelty, "importance": importance},
        )
        report.events_emitted += 1

        for candidate in candidates:
            session.add(
                Anomaly(
                    observation_id=observation.id,
                    anomaly_type=candidate.anomaly_type,
                    detector=candidate.detector,
                    score=round(candidate.score, 4),
                    baseline=candidate.baseline,
                    measured=candidate.measured,
                    detected_at=as_of,
                    is_demo=self.source.is_demo,
                )
            )
            report.anomalies_created += 1
            await self._emit_event(
                session,
                event_type=EventType.ANOMALY,
                message=(
                    f"{candidate.anomaly_type} score={candidate.score:.2f} "
                    f"— {candidate.explanation}"
                ),
                occurred_at=as_of,
                ref_type="observation",
                ref_id=observation.id,
                detail={"detector": candidate.detector},
            )
            report.events_emitted += 1
        await session.flush()

        if importance >= self.settings.observation_memory_importance_floor:
            result = await store_memory(
                session,
                memory_type="OBSERVATION",
                content=summary,
                summary=f"{subject_ref[:12]}… {kind.lower()}",
                meta={"payload": payload, "novelty": novelty, "importance": importance},
                source=self.source.name,
                confidence=confidence,
                ref_type="observation",
                ref_id=observation.id,
                is_demo=self.source.is_demo,
                commit=False,
            )
            if result.created:
                report.memories_written += 1
                await self._emit_event(
                    session,
                    event_type=EventType.MEMORY_UPDATED,
                    message=f"observation #{observation.seq} written to memory",
                    occurred_at=as_of,
                    ref_type="memory",
                    ref_id=result.memory.id,
                )
                report.events_emitted += 1

        return observation

    # -- the cycle ---------------------------------------------------------

    async def run(
        self, session: AsyncSession, *, as_of: datetime | None = None, commit: bool = True
    ) -> RunReport:
        started = utcnow()
        report = RunReport()

        self._resolve_source(session)
        as_of = as_of or await self.source.latest_timestamp()
        if as_of is None:
            report.duration_ms = int((utcnow() - started).total_seconds() * 1000)
            return report
        report.as_of = as_of

        window_start = as_of - timedelta(hours=self.settings.observation_window_hours)
        tokens = await self.source.list_tokens()
        all_posts = await self.source.get_posts(since=window_start, until=as_of)
        report.posts_ingested = await self._store_posts(session, all_posts)

        for ref in tokens:
            report.subjects_examined += 1
            snapshots = await self.source.get_snapshots(
                ref.address, since=window_start, until=as_of
            )
            if not snapshots:
                report.dropped["no_measurements"] += 1
                continue

            token = await self._upsert_token(session, ref)
            report.snapshots_ingested += await self._store_snapshots(session, token, snapshots)

            window = build_token_window(ref, snapshots)
            if not self._filter_window(window, report):
                continue

            candidates = [
                candidate
                for detector in ONCHAIN_DETECTORS
                if (candidate := detector(window, self.params)) is not None
            ]

            posts = [
                post
                for post in all_posts
                if post.get("mentions_token_address") == ref.address
            ]
            social = build_social_window(
                posts,
                window_end=as_of,
                window_hours=self.settings.observation_window_hours,
                token_address=ref.address,
            )
            social_candidates = []
            if (velocity := social_velocity(social, self.params)) is not None:
                social_candidates.append(velocity)
            if (
                divergence := social_onchain_divergence(window, social, self.params)
            ) is not None:
                social_candidates.append(divergence)

            fresh: list[AnomalyCandidate] = []
            for candidate in [*candidates, *social_candidates]:
                if await self._is_duplicate(
                    session, ref.address, candidate.anomaly_type, as_of
                ):
                    report.dropped["duplicate_anomaly"] += 1
                    continue
                fresh.append(candidate)

            summary = self._summarize(ref, fresh, window, social)
            if not fresh:
                novelty = await novelty_score(session, summary, kind=str(ObservationKind.ONCHAIN))
                if novelty < self.settings.observation_novelty_floor:
                    report.dropped["not_novel_no_anomaly"] += 1
                    continue

            kind = self._classify(fresh, bool(social_candidates))
            await self._record_observation(
                session,
                kind=kind,
                summary=summary,
                subject_type="token",
                subject_ref=ref.address,
                payload=self._payload(window, social, fresh),
                candidates=fresh,
                confidence=confidence_score(window),
                liquidity=window.value("liquidity_usd"),
                as_of=as_of,
                report=report,
            )

        await self._run_narrative_detector(session, all_posts, as_of, report)
        await self._run_cluster_detector(session, as_of, window_start, report)

        report.duration_ms = int((utcnow() - started).total_seconds() * 1000)
        await self._record_run(session, report, started)
        if commit:
            await session.commit()
        return report

    async def _record_run(
        self, session: AsyncSession, report: RunReport, started: datetime
    ) -> None:
        """Observability row.

        Named for the pipeline, not for the observer agent: this is the
        deterministic stage. `model` is null and the cost is 0.0 because no
        model was called — not because the cost was not measured.
        """
        session.add(
            AgentRun(
                agent_name=PIPELINE_RUN_NAME,
                model=None,
                input_summary=(
                    f"{report.subjects_examined} subjects at "
                    f"{report.as_of.isoformat() if report.as_of else 'unknown'}"
                ),
                output_summary=(
                    f"{report.observations_created} observations, "
                    f"{report.anomalies_created} anomalies, "
                    f"{sum(report.dropped.values())} dropped"
                ),
                duration_ms=report.duration_ms,
                status="OK",
                estimated_cost_usd=0.0,
                started_at=started,
                is_demo=self.source.is_demo,
            )
        )
        await session.flush()

    async def _run_narrative_detector(
        self, session: AsyncSession, posts: list[dict], as_of: datetime, report: RunReport
    ) -> None:
        social = build_social_window(
            posts, window_end=as_of, window_hours=self.settings.observation_window_hours
        )
        for candidate in narrative_acceleration(social, self.params)[:3]:
            term = str(candidate.measured.get("term"))
            if await self._is_duplicate(session, f"term:{term}", candidate.anomaly_type, as_of):
                report.dropped["duplicate_anomaly"] += 1
                continue
            await self._record_observation(
                session,
                kind=ObservationKind.SOCIAL,
                summary=f"narrative: {candidate.explanation}",
                subject_type="term",
                subject_ref=f"term:{term}",
                payload={"term": term, **candidate.measured},
                candidates=[candidate],
                confidence=1.0,
                liquidity=None,
                as_of=as_of,
                report=report,
            )

    async def _run_cluster_detector(
        self,
        session: AsyncSession,
        as_of: datetime,
        window_start: datetime,
        report: RunReport,
    ) -> None:
        clusters = (
            await session.scalars(
                select(WalletCluster).where(
                    WalletCluster.created_at >= window_start,
                    WalletCluster.created_at <= as_of,
                )
            )
        ).all()
        for cluster in clusters:
            subject = f"cluster:{cluster.id}"
            candidate = new_wallet_cluster(
                {
                    "method": cluster.method,
                    "confidence": cluster.confidence,
                    "size": cluster.size,
                    "label": cluster.label,
                }
            )
            if await self._is_duplicate(session, subject, candidate.anomaly_type, as_of):
                report.dropped["duplicate_anomaly"] += 1
                continue
            await self._record_observation(
                session,
                kind=ObservationKind.ONCHAIN,
                summary=f"wallet cluster: {candidate.explanation}",
                subject_type="wallet_cluster",
                subject_ref=subject,
                payload=candidate.measured,
                candidates=[candidate],
                confidence=0.5,
                liquidity=None,
                as_of=as_of,
                report=report,
            )

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _classify(candidates: list[AnomalyCandidate], had_social: bool) -> ObservationKind:
        types = {candidate.anomaly_type for candidate in candidates}
        social_types = {"SOCIAL_VELOCITY", "NARRATIVE_ACCELERATION"}
        mixed = {"SOCIAL_ONCHAIN_DIVERGENCE"}
        if types & mixed:
            return ObservationKind.DERIVED
        if types and types <= social_types:
            return ObservationKind.SOCIAL
        if not types and had_social:
            return ObservationKind.SOCIAL
        return ObservationKind.ONCHAIN

    @staticmethod
    def _summarize(
        ref: TokenRef,
        candidates: list[AnomalyCandidate],
        window: TokenWindow,
        social,  # SocialWindow
    ) -> str:
        label = ref.symbol or ref.address[:10]
        if candidates:
            return f"{label}: " + "; ".join(c.explanation for c in candidates)
        liquidity = window.value("liquidity_usd")
        holders = window.value("holders")
        return (
            f"{label}: no anomaly. liquidity "
            f"{'unknown' if liquidity is None else f'${liquidity:,.0f}'}, "
            f"{'unknown' if holders is None else int(holders)} holders, "
            f"{social.latest_hour} mentions in the last hour"
        )

    @staticmethod
    def _payload(window: TokenWindow, social, candidates: list[AnomalyCandidate]) -> dict:
        return {
            "liquidity_usd": window.value("liquidity_usd"),
            "volume_usd": window.value("volume_usd"),
            "holders": window.value("holders"),
            "holder_concentration_top10": window.value("holder_concentration_top10"),
            "buys": window.value("buys"),
            "sells": window.value("sells"),
            "age_seconds": window.value("age_seconds"),
            "mentions_last_hour": social.latest_hour,
            "mentions_window": sum(social.hourly_counts),
            "window_points": window.size,
            "detectors_fired": [candidate.detector for candidate in candidates],
        }


async def run_backfill(
    session: AsyncSession,
    *,
    source: ObservationSource | None = None,
    settings: Settings | None = None,
    step_hours: int = 1,
) -> list[RunReport]:
    """Walk the whole series hour by hour, the way a live loop would.

    A single run at the newest timestamp only sees the newest hour; a surge
    that happened twelve hours ago is, correctly, no longer news. Backfilling
    is how a frozen dataset produces the sequence of observations it would
    have produced live.
    """
    settings = settings or get_settings()
    pipeline = ObservationPipeline(source=source, settings=settings)

    latest = await pipeline.source.latest_timestamp()
    if latest is None:
        return []

    tokens = await pipeline.source.list_tokens()
    earliest: datetime | None = None
    for ref in tokens:
        snapshots = await pipeline.source.get_snapshots(ref.address)
        if snapshots:
            first = snapshots[0]["observed_at"]
            earliest = first if earliest is None else min(earliest, first)
    if earliest is None:
        return []

    start = earliest + timedelta(hours=settings.observation_window_hours)
    reports: list[RunReport] = []
    cursor = start
    while cursor <= latest:
        reports.append(await pipeline.run(session, as_of=cursor, commit=False))
        cursor += timedelta(hours=step_hours)

    await session.commit()
    return reports
