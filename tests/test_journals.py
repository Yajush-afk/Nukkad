import time

import pytest
from fastapi.testclient import TestClient

from nukkad.app import create_app
from nukkad.journals import WrittenJournal, generate_journal, validate_written
from nukkad.ollama import ModelFailure


def draft(text="They enjoyed tree shapes.", quote="I enjoyed tree shapes."):
    return WrittenJournal(passages=[{"text": text, "quote": quote}])


def test_written_journal_requires_third_person_and_source_evidence():
    source = {"note": "I enjoyed tree shapes.", "status": "completed"}
    validate_written(draft(), source)
    for text, quote in (
        ("I enjoyed tree shapes.", source["note"]),
        ("They felt calm.", source["note"]),
        ("They counted 50 trees.", source["note"]),
        ("They enjoyed it.", "A made-up quote"),
    ):
        with pytest.raises(ValueError):
            validate_written(draft(text, quote), source)
    with pytest.raises(ValueError):
        validate_written(
            draft("They enjoyed trees.", "I did not enjoy trees."),
            {"note": "I did not enjoy trees."},
        )


def test_failed_journal_preserves_truthful_extract():
    class Missing:
        def generate(self, *args):
            raise ModelFailure("Unavailable")

    result = generate_journal(
        {"note": "I never left home.", "status": "not_taken"}, Missing(), time.monotonic() + 1
    )
    assert result["text"] == "I never left home."
    assert result["mode"] == "extractive fallback" and result["interests"] == []


def test_journal_versions_and_interest_review_are_separate(registry, monkeypatch):
    maps, store = registry[:2]
    source = {
        "id": "visit",
        "note": "I enjoyed tree shapes.",
        "original_note": "I enjoyed tree shapes.",
        "status": "completed",
        "updated_at": "revision-1",
    }
    store.put("outcome", "visit", source)

    def response(*args):
        return WrittenJournal(
            passages=[{"text": "They enjoyed tree shapes.", "quote": source["note"]}],
            interests=[{"theme": "trees", "quote": source["note"]}],
        ), {}

    monkeypatch.setattr("nukkad.ollama.Ollama.generate", response)
    with TestClient(create_app(maps.config), base_url="http://127.0.0.1") as client:
        client.headers["X-Nukkad-Token"] = client.get("/api/session").json()["token"]
        for _ in range(2):
            job = client.post("/api/outcomes/visit/reflect").json()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                state = client.get("/api/jobs/" + job["id"]).json()
                if state["status"] == "complete":
                    break
                assert state["status"] != "failed", state
                time.sleep(0.01)
            assert state["status"] == "complete"
            edited = client.patch(
                "/api/outcomes/visit/journal",
                json={"status": "accepted", "text": "Their edited account."},
            )
            assert edited.status_code == 200
        versions = client.get("/api/outcomes/visit/journal/versions").json()
        assert any(item["text"] == "Their edited account." for item in versions)
        assert all(item["status"] != "accepted" for item in client.get("/api/interests").json())
    assert store.get("outcome", "visit") == source


def test_journal_generation_cannot_overwrite_review_during_inference(registry, monkeypatch):
    import threading

    store = registry[1]
    source = {"id": "visit", "note": "I enjoyed tree shapes.", "status": "completed"}
    store.put("outcome", "visit", source)
    old = {
        "id": "visit",
        "text": "Earlier draft",
        "source_note": source["note"],
        "status": "pending",
    }
    store.put("journal", "visit", old)
    entered, release = threading.Event(), threading.Event()

    def response(*args):
        entered.set()
        assert release.wait(3)
        return draft(), {}

    monkeypatch.setattr("nukkad.ollama.Ollama.generate", response)
    with TestClient(create_app(registry[0].config), base_url="http://127.0.0.1") as client:
        client.headers["X-Nukkad-Token"] = client.get("/api/session").json()["token"]
        job = client.post("/api/outcomes/visit/reflect").json()
        assert entered.wait(2)
        try:
            assert (
                client.patch(
                    "/api/outcomes/visit/journal",
                    json={"status": "accepted", "text": "Their edited account."},
                ).status_code
                == 200
            )
        finally:
            release.set()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = client.get("/api/jobs/" + job["id"]).json()
            if state["status"] == "failed":
                break
            time.sleep(0.01)
        assert state["status"] == "failed"
        assert store.get("journal", "visit")["text"] == "Their edited account."
