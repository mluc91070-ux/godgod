"""Demo seeding rules."""

from __future__ import annotations

from sqlalchemy import select

from app.models import Agent, ContentDraft, Experiment, Memory, Observation, Token


async def test_seed_populates_the_research_chain(seeded):
    assert seeded["observations"] == 3
    assert seeded["hypotheses"] == 2
    assert seeded["experiments"] == 1
    assert seeded["experiment_results"] == 1
    assert seeded["memories"] == 6
    assert seeded["events"] == 12
    assert seeded["agents"] == 6


async def test_every_demo_row_is_flagged(session, seeded):
    for model in (Observation, Experiment, Memory, ContentDraft, Token):
        rows = (await session.scalars(select(model))).all()
        assert rows
        assert all(row.is_demo for row in rows), f"{model.__tablename__} must be flagged is_demo"


async def test_agent_roster_is_configuration_not_demo_data(session, seeded):
    agents = (await session.scalars(select(Agent))).all()
    assert all(agent.is_demo is False for agent in agents)


async def test_seed_is_idempotent(session, seeded):
    from app.services.seed import seed_demo

    again = await seed_demo(session)
    assert "skipped" in again

    observations = (await session.scalars(select(Observation))).all()
    assert len(observations) == 3


async def test_experiment_records_a_real_dataset_hash(session, seeded):
    from app.services.fixtures import dataset_hash

    experiment = await session.scalar(select(Experiment))
    assert experiment.dataset_hash == dataset_hash()
    assert len(experiment.dataset_hash) == 64
    assert experiment.dataset_hash != "COMPUTED_AT_SEED"


async def test_memories_have_no_fabricated_embeddings(session, seeded):
    memories = (await session.scalars(select(Memory))).all()
    assert all(memory.embedding is None for memory in memories), (
        "embedding generation is PHASE 2; PHASE 1 must not invent vectors"
    )
