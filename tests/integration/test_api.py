from __future__ import annotations

from fastapi.testclient import TestClient

from lineage_graphrag.api.app import create_app


def test_api_flow(fixture_payload: dict) -> None:
    app = create_app("configs/base.yaml")
    client = TestClient(app)
    graph_id = "video_demo"

    import_resp = client.post(
        "/v1/graphs/import",
        json={"graph_id": graph_id, "lineage_json": fixture_payload},
    )
    assert import_resp.status_code == 200

    build_resp = client.post("/v1/graphs/build", json={"graph_id": graph_id})
    assert build_resp.status_code == 200

    ask_resp = client.post(
        "/v1/queries/ask",
        json={"graph_id": graph_id, "question": "job_video_tag_enrich 是什么意思", "top_k": 6},
    )
    assert ask_resp.status_code == 200
    assert "answer" in ask_resp.json()

    impact_resp = client.post(
        "/v1/impact/what-if",
        json={
            "graph_id": graph_id,
            "change_spec": {
                "source": "job_video_tag_enrich",
                "target": "dwd_video_profile",
                "relation": "transitions",
                "scope": "moderation",
                "max_depth": 3
            }
        },
    )
    assert impact_resp.status_code == 200
    body = impact_resp.json()
    assert "direct_impacts" in body
    assert "scoped_impact" in body

