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
