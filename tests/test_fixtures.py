"""Fixture integrity.

Fixtures are the demo data source, so they carry the same honesty rules as
real data: declared as demo, using placeholder identifiers only, and using
the same vocabulary as the rest of the system.
"""

from __future__ import annotations

import pytest

from app.core.enums import (
    AnomalyType,
    ContentType,
    DraftStatus,
    EventType,
    HypothesisStatus,
    MemoryType,
    ObservationKind,
    TraceStepKind,
)
from app.services.fixtures import FIXTURE_FILES, dataset_hash, fixtures_dir, load_fixture

DEMO_FILES = tuple(name for name in FIXTURE_FILES if name != "agents.json")


@pytest.mark.parametrize("name", FIXTURE_FILES)
def test_fixture_file_exists_and_declares_itself(name):
    data = load_fixture(name)
    assert "_meta" in data, f"{name} must declare _meta"
    assert "note" in data["_meta"]


@pytest.mark.parametrize("name", DEMO_FILES)
def test_demo_fixtures_are_marked_demo(name):
    assert load_fixture(name)["_meta"]["is_demo"] is True


def test_dataset_hash_is_stable_and_covers_the_files():
    first = dataset_hash()
    assert len(first) == 64
    assert first == dataset_hash()
    assert (fixtures_dir() / "research.json").is_file()


def test_placeholder_identifiers_only():
    """No fixture may reference a real-looking address."""
    tokens = load_fixture("tokens.json")
    for token in tokens["tokens"]:
        assert token["address"].startswith("DEMO")
    for wallet in tokens["wallets"]:
        assert wallet["address"].startswith("DEMO")


def test_observation_and_anomaly_vocabulary():
    research = load_fixture("research.json")
    kinds = {str(item) for item in ObservationKind}
    anomaly_types = {str(item) for item in AnomalyType}

    for observation in research["observations"]:
        assert observation["kind"] in kinds
        for anomaly in observation.get("anomalies", []):
            assert anomaly["anomaly_type"] in anomaly_types
            assert anomaly["detector"], "an anomaly must name the detector that fired"


def test_hypotheses_are_complete():
    required = (
        "statement",
        "question",
        "population",
        "sample_definition",
        "timeframe",
        "baseline",
        "expected_result",
        "falsification_condition",
    )
    statuses = {str(item) for item in HypothesisStatus}
    for hypothesis in load_fixture("research.json")["hypotheses"]:
        assert hypothesis["status"] in statuses
        for field in required:
            assert hypothesis[field].strip(), f"{field} is required"


def test_experiments_declare_limitations_and_reproducibility_fields():
    for experiment in load_fixture("research.json")["experiments"]:
        assert experiment["dataset_version"]
        assert experiment["limitations"]
        assert experiment["method"]
        for result in experiment.get("results", []):
            assert result["limitations"]
            assert result["critic_verdict"]


def test_trace_steps_use_the_declared_vocabulary():
    kinds = {str(item) for item in TraceStepKind}
    for trace in load_fixture("research.json")["traces"]:
        for step in trace["steps"]:
            assert step["kind"] in kinds


def test_memory_types_are_valid():
    valid = {str(item) for item in MemoryType}
    for memory in load_fixture("memories.json")["memories"]:
        assert memory["memory_type"] in valid


def test_drafts_use_declared_types_and_statuses():
    content_types = {str(item) for item in ContentType}
    statuses = {str(item) for item in DraftStatus}
    for draft in load_fixture("content.json")["drafts"]:
        assert draft["content_type"] in content_types
        assert draft.get("status", "PENDING") in statuses
        assert draft["body"].strip()


def test_events_use_declared_types():
    valid = {str(item) for item in EventType}
    for event in load_fixture("events.json")["events"]:
        assert event["event_type"] in valid


def test_only_agents_that_actually_run_are_marked_implemented():
    """The four deterministic engines do the job; the agents do not exist."""
    from app.agents import IMPLEMENTED_AGENTS

    for agent in load_fixture("agents.json")["agents"]:
        assert agent["implemented"] is (agent["name"] in IMPLEMENTED_AGENTS), agent["name"]
        assert agent["question"].endswith("?")
