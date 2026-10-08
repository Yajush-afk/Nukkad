from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from nukkad.air_quality import enforce
from nukkad.app import create_app
from nukkad.backups import backup, restore
from nukkad.planning import NoQuest, Settings


def test_aqi_policy_disabled_unknown_stale_and_high(registry):
    maps, store, snapshot, _, _ = registry
    assert enforce(store, snapshot, Settings()) == {"status": "disabled"}
    settings = Settings(air_quality_enabled=True, air_quality_threshold=100)
    moment = datetime.now(UTC)
    with pytest.raises(NoQuest, match="unknown"):
        enforce(store, snapshot, settings, moment)
    record = {"value": 80, "retrieved_at": moment.isoformat(), "valid_at": moment.isoformat()}
    store.put("air_quality", snapshot["id"], record)
    assert enforce(store, snapshot, settings, moment)["value"] == 80
    with pytest.raises(NoQuest, match="stale"):
        enforce(store, snapshot, settings, moment + timedelta(hours=4))
    record["value"] = 150
    store.put("air_quality", snapshot["id"], record)
    with pytest.raises(NoQuest, match="exceeds"):
        enforce(store, snapshot, settings, moment)


def test_host_origin_and_session_protection(registry):
    with TestClient(create_app(registry[0].config), base_url="http://127.0.0.1") as client:
        assert client.get("/", headers={"Host": "evil.example"}).status_code == 400
        assert client.post("/api/quests", json={}).status_code == 403
        token = client.get("/api/session").json()["token"]
        assert (
            client.put(
                "/api/profile",
                json={"interests": ["trees"]},
                headers={"X-Nukkad-Token": token, "Origin": "https://evil.example"},
            ).status_code
            == 403
        )
        assert (
            client.put(
                "/api/profile", json={"interests": ["trees"]}, headers={"X-Nukkad-Token": token}
            ).status_code
            == 200
        )


def test_backup_restores_graph_and_exact_notes_without_overwrite(registry, tmp_path):
    maps, store, snapshot, _, _ = registry
    store.put("outcome", "sample", {"note": " exact\n note "})
    archive = backup(maps.config)
    destination = tmp_path / "restored"
    restore(archive, destination)
    from nukkad.config import Config
    from nukkad.maps import Maps
    from nukkad.storage import Store

    restored = Store(destination)
    assert restored.get("outcome", "sample")["note"] == " exact\n note "
    assert Maps(Config(data_dir=destination), restored).graph().number_of_edges() == 4
    with pytest.raises(ValueError, match="new directory"):
        restore(archive, destination)
