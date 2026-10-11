"""An isolated HTTP flow through search, maps, reporting and the local notebook."""

import io
import json

from fastapi.testclient import TestClient
from PIL import Image
from test_location_cards import wait

from nukkad.app import create_app
from nukkad.ollama import ModelFailure


def test_working_pages_keep_the_full_product_flow(registry, monkeypatch):
    maps, store, _, area, source = registry
    monkeypatch.setattr(
        "nukkad.geocoding.search",
        lambda store, query: {
            "matches": [
                {
                    "name": "Synthetic locality",
                    "label": "Synthetic locality, Sample city",
                    "point": area.start.model_dump(),
                }
            ],
            "source": "Controlled search fixture",
            "cached": False,
        },
    )

    def unavailable(*args, **kwargs):
        raise ModelFailure("Controlled unavailable model")

    monkeypatch.setattr("nukkad.ollama.Ollama.generate", unavailable)
    with TestClient(create_app(maps.config), base_url="http://127.0.0.1") as client:
        client.headers["X-Nukkad-Token"] = client.get("/api/session").json()["token"]
        search = client.post("/api/locations/search", json={"query": "Synthetic locality"})
        assert search.status_code == 200
        metadata = {
            **area.model_dump(),
            "name": search.json()["matches"][0]["name"],
            "public_start_confirmed": False,
        }
        imported = client.post(
            "/api/areas/import",
            data={"metadata": json.dumps(metadata)},
            files={"extract": ("fixture.osm", source.read_bytes(), "application/xml")},
        )
        assert wait(client, imported.json())["status"] == "complete"
        assert not client.get("/api/area/status").json()["area"]["public_start_confirmed"]
        confirmed = client.post(
            "/api/areas/reuse", json={**metadata, "public_start_confirmed": True}
        )
        assert wait(client, confirmed.json())["status"] == "complete"
        assert client.get("/api/area/status").json()["area"]["public_start_confirmed"]
        created = client.post(
            "/api/places",
            json={
                "name": "Synthetic known place",
                "kind": "park",
                "entrance": area.start.model_dump(),
                "public_access_confirmed": True,
            },
        )
        assert created.status_code == 201
        place = created.json()
        suggestions = client.post(
            "/api/locations/suggest", json={"query": "Synthetic known", "scope": "place"}
        )
        assert suggestions.json()["matches"][0]["place_id"] == place["id"]
        report = client.patch(
            "/api/places/" + place["id"],
            json={"action": "verify", "detail": "Checked the synthetic public entrance"},
        )
        assert report.status_code == 200
        assert client.put("/api/settings", json={"daylight_required": False}).status_code == 200
        assert client.post("/api/quests/route-preview", json={"minutes": 30}).status_code == 200
        generated = client.post("/api/quests", json={"minutes": 30})
        result = wait(client, generated.json())
        assert result["status"] == "complete", result
        quest = client.get("/api/quests/" + result["result"]["quest_id"]).json()
        assert client.post("/api/quests/" + quest["id"] + "/accept").status_code == 200
        assert client.get("/api/quests/" + quest["id"] + "/card.png").status_code == 200
        reached = quest["stops"][0]
        outcome = client.put(
            "/api/quests/" + quest["id"] + "/outcome",
            json={
                "status": "completed",
                "note": "A synthetic walk report.",
                "stops": [
                    {
                        "id": item["id"],
                        "status": "reached" if item["id"] == reached["id"] else "skipped",
                    }
                    for item in quest["stops"]
                ],
                "place_experiences": [
                    {"stop_id": reached["id"], "note": "I noticed green shapes."}
                ],
            },
        )
        assert outcome.status_code == 200
        experience = client.get("/api/outcomes/" + outcome.json()["id"] + "/experiences").json()[0]
        output = io.BytesIO()
        Image.new("RGB", (64, 64), "green").save(output, "PNG")
        photo = client.post(
            "/api/experiences/" + experience["id"] + "/photos",
            files={"photo": ("synthetic.png", output.getvalue(), "image/png")},
        )
        assert photo.status_code == 201
        root = experience["place_id"]
        card_job = client.post(
            "/api/collection/" + root + "/generate",
            json={"experience_id": experience["id"], "mode": "manual"},
        )
        assert wait(client, card_job.json())["status"] == "complete"
        folder = client.get("/api/collection/" + root).json()
        card = folder["current_card"]
        updated = client.patch(
            "/api/collection/" + root + "/card",
            json={
                "version_id": card["id"],
                "summary": "They noticed green shapes.",
                "photo_id": photo.json()["id"],
            },
        )
        assert updated.status_code == 200
        assert (
            client.get("/api/location-cards/" + updated.json()["id"] + "/export.png").status_code
            == 200
        )
        assert client.get("/api/collection").json()["card_count"] == 1
        assert len(client.get("/api/collection/" + root).json()["card_versions"]) == 2
        for path in [
            "/?view=history",
            "/?view=folder&place=" + root,
            "/?view=preview&walk=" + quest["id"],
        ]:
            assert client.get(path).status_code == 200
    assert len(store.list("outcome")) == 1
