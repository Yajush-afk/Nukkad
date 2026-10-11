import time

import pytest
from fastapi.testclient import TestClient

from nukkad.app import create_app
from nukkad.domain import Ranking
from nukkad.ollama import ModelFailure
from nukkad.tasks import run_task


def test_readiness_checks_saved_graph_and_invalidates_cache(registry, monkeypatch):
    maps, _, snapshot = registry[:3]
    monkeypatch.setattr("nukkad.ollama.Ollama.models", lambda self: [{"name": self.config.model}])
    monkeypatch.setattr(
        "nukkad.ollama.Ollama.information", lambda self: {"capabilities": ["completion", "vision"]}
    )
    with TestClient(create_app(maps.config), base_url="http://127.0.0.1") as client:
        first = client.get("/api/readiness").json()
        assert first["deterministic_ready"] and first["local_ai_ready"]
        assert "vision" in first["model_capabilities"]
        path = maps.config.data_dir / "snapshots" / snapshot["id"] / "walking.graphml"
        path.write_bytes(b"damaged")
        damaged = client.get("/api/readiness").json()
        assert damaged["checks"]["map"]["status"] == "damaged"
        assert not damaged["deterministic_ready"]
        assert client.get("/api/quests").status_code == 200


def test_cloud_inventory_not_reported_ready(registry, monkeypatch):
    monkeypatch.setattr(
        "nukkad.ollama.Ollama.models",
        lambda self: [{"name": self.config.model, "remote_host": "example"}],
    )
    with TestClient(create_app(registry[0].config), base_url="http://127.0.0.1") as client:
        result = client.get("/api/readiness").json()
    assert result["model_status"] == "unsupported"
    assert not result["local_ai_ready"]


def test_failed_attempt_diagnostics_do_not_include_prompt_or_error_content():
    class Broken:
        def generate(self, *args):
            raise ModelFailure("Private source words", "timeout")

    with pytest.raises(ModelFailure) as captured:
        run_task(
            Broken(),
            Ranking,
            "Sensitive note",
            time.monotonic() + 10,
            lambda value: None,
            task="ranking",
        )
    diagnostics = captured.value.diagnostics
    assert len(diagnostics["attempts"]) == 2
    assert all(attempt["category"] == "timeout" for attempt in diagnostics["attempts"])
    assert "Sensitive" not in str(diagnostics) and "Private" not in str(diagnostics)
