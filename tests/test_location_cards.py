import io
import threading
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from nukkad.app import create_app
from nukkad.backups import backup, restore
from nukkad.config import Config
from nukkad.journals import WrittenJournal
from nukkad.location_cards import CardSummary, CoverChoice, validate_summary
from nukkad.ollama import ModelFailure
from nukkad.outcomes import Outcome, save_outcome
from nukkad.photos import save_photo


def prepared(registry, key="walk"):
    maps, store, snapshot = registry[:3]
    quest = {
        "id": key,
        "snapshot_id": snapshot["id"],
        "status": "accepted",
        "stops": [{"id": "osm-way-20", "name": "Sample park"}],
    }
    store.put("quest", key, quest)
    value = Outcome(
        status="completed",
        stops=[{"id": "osm-way-20", "status": "reached"}],
        place_experiences=[{"stop_id": "osm-way-20", "note": "I enjoyed noticing tree outlines."}],
    )
    save_outcome(store, quest, value)
    experience = next(item for item in store.list("experience") if item["outcome_id"] == key)
    output = io.BytesIO()
    Image.new("RGB", (100, 80), "green").save(output, "PNG")
    photo = save_photo(maps.config, store, experience["id"], output.getvalue())
    return experience, photo, quest, value


def wait(client, job):
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        state = client.get("/api/jobs/" + job["id"]).json()
        if state["status"] not in {"running", "queued"}:
            return state
        time.sleep(0.01)
    pytest.fail("Card job did not finish")


def token(client):
    client.headers["X-Nukkad-Token"] = client.get("/api/session").json()["token"]


def ai_response(photo):
    def response(self, response_type, prompt, deadline, schema=None, images=None, image_ids=None):
        if response_type is not WrittenJournal:
            assert images and len(images) == 1
        if response_type is CoverChoice:
            return CoverChoice(
                photo_id=photo["id"], reason="Selection: A clear view for the reported observation."
            ), {}
        if response_type is WrittenJournal:
            assert not images
            return WrittenJournal(
                passages=[
                    {
                        "text": "They enjoyed noticing tree outlines.",
                        "quote": "I enjoyed noticing tree outlines.",
                    }
                ]
            ), {}
        return CardSummary(
            summary="They enjoyed noticing tree outlines during their reported visit.",
            evidence_ids=["note"],
        ), {}

    return response


def test_card_generation_editing_versions_collection_and_backup(registry, monkeypatch, tmp_path):
    experience, photo, _, _ = prepared(registry)
    monkeypatch.setattr("nukkad.ollama.Ollama.generate", ai_response(photo))
    with TestClient(create_app(registry[0].config), base_url="http://127.0.0.1") as client:
        token(client)
        for _ in range(2):
            job = client.post("/api/collection/osm-way-20/generate", json={}).json()
            state = wait(client, job)
            assert state["status"] == "complete", state
        folder = client.get("/api/collection/osm-way-20").json()
        assert len(folder["card_versions"]) == 2
        assert client.get("/api/collection").json()["card_count"] == 1
        assert folder["visits"][0]["journal"]["status"] == "pending"
        current = folder["current_card"]
        edited = client.patch(
            "/api/collection/osm-way-20/card",
            json={
                "version_id": current["id"],
                "summary": "They kept an edited account of the outlines.",
                "photo_id": photo["id"],
                "crop_x": 0,
                "crop_y": 1,
            },
        )
        assert edited.status_code == 200, edited.text
        assert (
            client.patch(
                "/api/collection/osm-way-20/card",
                json={
                    "version_id": current["id"],
                    "summary": "They retained this visit.",
                    "photo_id": photo["id"],
                },
            ).status_code
            == 409
        )
        image = client.get("/api/location-cards/" + edited.json()["id"] + "/export.png")
        with Image.open(io.BytesIO(image.content)) as result:
            assert result.size == (1080, 1350) and not result.getexif()
        review = client.patch(
            "/api/outcomes/" + experience["id"] + "/journal",
            json={"status": "accepted", "text": "Their edited place journal."},
        )
        assert review.status_code == 200, review.text
        assert client.get("/api/collection").json()["card_count"] == 1
    destination = tmp_path / "restored"
    restore(backup(registry[0].config), destination)
    with TestClient(
        create_app(Config(data_dir=destination)), base_url="http://127.0.0.1"
    ) as client:
        folder = client.get("/api/collection/osm-way-20").json()
        assert len(folder["card_versions"]) == 3
        assert folder["visits"][0]["journal"]["text"] == "Their edited place journal."
        assert (
            client.get(
                "/api/location-cards/" + folder["current_card"]["id"] + "/export.png"
            ).status_code
            == 200
        )


