import time

import pytest
from fastapi.testclient import TestClient

from nukkad.app import create_app
from nukkad.config import Config
from nukkad.demo import prepare_demo
from nukkad.maps import Maps
from nukkad.places import seek_features
from nukkad.storage import Store


def test_demo_is_isolated_and_has_no_fabricated_history(tmp_path, monkeypatch):
    original = tmp_path / "personal"
    original.mkdir()
    sentinel = original / "keep.txt"
    sentinel.write_text("personal data")
    monkeypatch.setenv("NUKKAD_DATA_DIR", str(original))
    destination = tmp_path / "demo"
    assert prepare_demo(destination, "gemma4:e2b") == destination
    store = Store(destination)
    registry = Maps(Config(data_dir=destination), store)
    assert registry.snapshot()["area"]["name"].startswith("Synthetic demo")
    assert registry.snapshot()["synthetic"] is True
    assert len(registry.places()) == 8
    assert sum(bool(seek_features(place)) for place in registry.places()) == 2
    for kind in ("quest", "outcome", "journal", "interest"):
        assert store.list(kind) == []
    assert sentinel.read_text() == "personal data"
    with pytest.raises(ValueError, match="new directory"):
        prepare_demo(destination, "gemma4:e2b")


def test_synthetic_source_provenance_survives_a_fresh_import(tmp_path):
    destination = prepare_demo(tmp_path / "demo", "gemma4:e2b")
    store = Store(destination)
    registry = Maps(Config(data_dir=destination), store)
    original = registry.snapshot()
    from nukkad.places import AreaInput

    area = AreaInput.model_validate({**original["area"], "name": "Renamed demo"})
    imported = registry.acquire(area, destination / "synthetic.osm")
    assert imported["synthetic"] is True
    assert imported["source"].startswith("Synthetic fixture")
    assert imported["id"] != original["id"]
    assert store.get("snapshot", original["id"])["synthetic"] is True


def test_reusing_legacy_demo_extract_retains_snapshot_provenance(tmp_path):
    destination = prepare_demo(tmp_path / "demo", "gemma4:e2b")
    store = Store(destination)
    snapshot = Maps(Config(data_dir=destination), store).snapshot()
    # Older locally prepared demos have a snapshot marker but no XML root marker.
    source = destination / "snapshots" / snapshot["id"] / "source.osm"
    source.write_text(source.read_text().replace(' nukkad_synthetic="true"', ""))
    with TestClient(
        create_app(Config(data_dir=destination)), base_url="http://127.0.0.1"
    ) as client:
        client.headers["X-Nukkad-Token"] = client.get("/api/session").json()["token"]
        response = client.post(
            "/api/areas/reuse", json={**snapshot["area"], "name": "Renamed demo"}
        )
        assert response.status_code == 200
        key = response.json()["id"]
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            job = client.get("/api/jobs/" + key).json()
            if job["status"] == "complete":
                break
            assert job["status"] not in {"failed", "cancelled"}, job
            time.sleep(0.01)
        assert job["status"] == "complete"
        refreshed = store.get("snapshot", job["result"]["snapshot_id"])
        assert refreshed["synthetic"] is True
        assert refreshed["source"].startswith("Synthetic fixture")
