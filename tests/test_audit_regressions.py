import json
import time
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from nukkad.app import create_app
from nukkad.places import Place
from nukkad.planning import Planner, QuestInput, Settings
from nukkad.quests import accept


def test_browser_multipart_contract_imports_a_saved_extract(registry):
    maps, _, _, area, source = registry
    with TestClient(create_app(maps.config), base_url="http://127.0.0.1") as client:
        client.headers["X-Nukkad-Token"] = client.get("/api/session").json()["token"]
        response = client.post(
            "/api/areas/import",
            data={"metadata": json.dumps(area.model_dump())},
            files={"extract": ("neighbourhood.osm", source.read_bytes(), "application/xml")},
        )
        assert response.status_code == 202
        key = response.json()["id"]
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            job = client.get("/api/jobs/" + key).json()
            if job["status"] == "complete":
                break
            assert job["status"] != "failed", job
            time.sleep(0.01)
        assert job["status"] == "complete"
        assert client.get("/api/area").json()["source"] == "user-imported OpenStreetMap XML"


def test_refreshed_snapshot_resnaps_stored_entrance(registry):
    maps, store, _, area, source = registry
    place = maps.places()[0]
    store.put("place", place.id, place.model_dump())
    source.write_text(
        source.read_text().replace('id="2"', 'id="22"').replace('ref="2"', 'ref="22"')
    )
    maps.acquire(area, source)
    refreshed = maps.places()[0]
    assert refreshed.entrance_node == 22
    assert refreshed.entrance == place.entrance


def test_acceptance_uses_full_registry_instead_of_a_new_shortlist(registry, monkeypatch):
    import nukkad.quests as quests

    maps = registry[0]
    graph = maps.graph()
    graph.remove_edges_from(list(graph.edges(keys=True)))
    places = []
    for index in range(2, 18):
        graph.add_node(index, x=77.36 + index * 0.00001, y=28.639)
        graph.add_edge(1, index, length=index * 10, highway="residential")
        graph.add_edge(index, 1, length=index * 10, highway="residential")
        places.append(
            Place(
                id=f"stop-{index}",
                name=f"Stop {index}",
                kind="park" if index == 17 else "market",
                point={"lat": 28.639, "lon": 77.36},
                entrance={"lat": 28.639, "lon": 77.36 + index * 0.00001},
                entrance_node=index,
            )
        )
    monkeypatch.setattr(maps, "graph", lambda snapshot: graph)
    monkeypatch.setattr(maps, "places", lambda snapshot: places)

    def clock():
        return datetime(2026, 10, 9, 7, tzinfo=UTC)

    original = Planner
    monkeypatch.setattr(quests, "Planner", lambda maps, settings: original(maps, settings, clock))
    settings = Settings(max_stops=1)
    planner = Planner(maps, settings, clock)
    request = QuestInput()
    pool = planner.candidates(request, ["nature"])
    assert "stop-17" in {place.id for place in pool}
    assert "stop-17" not in {place.id for place in planner.candidates(request, [])}
    ranked = ["stop-17", *[place.id for place in pool if place.id != "stop-17"]]
    quest = planner.build(pool, ranked, request)
    assert accept(quest, maps, settings)["status"] == "accepted"


def test_card_date_uses_saved_timezone_across_utc_midnight(registry, monkeypatch):
    import nukkad.quests as quests

    maps, store, snapshot, _, _ = registry
    snapshot["area"]["timezone"] = "Pacific/Kiritimati"
    store.put("snapshot", snapshot["id"], snapshot)
    moment = [datetime(2026, 10, 8, 22, tzinfo=UTC)]
    original = Planner
    monkeypatch.setattr(
        quests, "Planner", lambda maps, settings: original(maps, settings, lambda: moment[0])
    )
    settings = Settings(daylight_required=False)
    planner = Planner(maps, settings, lambda: moment[0])
    pool = planner.candidates(QuestInput(), [])
    quest = planner.build(pool, [place.id for place in pool], QuestInput())
    moment[0] = datetime(2026, 10, 9, 1, tzinfo=UTC)
    assert accept(quest, maps, settings)["status"] == "accepted"
