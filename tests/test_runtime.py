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
    with TestClient(create_app(Config(data_dir=tmp_path))) as client:
        response = client.get("/api/readiness")
    assert response.status_code == 200
    assert response.json()["model_status"] == "unavailable"
