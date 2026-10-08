import socket
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from nukkad.app import create_app
from nukkad.evaluation import loopback_only
from nukkad.places import Place
from nukkad.planning import Planner, QuestInput, Settings, baseline
from nukkad.storage import Store


def test_combined_walk_exceeding_budget_selects_only_feasible_subset(registry, monkeypatch):
    maps = registry[0]
    graph = maps.graph()
    graph.remove_edges_from(list(graph.edges(keys=True)))
    for node in (2, 3):
        graph.add_edge(1, node, length=700, highway="residential")
        graph.add_edge(node, 1, length=700, highway="residential")
    places = [
        Place(
            id=f"stop-{node}",
            name=f"Stop {node}",
            kind="park",
            point={"lat": 28.639, "lon": 77.361},
            entrance={"lat": 28.639, "lon": 77.361},
            entrance_node=node,
        )
        for node in (2, 3)
    ]
    monkeypatch.setattr(maps, "graph", lambda snapshot: graph)
    monkeypatch.setattr(maps, "places", lambda snapshot: places)
    plan = Planner(maps, Settings(), lambda: datetime(2026, 10, 8, 7, tzinfo=UTC))
    request = QuestInput(minutes=40)
    candidates = plan.candidates(request, [])
    assert len(candidates) == 2
    result = plan.build(candidates, baseline(candidates, []), request)
    assert len(result["stops"]) == 1
    assert result["estimated_minutes"] <= 40


def test_restart_preserves_outcomes_and_marks_unfinished_job_interrupted(registry):
    maps, store, _, _, _ = registry
    store.put("outcome", "saved", {"id": "saved", "note": "Exact note"})
    store.put("job", "interrupted", {"id": "interrupted", "status": "running"})
    with TestClient(create_app(maps.config), base_url="http://127.0.0.1") as client:
        assert client.get("/api/outcomes").json()[0]["note"] == "Exact note"
        assert client.get("/api/jobs/interrupted").json()["status"] == "interrupted"
        for path in [
            "/",
            "/static/app.js",
            "/static/style.css",
            "/static/vendor/leaflet.js",
            "/static/vendor/leaflet.css",
        ]:
            assert client.get(path).status_code == 200
    assert Store(maps.config.data_dir).get("outcome", "saved")["note"] == "Exact note"


def test_network_guard_rejects_non_loopback_without_changing_machine_network():
    original = socket.socket.connect
    with loopback_only() as attempts, socket.socket() as connection:
        with pytest.raises(OSError, match="non-loopback"):
            connection.connect(("203.0.113.1", 443))
        assert attempts == ["203.0.113.1"]
    assert socket.socket.connect is original
