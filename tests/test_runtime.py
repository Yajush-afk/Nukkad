import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from nukkad.app import create_app
from nukkad.config import Config
from nukkad.domain import Point, validate_ids


def test_invalid_coordinates_and_nonfinite_values():
    for value in (float("nan"), float("inf"), 91):
        with pytest.raises(ValidationError):
            Point(lat=value, lon=77)


def test_ids_must_have_exact_membership_without_duplicates():
    validate_ids(["b", "a"], ["a", "b"])
    for values in (["a", "a"], ["a", "c"], ["a"]):
        with pytest.raises(ValueError):
            validate_ids(values, ["a", "b"])


def test_readiness_handles_unavailable_model(tmp_path, monkeypatch):
    def unavailable(self):
        raise RuntimeError("offline")

    monkeypatch.setattr("nukkad.ollama.Ollama.models", unavailable)
    with TestClient(create_app(Config(data_dir=tmp_path)), base_url="http://127.0.0.1") as client:
        response = client.get("/api/readiness")
    assert response.status_code == 200
    assert response.json()["model_status"] == "unavailable"


def test_expired_generation_never_contacts_runtime(monkeypatch):
    import time
    from nukkad.ollama import ModelFailure, Ollama
    from nukkad.domain import Ranking

    model = Ollama(Config())
    monkeypatch.setattr(
        model, "models", lambda: pytest.fail("Inventory must not run after deadline")
    )
    with pytest.raises(ModelFailure, match="deadline"):
        model.generate(Ranking, "", time.monotonic() - 1)


def test_cloud_selection_retains_truthful_journal_fallback():
    import time
    from nukkad.journals import generate_journal
    from nukkad.ollama import Ollama

    result = generate_journal(
        {"note": "I stayed home."}, Ollama(Config(model="example:cloud")), time.monotonic() + 1
    )
    assert result["mode"] == "extractive fallback"
    assert result["metrics"]["attempts"][0]["category"] == "unsupported_model"