def test_failed_or_stale_generation_keeps_current_card(registry, monkeypatch):
    experience, photo, quest, value = prepared(registry)
    with TestClient(create_app(registry[0].config), base_url="http://127.0.0.1") as client:
        token(client)
        state = wait(
            client,
            client.post("/api/collection/osm-way-20/generate", json={"mode": "manual"}).json(),
        )
        previous = state["result"]["card_id"]

        def unsupported(*args, **kwargs):
            raise ModelFailure("No vision", "unsupported_capability")

        monkeypatch.setattr("nukkad.ollama.Ollama.generate", unsupported)
        failed = wait(client, client.post("/api/collection/osm-way-20/generate", json={}).json())
        assert (
            failed["status"] == "failed" and failed["failure_category"] == "unsupported_capability"
        )
        assert client.get("/api/collection/osm-way-20").json()["current_card"]["id"] == previous
        entered, release = threading.Event(), threading.Event()
        response = ai_response(photo)

        def delayed(*args, **kwargs):
            entered.set()
            assert release.wait(3)
            return response(*args, **kwargs)

        monkeypatch.setattr("nukkad.ollama.Ollama.generate", delayed)
        job = client.post("/api/collection/osm-way-20/generate", json={}).json()
        assert entered.wait(2)
        try:
            value.place_experiences[0].note = "I did not enjoy the noise."
            save_outcome(registry[1], quest, value)
        finally:
            release.set()
        assert wait(client, job)["status"] == "failed"
        folder = client.get("/api/collection/osm-way-20").json()
        assert folder["current_card"]["id"] == previous and folder["current_card"]["stale"]
        assert len(folder["card_versions"]) == 1


def test_photo_membership_removal_and_reached_counts(registry):
    experience, photo, quest, value = prepared(registry)
    with TestClient(create_app(registry[0].config), base_url="http://127.0.0.1") as client:
        token(client)
        assert (
            wait(
                client,
                client.post("/api/collection/osm-way-20/generate", json={"mode": "manual"}).json(),
            )["status"]
            == "complete"
        )
        assert (
            client.patch(
                "/api/collection/osm-way-20/card",
                json={
                    "version_id": client.get("/api/collection/osm-way-20").json()["current_card"][
                        "id"
                    ],
                    "summary": "They reported this stop.",
                    "photo_id": "someone-else",
                },
            ).status_code
            == 422
        )
        assert client.delete("/api/photos/" + photo["id"]).status_code == 200
        assert client.get("/api/collection/osm-way-20").json()["current_card"]["stale"]
        value.stops[0].status = "skipped"
        save_outcome(registry[1], quest, value)
        assert client.get("/api/collection").json()["card_count"] == 0
        assert registry[1].list("location_card_version")


def test_summary_requires_third_person_and_bounded_grounding():
    for summary in ("I enjoyed the trees.", "You enjoyed the trees.", "They enjoyed it. " * 20):
        with pytest.raises(ValueError):
            validate_summary(summary)
    with pytest.raises(ValueError):
        validate_summary("They felt calm beside 12 trees.", "I noticed outlines.", generated=True)


def test_card_job_cancellation_cannot_replace_current_version(registry, monkeypatch):
    _, photo, _, _ = prepared(registry)
    entered, release = threading.Event(), threading.Event()

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return CoverChoice(photo_id=photo["id"], reason="Selection: A clear view."), {}

    with TestClient(create_app(registry[0].config), base_url="http://127.0.0.1") as client:
        token(client)
        first = wait(
            client,
            client.post("/api/collection/osm-way-20/generate", json={"mode": "manual"}).json(),
        )
        old = first["result"]["card_id"]
        monkeypatch.setattr("nukkad.ollama.Ollama.generate", delayed)
        job = client.post("/api/collection/osm-way-20/generate", json={}).json()
        assert entered.wait(2)
        try:
            assert client.post("/api/jobs/" + job["id"] + "/cancel").json()["status"] == "cancelled"
        finally:
            release.set()
        deadline = time.monotonic() + 3
        while client.app.state.jobs.active and time.monotonic() < deadline:
            time.sleep(0.01)
        assert client.get("/api/collection/osm-way-20").json()["current_card"]["id"] == old
        assert len(registry[1].list("location_card_version")) == 1


