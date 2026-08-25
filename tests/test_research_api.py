"""The research chain over HTTP."""

from __future__ import annotations


async def test_observation_detail_includes_its_anomalies(client):
    listing = (await client.get("/api/observations")).json()
    divergent = next(item for item in listing["items"] if item["seq"] == 41)

    detail = (await client.get(f"/api/observations/{divergent['id']}")).json()
    assert detail["llm_reviewed"] is False, "deterministic filtering only in PHASE 1"
    assert detail["anomalies"][0]["anomaly_type"] == "SOCIAL_ONCHAIN_DIVERGENCE"
    assert detail["anomalies"][0]["detector"]


async def test_observation_filters(client):
    social = (await client.get("/api/observations", params={"kind": "SOCIAL"})).json()
    assert {item["kind"] for item in social["items"]} == {"SOCIAL"}

    novel = (await client.get("/api/observations", params={"min_novelty": 0.8})).json()
    assert all(item["novelty_score"] >= 0.8 for item in novel["items"])


async def test_missing_observation_is_404(client):
    assert (await client.get("/api/observations/does-not-exist")).status_code == 404


async def test_every_hypothesis_is_falsifiable(client):
    body = (await client.get("/api/hypotheses")).json()
    assert body["items"]
    for item in body["items"]:
        assert item["falsification_condition"].strip()
        assert item["population"].strip()
        assert item["baseline"].strip()
        assert item["timeframe"].strip()


async def test_rejected_hypothesis_links_to_its_experiment(client):
    hypotheses = (await client.get("/api/hypotheses", params={"status": "REJECTED"})).json()
    assert hypotheses["total"] == 1
    hypothesis_id = hypotheses["items"][0]["id"]

    detail = (await client.get(f"/api/hypotheses/{hypothesis_id}")).json()
    assert detail["experiments"], "a rejected hypothesis must show what rejected it"


async def test_experiment_detail_carries_method_dataset_and_critic(client):
    listing = (await client.get("/api/experiments")).json()
    experiment_id = listing["items"][0]["id"]

    detail = (await client.get(f"/api/experiments/{experiment_id}")).json()
    assert detail["method"]
    assert detail["sample_size"] == 96
    assert detail["dataset_version"] == "demo-2026-08-20"
    assert detail["limitations"]

    result = detail["results"][0]
    assert result["outcome"] == "REJECTED"
    assert result["critic_verdict"] == "FAIL"
    assert result["critic_checks"]["sample_size"] == "FAIL"
    assert result["limitations"]

    assert detail["hypothesis"]["status"] == "REJECTED"


async def test_no_hypothesis_is_supported_without_a_passing_critic(client):
    experiments = (await client.get("/api/experiments")).json()["items"]
    for experiment in experiments:
        detail = (await client.get(f"/api/experiments/{experiment['id']}")).json()
        for result in detail["results"]:
            if result["outcome"] == "SUPPORTED":
                assert result["critic_verdict"] == "PASS"


async def test_trace_is_ordered_and_complete(client):
    traces = (await client.get("/api/traces")).json()
    assert traces["total"] == 1
    trace = traces["items"][0]

    kinds = [step["kind"] for step in trace["steps"]]
    assert kinds == [
        "OBSERVATION",
        "ANOMALY",
        "MEMORY_SEARCH",
        "HYPOTHESIS",
        "DATASET",
        "EXPERIMENT",
        "CRITIC",
        "RESULT",
        "MEMORY_UPDATE",
    ]
    positions = [step["position"] for step in trace["steps"]]
    assert positions == sorted(positions)

    detail = (await client.get(f"/api/traces/{trace['id']}")).json()
    assert detail["experiment_id"]
    assert detail["hypothesis_id"]


async def test_patterns_record_rejections_too(client):
    body = (await client.get("/api/patterns")).json()
    statuses = {item["name"]: item["status"] for item in body["items"]}
    assert statuses["attention predicts survival"] == "REJECTED"
    assert statuses["single-account amplification"] == "CANDIDATE"
