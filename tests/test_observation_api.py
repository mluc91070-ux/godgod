"""Anomaly listing and the pipeline trigger over HTTP."""

from __future__ import annotations


async def test_anomalies_list_carries_detector_and_evidence(client):
    body = (await client.get("/api/anomalies")).json()
    assert body["total"] >= 1
    anomaly = body["items"][0]
    assert anomaly["detector"]
    assert anomaly["baseline"] is not None
    assert anomaly["measured"] is not None


async def test_anomalies_can_be_filtered(client):
    body = (
        await client.get("/api/anomalies", params={"type": "social_onchain_divergence"})
    ).json()
    assert {item["anomaly_type"] for item in body["items"]} <= {"SOCIAL_ONCHAIN_DIVERGENCE"}

    strong = (await client.get("/api/anomalies", params={"min_score": 0.5})).json()
    assert all(item["score"] >= 0.5 for item in strong["items"])


async def test_running_the_pipeline_requires_the_admin_token(client):
    assert (await client.post("/api/admin/observe/run")).status_code == 401


async def test_admin_can_run_a_cycle_and_the_report_says_no_model_ran(client, admin_headers):
    response = await client.post("/api/admin/observe/run", headers=admin_headers)
    assert response.status_code == 200

    report = response.json()
    assert report["llm_calls"] == 0
    assert report["cycles"] == 1
    assert report["subjects_examined"] == 6
    assert report["as_of"]
    assert isinstance(report["dropped"], dict)


async def test_admin_backfill_produces_the_planted_anomalies(client, admin_headers):
    before = (await client.get("/api/anomalies")).json()["total"]

    report = (
        await client.post(
            "/api/admin/observe/run", params={"mode": "backfill"}, headers=admin_headers
        )
    ).json()

    assert report["cycles"] > 1
    assert report["observations_created"] > 0
    assert report["llm_calls"] == 0

    after = (await client.get("/api/anomalies")).json()
    assert after["total"] > before

    types = {item["anomaly_type"] for item in after["items"]}
    assert "VOLUME_ACCELERATION" in types
    assert "LIQUIDITY_CHANGE" in types


async def test_observations_from_the_pipeline_are_marked_as_filter_only(client, admin_headers):
    await client.post("/api/admin/observe/run", params={"mode": "backfill"}, headers=admin_headers)
    body = (await client.get("/api/observations", params={"limit": 100})).json()

    pipeline_rows = [row for row in body["items"] if row["source"] == "fixture-timeseries"]
    assert pipeline_rows
    assert all(row["llm_reviewed"] is False for row in pipeline_rows)
    assert all(row["novelty_score"] is not None for row in pipeline_rows)


async def test_status_describes_the_observation_stage(client):
    pipeline = (await client.get("/api/status")).json()["pipeline"]

    assert pipeline["implemented"] is True
    assert pipeline["source"] == "fixture-timeseries"
    assert pipeline["source_is_demo"] is True
    assert pipeline["llm_in_loop"] is False
    assert len(pipeline["detectors"]) == 10
    assert "volume-acceleration-v1" in pipeline["detectors"]


async def test_status_records_when_the_pipeline_last_ran(client, admin_headers):
    assert (await client.get("/api/status")).json()["pipeline"]["last_run_at"] is None

    await client.post("/api/admin/observe/run", headers=admin_headers)
    assert (await client.get("/api/status")).json()["pipeline"]["last_run_at"] is not None
