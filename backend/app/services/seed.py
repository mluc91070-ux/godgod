"""Seed the database from fixtures.

Idempotent by design: seeding twice does not duplicate rows. Everything the
seeder writes is marked ``is_demo=True`` except the agent roster, which is
configuration describing the intended architecture.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Agent,
    Anomaly,
    ContentDraft,
    Experiment,
    ExperimentResult,
    Hypothesis,
    Memory,
    MetricsSnapshot,
    Observation,
    Pattern,
    PublishedPost,
    ResearchSource,
    ResearchTrace,
    SocialAccount,
    SocialPost,
    SystemEvent,
    Token,
    TokenSnapshot,
    TraceStep,
    Wallet,
    WalletCluster,
)
from app.services.fixtures import dataset_hash, load_fixture, parse_dt

DEMO_TABLES = (
    PublishedPost,
    ContentDraft,
    TraceStep,
    ResearchTrace,
    ExperimentResult,
    Experiment,
    Hypothesis,
    Anomaly,
    Observation,
    Pattern,
    Memory,
    ResearchSource,
    SystemEvent,
    MetricsSnapshot,
    SocialPost,
    SocialAccount,
    TokenSnapshot,
    Token,
    Wallet,
    WalletCluster,
)


async def _count(session: AsyncSession, model: Any) -> int:
    return int(await session.scalar(select(func.count()).select_from(model)) or 0)


async def clear_demo_rows(session: AsyncSession) -> None:
    """Remove fixture rows only. Real rows (is_demo=False) are never touched."""
    for model in DEMO_TABLES:
        await session.execute(delete(model).where(model.is_demo.is_(True)))
    await session.flush()


async def seed_agents(session: AsyncSession) -> int:
    data = load_fixture("agents.json")
    written = 0
    for item in data["agents"]:
        existing = await session.scalar(select(Agent).where(Agent.name == item["name"]))
        target = existing or Agent(name=item["name"])
        target.role = item["role"]
        target.question = item["question"]
        target.inputs = item.get("inputs")
        target.outputs = item.get("outputs")
        target.allowed_tools = item.get("allowed_tools")
        target.model_role = item.get("model_role")
        target.implemented = bool(item.get("implemented", False))
        target.enabled = bool(item.get("enabled", True))
        target.is_demo = False
        session.add(target)
        written += 1
    await session.flush()
    return written


async def _seed_tokens(session: AsyncSession) -> dict[str, str]:
    data = load_fixture("tokens.json")
    cluster_ids: dict[str, str] = {}
    for item in data.get("wallet_clusters", []):
        cluster = WalletCluster(
            label=item.get("label"),
            method=item["method"],
            confidence=item.get("confidence"),
            size=item.get("size"),
            evidence=item.get("evidence"),
            is_demo=True,
        )
        session.add(cluster)
        await session.flush()
        cluster_ids[item["key"]] = cluster.id

    for item in data.get("wallets", []):
        session.add(
            Wallet(
                address=item["address"],
                label=item.get("label"),
                cluster_id=cluster_ids.get(item.get("cluster_key") or ""),
                first_seen_at=parse_dt(item.get("first_seen_at")),
                last_seen_at=parse_dt(item.get("last_seen_at")),
                is_demo=True,
            )
        )

    token_ids: dict[str, str] = {}
    for item in data["tokens"]:
        token = Token(
            address=item["address"],
            symbol=item.get("symbol"),
            name=item.get("name"),
            decimals=item.get("decimals"),
            launchpad=item.get("launchpad"),
            launch_time=parse_dt(item.get("launch_time")),
            bonding_curve_state=item.get("bonding_curve_state"),
            migrated_to_dex=item.get("migrated_to_dex"),
            first_seen_at=parse_dt(item.get("first_seen_at")),
            last_seen_at=parse_dt(item.get("last_seen_at")),
            market_cap_usd=item.get("market_cap_usd"),
            liquidity_usd=item.get("liquidity_usd"),
            volume_24h_usd=item.get("volume_24h_usd"),
            holders=item.get("holders"),
            holder_concentration_top10=item.get("holder_concentration_top10"),
            source=item.get("source"),
            is_demo=True,
        )
        session.add(token)
        await session.flush()
        token_ids[item["address"]] = token.id
        for snap in item.get("snapshots", []):
            session.add(
                TokenSnapshot(
                    token_id=token.id,
                    observed_at=parse_dt(snap["observed_at"]),
                    market_cap_usd=snap.get("market_cap_usd"),
                    liquidity_usd=snap.get("liquidity_usd"),
                    volume_usd=snap.get("volume_usd"),
                    holders=snap.get("holders"),
                    holder_concentration_top10=snap.get("holder_concentration_top10"),
                    transactions=snap.get("transactions"),
                    buys=snap.get("buys"),
                    sells=snap.get("sells"),
                    age_seconds=snap.get("age_seconds"),
                    liquidity_change_pct=snap.get("liquidity_change_pct"),
                    holder_change_pct=snap.get("holder_change_pct"),
                    source="fixture",
                    is_demo=True,
                )
            )
    await session.flush()
    return token_ids


async def _seed_social(session: AsyncSession) -> None:
    data = load_fixture("social.json")
    account_ids: dict[str, str] = {}
    for item in data.get("accounts", []):
        account = SocialAccount(
            external_id=item["external_id"],
            handle=item.get("handle"),
            display_name=item.get("display_name"),
            followers=item.get("followers"),
            account_created_at=parse_dt(item.get("account_created_at")),
            is_demo=True,
        )
        session.add(account)
        await session.flush()
        account_ids[item["external_id"]] = account.id

    for item in data.get("posts", []):
        session.add(
            SocialPost(
                external_id=item["external_id"],
                account_id=account_ids.get(item.get("account_external_id") or ""),
                posted_at=parse_dt(item.get("posted_at")),
                text=item["text"],
                lang=item.get("lang"),
                likes=item.get("likes"),
                reposts=item.get("reposts"),
                replies=item.get("replies"),
                matched_terms=item.get("matched_terms"),
                mentions_token_address=item.get("mentions_token_address"),
                source="fixture",
                is_demo=True,
            )
        )
    await session.flush()


async def _seed_research(session: AsyncSession) -> dict[str, dict[str, str]]:
    data = load_fixture("research.json")
    ids: dict[str, dict[str, str]] = {
        "observation": {},
        "hypothesis": {},
        "experiment": {},
        "anomaly": {},
    }

    for item in data.get("sources", []):
        session.add(
            ResearchSource(
                kind=item["kind"],
                name=item["name"],
                url=item.get("url"),
                description=item.get("description"),
                reliability=item.get("reliability"),
                last_used_at=parse_dt(item.get("last_used_at")),
                is_demo=True,
            )
        )

    for item in data.get("observations", []):
        observation = Observation(
            seq=item.get("seq"),
            kind=item["kind"],
            summary=item["summary"],
            subject_type=item.get("subject_type"),
            subject_ref=item.get("subject_ref"),
            payload=item.get("payload"),
            novelty_score=item.get("novelty_score"),
            importance=item.get("importance"),
            confidence=item.get("confidence"),
            observed_at=parse_dt(item["observed_at"]),
            source=item.get("source"),
            llm_reviewed=bool(item.get("llm_reviewed", False)),
            is_demo=True,
        )
        session.add(observation)
        await session.flush()
        ids["observation"][item["key"]] = observation.id
        for anomaly_item in item.get("anomalies", []):
            anomaly = Anomaly(
                observation_id=observation.id,
                anomaly_type=anomaly_item["anomaly_type"],
                detector=anomaly_item["detector"],
                score=anomaly_item.get("score"),
                baseline=anomaly_item.get("baseline"),
                measured=anomaly_item.get("measured"),
                detected_at=parse_dt(anomaly_item["detected_at"]),
                is_demo=True,
            )
            session.add(anomaly)
            await session.flush()
            ids["anomaly"][item["key"]] = anomaly.id

    for item in data.get("hypotheses", []):
        hypothesis = Hypothesis(
            seq=item.get("seq"),
            statement=item["statement"],
            question=item["question"],
            variables=item.get("variables"),
            population=item["population"],
            sample_definition=item["sample_definition"],
            timeframe=item["timeframe"],
            baseline=item["baseline"],
            expected_result=item["expected_result"],
            falsification_condition=item["falsification_condition"],
            confidence=item.get("confidence"),
            status=item.get("status", "PROPOSED"),
            origin_observation_id=ids["observation"].get(item.get("origin_observation_key") or ""),
            is_demo=True,
        )
        session.add(hypothesis)
        await session.flush()
        ids["hypothesis"][item["key"]] = hypothesis.id

    for item in data.get("experiments", []):
        declared_hash = item.get("dataset_hash")
        experiment = Experiment(
            seq=item.get("seq"),
            hypothesis_id=ids["hypothesis"][item["hypothesis_key"]],
            title=item["title"],
            method=item["method"],
            features=item.get("features"),
            parameters=item.get("parameters"),
            dataset_version=item["dataset_version"],
            dataset_hash=(
                dataset_hash() if declared_hash in (None, "COMPUTED_AT_SEED") else declared_hash
            ),
            sample_size=item.get("sample_size"),
            train_period=item.get("train_period"),
            validation_period=item.get("validation_period"),
            out_of_sample_period=item.get("out_of_sample_period"),
            status=item.get("status", "PLANNED"),
            started_at=parse_dt(item.get("started_at")),
            completed_at=parse_dt(item.get("completed_at")),
            limitations=item.get("limitations"),
            is_demo=True,
        )
        session.add(experiment)
        await session.flush()
        ids["experiment"][item["key"]] = experiment.id
        for result_item in item.get("results", []):
            session.add(
                ExperimentResult(
                    experiment_id=experiment.id,
                    outcome=result_item["outcome"],
                    summary=result_item["summary"],
                    metrics=result_item.get("metrics"),
                    effect_size=result_item.get("effect_size"),
                    p_value=result_item.get("p_value"),
                    confidence=result_item.get("confidence"),
                    critic_verdict=result_item.get("critic_verdict"),
                    critic_notes=result_item.get("critic_notes"),
                    critic_checks=result_item.get("critic_checks"),
                    limitations=result_item.get("limitations"),
                    is_demo=True,
                )
            )

    for item in data.get("traces", []):
        trace = ResearchTrace(
            seq=item.get("seq"),
            title=item.get("title"),
            hypothesis_id=ids["hypothesis"].get(item.get("hypothesis_key") or ""),
            experiment_id=ids["experiment"].get(item.get("experiment_key") or ""),
            started_at=parse_dt(item.get("started_at")),
            completed_at=parse_dt(item.get("completed_at")),
            is_demo=True,
        )
        session.add(trace)
        await session.flush()
        for position, step in enumerate(item.get("steps", [])):
            ref_type = step.get("ref_type")
            ref_key = step.get("ref_key")
            session.add(
                TraceStep(
                    trace_id=trace.id,
                    position=position,
                    kind=step["kind"],
                    summary=step["summary"],
                    ref_type=ref_type,
                    ref_id=ids.get(ref_type or "", {}).get(ref_key or ""),
                    occurred_at=parse_dt(step.get("occurred_at")),
                    detail=step.get("detail"),
                    is_demo=True,
                )
            )

    for item in data.get("patterns", []):
        session.add(
            Pattern(
                name=item["name"],
                description=item["description"],
                status=item.get("status", "CANDIDATE"),
                support_count=item.get("support_count", 0),
                contradiction_count=item.get("contradiction_count", 0),
                confidence=item.get("confidence"),
                first_seen_at=parse_dt(item.get("first_seen_at")),
                last_confirmed_at=parse_dt(item.get("last_confirmed_at")),
                evidence_refs=item.get("evidence_refs"),
                is_demo=True,
            )
        )

    await session.flush()
    return ids


async def _seed_memories(session: AsyncSession, ids: dict[str, dict[str, str]]) -> None:
    data = load_fixture("memories.json")
    for item in data.get("memories", []):
        ref_type = item.get("ref_type")
        session.add(
            Memory(
                memory_type=item["memory_type"],
                content=item["content"],
                summary=item.get("summary"),
                meta=item.get("meta"),
                source=item.get("source"),
                confidence=item.get("confidence"),
                ref_type=ref_type,
                ref_id=ids.get(ref_type or "", {}).get(item.get("ref_key") or ""),
                embedding=None,  # PHASE 2
                is_demo=True,
            )
        )
    await session.flush()


async def _seed_content(session: AsyncSession, ids: dict[str, dict[str, str]]) -> None:
    data = load_fixture("content.json")
    for item in data.get("drafts", []):
        source_kind = item.get("source_kind")
        session.add(
            ContentDraft(
                content_type=item["content_type"],
                body=item["body"],
                status=item.get("status", "PENDING"),
                reviewer_verdict=item.get("reviewer_verdict"),
                reviewer_notes=item.get("reviewer_notes"),
                rejection_reason=item.get("rejection_reason"),
                source_kind=source_kind,
                source_id=ids.get(source_kind or "", {}).get(item.get("source_key") or ""),
                approved_at=parse_dt(item.get("approved_at")),
                approved_by=item.get("approved_by"),
                is_demo=True,
            )
        )
    await session.flush()


async def _seed_events(session: AsyncSession, ids: dict[str, dict[str, str]]) -> None:
    data = load_fixture("events.json")
    for item in data.get("events", []):
        ref_type = item.get("ref_type")
        session.add(
            SystemEvent(
                seq=item.get("seq"),
                event_type=item["event_type"],
                message=item["message"],
                level=item.get("level", "INFO"),
                ref_type=ref_type,
                ref_id=ids.get(ref_type or "", {}).get(item.get("ref_key") or ""),
                detail=item.get("detail"),
                occurred_at=parse_dt(item["occurred_at"]),
                is_demo=True,
            )
        )
    await session.flush()


async def seed_demo(session: AsyncSession, *, force: bool = False) -> dict[str, int]:
    """Load the demo fixtures. Returns a per-table row count."""
    existing = await _count(session, Observation)
    if existing and not force:
        return {"skipped": existing}

    if force:
        await clear_demo_rows(session)

    await seed_agents(session)
    await _seed_tokens(session)
    await _seed_social(session)
    ids = await _seed_research(session)
    await _seed_memories(session, ids)
    await _seed_content(session, ids)
    await _seed_events(session, ids)
    await session.commit()

    return {
        "tokens": await _count(session, Token),
        "token_snapshots": await _count(session, TokenSnapshot),
        "wallets": await _count(session, Wallet),
        "social_posts": await _count(session, SocialPost),
        "observations": await _count(session, Observation),
        "anomalies": await _count(session, Anomaly),
        "hypotheses": await _count(session, Hypothesis),
        "experiments": await _count(session, Experiment),
        "experiment_results": await _count(session, ExperimentResult),
        "traces": await _count(session, ResearchTrace),
        "patterns": await _count(session, Pattern),
        "memories": await _count(session, Memory),
        "drafts": await _count(session, ContentDraft),
        "events": await _count(session, SystemEvent),
        "agents": await _count(session, Agent),
    }
