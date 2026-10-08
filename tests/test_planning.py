from datetime import UTC, datetime

import pytest

from nukkad.planning import NoQuest, Planner, QuestInput, Settings, baseline, pedestrian_graph


def planner(registry, hour=7):
    return Planner(registry[0], Settings(), lambda: datetime(2026, 10, 8, hour, tzinfo=UTC))


def test_complete_return_and_budget(registry):
    plan = planner(registry)
    candidates = plan.candidates(QuestInput(), [])
    result = plan.build(candidates, baseline(candidates, []), QuestInput())
    assert len(result["legs"]) == 2
    assert result["legs"][-1]["coordinates"][-1] == result["legs"][0]["coordinates"][0]
    assert result["meters"] == sum(leg["meters"] for leg in result["legs"])
    assert result["estimated_minutes"] >= 9
    assert result["estimated_minutes"] <= 30


def test_night_and_foreign_ids_rejected(registry):
    plan = planner(registry, 18)
    candidates = plan.candidates(QuestInput(), [])
    with pytest.raises(NoQuest, match="daylight"):
        plan.build(candidates, baseline(candidates, []), QuestInput())
    with pytest.raises(ValueError, match="IDs"):
        plan.build(candidates, ["invented"], QuestInput())


def test_private_connection_excluded(registry):
    graph = registry[0].graph()
    for _, _, data in graph.edges(data=True):
        data["access"] = "private"
    assert pedestrian_graph(graph).number_of_edges() == 0


def test_unconfirmed_start_rejected(registry):
    maps, store, snapshot, _, _ = registry
    snapshot["area"]["public_start_confirmed"] = False
    store.put("snapshot", snapshot["id"], snapshot)
    with pytest.raises(NoQuest, match="confirm"):
        Planner(maps, Settings())


def test_no_return_path_excludes_candidate(registry):
    plan = planner(registry)
    plan.graph.remove_edges_from(list(plan.graph.out_edges(2, keys=True)))
    assert plan.candidates(QuestInput(), []) == []
    with pytest.raises(NoQuest, match="return"):
        plan.build([], [], QuestInput())
