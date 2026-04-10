from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

from lineage_graphrag.api.app import create_app


def _prepare_graph(client: TestClient, fixture_payload: dict, graph_id: str) -> None:
    import_resp = client.post(
        "/v1/graphs/import",
        json={"graph_id": graph_id, "lineage_json": fixture_payload},
    )
    assert import_resp.status_code == 200

    build_resp = client.post("/v1/graphs/build", json={"graph_id": graph_id})
    assert build_resp.status_code == 200


def _set_snapshot_dir(subdir: str) -> None:
    runtime_dir = Path("tests/.runtime_snapshots") / subdir
    runtime_dir.mkdir(parents=True, exist_ok=True)
    os.environ["LINEAGE_SNAPSHOT_DIR"] = str(runtime_dir)


def test_api_flow_agent_mode(fixture_payload: dict) -> None:
    _set_snapshot_dir("agent")
    app = create_app("configs/base.yaml")
    client = TestClient(app)
    graph_id = "video_demo"
    _prepare_graph(client, fixture_payload, graph_id)

    ask_resp = client.post(
        "/v1/queries/ask",
        json={
            "graph_id": graph_id,
            "question": "What does job_video_tag_enrich impact downstream?",
            "top_k": 6,
            "mode": "agent",
            "max_steps": 3,
        },
    )
    assert ask_resp.status_code == 200
    ask_body = ask_resp.json()
    assert "answer" in ask_body
    assert ask_body["retrieval"]["mode"] == "agent"
    assert "reasoning_steps" in ask_body["retrieval"]
    assert isinstance(ask_body["sub_questions"], list)

    impact_resp = client.post(
        "/v1/impact/what-if",
        json={
            "graph_id": graph_id,
            "change_spec": {
                "source": "job_video_tag_enrich",
                "target": "dwd_video_profile",
                "relation": "transitions",
                "scope": "moderation",
                "max_depth": 3,
            },
        },
    )
    assert impact_resp.status_code == 200
    body = impact_resp.json()
    assert "direct_impacts" in body
    assert "scoped_impact" in body


def test_api_flow_noagent_mode(fixture_payload: dict) -> None:
    _set_snapshot_dir("noagent")
    app = create_app("configs/base.yaml")
    client = TestClient(app)
    graph_id = "video_demo_noagent"
    _prepare_graph(client, fixture_payload, graph_id)

    ask_resp = client.post(
        "/v1/queries/ask",
        json={
            "graph_id": graph_id,
            "question": "Show core lineage around dwd_video_profile.",
            "top_k": 6,
            "mode": "noagent",
            "max_steps": 3,
        },
    )
    assert ask_resp.status_code == 200
    ask_body = ask_resp.json()
    assert ask_body["retrieval"]["mode"] == "noagent"
    assert isinstance(ask_body["retrieval"]["chunk_ids"], list)
