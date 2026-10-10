import threading
from xml.etree.ElementTree import ParseError

import pytest

from nukkad.config import Config
from nukkad.jobs import Jobs, Result
from nukkad.storage import Store

XML = """<osm version="0.6">
<node id="1" lat="28.639" lon="77.360"/>
<node id="2" lat="28.639" lon="77.361"><tag k="entrance" v="yes"/></node>
<node id="3" lat="28.639" lon="77.362"/>
<node id="4" lat="28.640" lon="77.361"/>
<node id="5" lat="28.640" lon="77.362"/>
<way id="10"><nd ref="1"/><nd ref="2"/><nd ref="3"/><tag k="highway" v="residential"/><tag k="name" v="Sample street"/></way>
<way id="20"><nd ref="2"/><nd ref="4"/><nd ref="5"/><nd ref="2"/><tag k="leisure" v="park"/><tag k="name" v="Sample park"/></way>
<way id="21"><nd ref="2"/><nd ref="4"/><nd ref="5"/><nd ref="2"/><tag k="leisure" v="park"/><tag k="access" v="private"/></way>
</osm>"""


def test_import_preserves_provenance_and_excludes_private_places(registry):
    maps, _, snapshot, _, _ = registry
    assert snapshot["eligible_mapped_ids"] == ["osm-way-20"]
    assert maps.graph(snapshot).number_of_edges() == 4
    assert maps.places()[0].access == "unknown"
    assert maps.places()[0].verification == "unverified"


def test_bad_refresh_preserves_active_snapshot_and_old_denominator(registry):
    maps, store, snapshot, area, source = registry
    source.write_text("<osm>")
    with pytest.raises(ParseError):
        maps.acquire(area, source)
    assert store.get("area", "active")["snapshot_id"] == snapshot["id"]
    assert store.get("snapshot", snapshot["id"])["eligible_mapped_ids"] == ["osm-way-20"]


def test_new_private_tags_override_previous_confirmation(registry):
    maps, store, snapshot, _, _ = registry
    place = maps.places()[0].model_dump()
    place.update(verification="verified", access="confirmed")
    store.put("place", place["id"], place)
    snapshot["places"][0]["tags"]["access"] = "private"
    store.put("snapshot", snapshot["id"], snapshot)
    assert maps.places()[0].valid is False


def test_cancellation_prevents_late_publication(tmp_path):
    Config(data_dir=tmp_path).prepare()
    store = Store(tmp_path)
    jobs = Jobs(store)
    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    def action(stage):
        started.set()
        release.wait(2)
        return Result({"ok": True}, [("quest", "late", {"id": "late"})])

    job = jobs.submit("Test", action)
    assert started.wait(2)
    jobs.cancel(job["id"])
    release.set()
    jobs.executor.submit(finished.set)
    assert finished.wait(2)
    assert store.get("quest", "late") is None
    assert store.get("job", job["id"])["status"] == "cancelled"
    jobs.close()


def test_unconfirmed_search_centre_can_save_map_without_inventing_entrance(registry):
    from nukkad.planning import NoQuest, Planner, Settings

    maps, store, _, area, source = registry
    centre = area.model_copy(
        update={
            "start": area.start.model_copy(update={"lat": 28.641}),
            "public_start_confirmed": False,
        }
    )
    saved = maps.acquire(centre, source)
    assert saved["start_node"] is None
    assert saved["eligible_mapped_ids"] == []
    with pytest.raises(NoQuest, match="confirm a public"):
        Planner(maps, Settings())
    with pytest.raises(ValueError, match="50 metres"):
        maps.acquire(centre.model_copy(update={"public_start_confirmed": True}), source)
    assert store.get("area", "active")["snapshot_id"] == saved["id"]
