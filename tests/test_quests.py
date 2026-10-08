import time
from datetime import UTC, datetime

import pytest

from nukkad.domain import Ranking
from nukkad.ollama import ModelFailure
from nukkad.planning import Planner, QuestInput, Settings
from nukkad.quests import generate, validate_prose, validated_task


class MissingModel:
    def generate(self, *args):
        raise ModelFailure("Unavailable")


def test_separate_fallbacks_keep_complete_route(registry, monkeypatch):
    import nukkad.quests as quests

    original = Planner
    monkeypatch.setattr(
        quests,
        "Planner",
        lambda maps, settings: original(
            maps, settings, lambda: datetime(2026, 10, 8, 7, tzinfo=UTC)
        ),
    )
    maps, store, _, _, _ = registry
    result = generate(
        maps, store, maps.config, Settings(), QuestInput(), lambda _: None, MissingModel()
    )
    assert result["ranking_mode"] == "deterministic fallback"
    assert result["prose_mode"] == "template fallback"
    assert set(result["prompts"]) == {place["id"] for place in result["stops"]}
    assert len(result["legs"]) == len(result["stops"]) + 1


def test_corrective_retry_rejects_duplicate_ids():
    class Duplicate:
        calls = 0

        def generate(self, *args):
            self.calls += 1
            return Ranking(
                places=[{"id": "a", "reason": "nearby"}, {"id": "a", "reason": "nearby"}]
            ), {}

    model = Duplicate()
    with pytest.raises(ModelFailure):
        validated_task(
            model, Ranking, "places", ["a", "b"], "Rank", time.monotonic() + 10, lambda _: None
        )
    assert model.calls == 2


def test_prose_rejects_invented_features_and_numbers():
    validate_prose("Notice the shapes visible from your public stopping point.")
    for text in [
        "Notice the ancient fountain built in 1850.",
        "This park is safe.",
        "Look for a kingfisher.",
    ]:
        with pytest.raises(ValueError):
            validate_prose(text)


def test_general_observation_vocabulary_accepts_real_model_examples():
    validate_prose("Notice the sounds present in this space.")
    validate_prose("Observe the shades of colour in this area.")
