import pytest
from test_maps import XML

from nukkad.maps import neighbourhood_query, parse_extract


def test_relation_only_park_imports_boundary_and_mapped_entrance(registry):
    _, _, _, area, source = registry
    source.write_text(
        XML.replace('<tag k="leisure" v="park"/><tag k="name" v="Sample park"/>', "").replace(
            "</osm>",
            '<relation id="30"><member type="way" ref="20" role="outer"/><tag k="type" v="multipolygon"/><tag k="leisure" v="park"/><tag k="name" v="Relation park"/></relation></osm>',
        )
    )
    _, places, geometry = parse_extract(source, area)
    place = next(item for item in places if item.id == "osm-relation-30")
    assert place.entrance_node == 2
    assert place.member_ids == ["osm-way-20"]
    assert place.geometry["type"] == "MultiPolygon"
    assert any(item["geometry"]["type"] == "MultiPolygon" for item in geometry["features"])
    assert 'relation["leisure"' in neighbourhood_query(area)


def test_incomplete_relation_preserves_previous_snapshot(registry):
    maps, store, old, area, source = registry
    source.write_text(
        XML.replace(
            "</osm>",
            '<relation id="30"><member type="way" ref="999" role="outer"/><tag k="type" v="multipolygon"/><tag k="leisure" v="park"/></relation></osm>',
        )
    )
    with pytest.raises(ValueError, match="missing a boundary member"):
        maps.acquire(area, source)
    assert store.get("area", "active")["snapshot_id"] == old["id"]


def test_structurally_identical_member_alias_preserves_identity(registry):
    maps, store, _, area, source = registry
    source.write_text(
        XML.replace(
            "</osm>",
            '<relation id="30"><member type="way" ref="20" role="outer"/><tag k="type" v="multipolygon"/><tag k="leisure" v="park"/><tag k="name" v="Sample park"/></relation></osm>',
        )
    )
    maps.acquire(area, source)
    assert store.get("place_alias", "osm-relation-30")["canonical_id"] == "osm-way-20"
    assert len([place for place in maps.places() if place.name == "Sample park"]) == 1
    assert next(place for place in maps.places() if place.name == "Sample park").id == "osm-way-20"


def test_reviewed_duplicate_merge_keeps_visits_and_denominator(registry):
    from fastapi.testclient import TestClient

    from nukkad.app import create_app

    maps, store, snapshot = registry[:3]
    with TestClient(create_app(maps.config), base_url="http://127.0.0.1") as client:
        client.headers["X-Nukkad-Token"] = client.get("/api/session").json()["token"]
        ids = []
        for lon in (77.361, 77.3611):
            response = client.post(
                "/api/places",
                json={
                    "name": "Checked corner",
                    "kind": "landmark",
                    "entrance": {"lat": 28.639, "lon": lon},
                    "public_access_confirmed": True,
                },
            )
            ids.append(response.json()["id"])
        store.put("outcome", "old", {"id": "old", "reached_ids": [ids[1]]})
        pair = client.get("/api/places/duplicates").json()[0]
        assert len([place for place in maps.places() if place.id in ids]) == 2
        response = client.patch(
            "/api/places/duplicates/" + pair["id"], json={"decision": "merge", "target_id": ids[0]}
        )
        assert response.status_code == 200, response.text
        assert client.get("/api/places/duplicates").json() == []
    merged = [place for place in maps.places() if place.name == "Checked corner"]
    assert len(merged) == 1 and merged[0].visited
    assert store.get("outcome", "old")["reached_ids"] == [ids[1]]
    assert (
        store.get("snapshot", snapshot["id"])["eligible_mapped_ids"]
        == snapshot["eligible_mapped_ids"]
    )


def test_fragmented_rings_holes_and_disconnected_components():
    from xml.etree import ElementTree

    from nukkad.domain import Point
    from nukkad.polygons import multipolygons

    coordinates = {
        1: (0, 0),
        2: (4, 0),
        3: (4, 4),
        4: (0, 4),
        5: (1, 1),
        6: (2, 1),
        7: (2, 2),
        8: (1, 2),
        9: (5, 0),
        10: (6, 0),
        11: (6, 1),
        12: (5, 1),
    }
    points = {key: Point(lon=x, lat=y) for key, (x, y) in coordinates.items()}
    ways = {20: [1, 2, 3], 21: [1, 4, 3], 22: [5, 6, 7, 8, 5], 23: [9, 10, 11, 12, 9]}
    xml = "<osm>" + "".join(
        f'<way id="{key}">' + "".join(f'<nd ref="{ref}"/>' for ref in refs) + "</way>"
        for key, refs in ways.items()
    )
    xml += (
        '<relation id="30">'
        + "".join(
            f'<member type="way" ref="{key}" role="{"inner" if key == 22 else "outer"}"/>'
            for key in ways
        )
        + '<tag k="type" v="multipolygon"/><tag k="leisure" v="park"/></relation></osm>'
    )
    shapes, _ = multipolygons(ElementTree.fromstring(xml), points)
    assert len(shapes["30"]["geometry"]["coordinates"]) == 2
    assert len(shapes["30"]["geometry"]["coordinates"][0]) == 2