def test_collection_merges_aliases_without_inflating_card_count(registry):
    first, _, _, _ = prepared(registry)
    second, _, _, _ = prepared(registry, "walk-2")
    with TestClient(create_app(registry[0].config), base_url="http://127.0.0.1") as client:
        token(client)
        assert (
            wait(
                client,
                client.post("/api/collection/osm-way-20/generate", json={"mode": "manual"}).json(),
            )["status"]
            == "complete"
        )
        registry[1].put("place_alias", "osm-way-20", {"canonical_id": "merged-place"})
        collection = client.get("/api/collection").json()
        assert collection["card_count"] == 1 and len(collection["folders"]) == 1
        assert collection["folders"][0]["visits"] == 2
        folder = client.get("/api/collection/merged-place").json()
        assert {item["id"] for item in folder["visits"]} == {first["id"], second["id"]}
        assert folder["current_card"]


def test_model_cannot_publish_an_unknown_cover_photo(registry, monkeypatch):
    prepared(registry)
    monkeypatch.setattr(
        "nukkad.ollama.Ollama.generate",
        lambda *args, **kwargs: (
            CoverChoice(photo_id="not-supplied", reason="Selection: A clear scene."),
            {},
        ),
    )
    with TestClient(create_app(registry[0].config), base_url="http://127.0.0.1") as client:
        token(client)
        state = wait(client, client.post("/api/collection/osm-way-20/generate", json={}).json())
        assert state["status"] == "failed"
        assert state["diagnostics"]["task"] == "location_cover"
        assert len(state["diagnostics"]["attempts"]) == 2
        assert client.get("/api/collection").json()["card_count"] == 0


def test_place_merge_during_generation_cannot_publish_to_stale_identity(registry, monkeypatch):
    _, photo, _, _ = prepared(registry)
    response = ai_response(photo)

    def merging(*args, **kwargs):
        registry[1].put("place_alias", "osm-way-20", {"canonical_id": "reviewed-place"})
        return response(*args, **kwargs)

    monkeypatch.setattr("nukkad.ollama.Ollama.generate", merging)
    with TestClient(create_app(registry[0].config), base_url="http://127.0.0.1") as client:
        token(client)
        state = wait(client, client.post("/api/collection/osm-way-20/generate", json={}).json())
        assert state["status"] == "failed" and "changed" in state["message"].lower()
        assert not registry[1].list("location_card_version")


def test_place_journal_edits_survive_card_regeneration(registry, monkeypatch):
    experience, photo, _, _ = prepared(registry)
    monkeypatch.setattr("nukkad.ollama.Ollama.generate", ai_response(photo))
    with TestClient(create_app(registry[0].config), base_url="http://127.0.0.1") as client:
        token(client)
        first = wait(client, client.post("/api/collection/osm-way-20/generate", json={}).json())
        assert first["status"] == "complete"
        journal = client.get("/api/collection/osm-way-20").json()["visits"][0]["journal"]
        assert (
            client.patch(
                "/api/outcomes/" + experience["id"] + "/journal",
                json={
                    "status": "accepted",
                    "text": "They kept their edited memory.",
                    "version_id": journal["version_id"],
                },
            ).status_code
            == 200
        )
        assert (
            wait(client, client.post("/api/collection/osm-way-20/generate", json={}).json())[
                "status"
            ]
            == "complete"
        )
        folder = client.get("/api/collection/osm-way-20").json()
        assert len(folder["card_versions"]) == 2
        assert any(
            item["text"] == "They kept their edited memory." and item["status"] == "accepted"
            for item in folder["visits"][0]["journal_versions"]
        )
        assert client.get("/api/collection").json()["card_count"] == 1


def test_card_visit_date_uses_reported_timezone(registry, monkeypatch):
    from PIL import ImageDraw

    from nukkad.location_cards import render_card

    _, photo, _, _ = prepared(registry)
    drawn = []
    original = ImageDraw.ImageDraw.text

    def record(draw, xy, text, *args, **kwargs):
        drawn.append(text)
        return original(draw, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record)
    render_card(
        registry[0].config,
        {
            "place_name": "Sample park",
            "visit_date": "2026-10-11T20:00:00+00:00",
            "timezone": "Asia/Kolkata",
            "summary": "They reported this visit.",
            "mode": "Manual template",
        },
        photo,
    )
    assert "REPORTED VISIT / 12 Oct 2026" in drawn
