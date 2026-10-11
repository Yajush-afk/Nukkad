import networkx as nx
import pytest
from shapely.geometry import LineString

from nukkad.domain import Point
from nukkad.maps import nearest_node
from nukkad.planning import pedestrian_graph


def street(reverse=True):
    graph = nx.MultiDiGraph(crs="epsg:4326")
    graph.add_node(1, x=77.360, y=28.639)
    graph.add_node(2, x=77.364, y=28.639)
    graph.add_edge(1, 2, length=400, highway="residential", osmid=10)
    if reverse:
        graph.add_edge(2, 1, length=400, highway="residential", osmid=10)
    return graph


def test_sparse_street_midpoint_and_multiple_snaps_keep_return_paths():
    graph = street()
    first = nearest_node(graph, Point(lat=28.639, lon=77.362))
    second = nearest_node(graph, Point(lat=28.639, lon=77.363))
    assert first not in (1, 2)
    assert nx.shortest_path_length(graph, first, second, weight="length") == pytest.approx(
        100, abs=0.1
    )
    assert nx.shortest_path_length(graph, second, first, weight="length") == pytest.approx(
        100, abs=0.1
    )
    assert nearest_node(graph, Point(lat=28.639, lon=77.360)) == 1


def test_use_sidepath_carriageway_is_excluded():
    graph = street()
    for _, _, data in graph.edges(data=True):
        data["foot"] = "use_sidepath"
    assert pedestrian_graph(graph).number_of_edges() == 0
    with pytest.raises(ValueError):
        nearest_node(pedestrian_graph(graph), Point(lat=28.639, lon=77.362))


def test_curved_one_way_retains_geometry_and_direction():
    graph = street(reverse=False)
    graph[1][2][0]["geometry"] = LineString([(77.360, 28.639), (77.362, 28.640), (77.364, 28.639)])
    node = nearest_node(graph, Point(lat=28.640, lon=77.362))
    assert nx.has_path(graph, 1, node) and nx.has_path(graph, node, 2)
    assert not nx.has_path(graph, node, 1)
    assert graph.nodes[node]["y"] == pytest.approx(28.640, abs=1e-6)
    assert sum(data["length"] for _, _, data in graph.edges(data=True)) == pytest.approx(400)


def test_segment_start_and_custom_pin_survive_reload_without_rewriting_graph(registry):
    from fastapi.testclient import TestClient

    from nukkad.app import create_app
    from nukkad.planning import Planner, QuestInput, Settings

    maps, store, _, area, source = registry
    # Stretch the fixture street so its middle is farther than 50 m from any vertex.
    source.write_text(source.read_text().replace('lon="77.361"', 'lon="77.364"'))
    area = area.model_copy(update={"start": Point(lat=28.639, lon=77.362), "radius_meters": 1000})
    snapshot = maps.acquire(area, source)
    graph_path = maps.config.data_dir / "snapshots" / snapshot["id"] / "walking.graphml"
    before = graph_path.read_bytes()
    assert snapshot["start_snap"]["distance_meters"] < 1
    with TestClient(create_app(maps.config), base_url="http://127.0.0.1") as client:
        client.headers["X-Nukkad-Token"] = client.get("/api/session").json()["token"]
        response = client.post(
            "/api/places",
            json={
                "name": "Checked corner",
                "kind": "landmark",
                "entrance": {"lat": 28.639, "lon": 77.363},
                "public_access_confirmed": True,
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["snap"]["original"]["lon"] == 77.363
    planner = Planner(maps, Settings(daylight_required=False))
    candidates = planner.candidates(QuestInput(), [])
    assert response.json()["id"] in {place.id for place in candidates}
    assert graph_path.read_bytes() == before
    assert (
        store.get("snapshot", snapshot["id"])["graph_fingerprint"] == snapshot["graph_fingerprint"]
    )
