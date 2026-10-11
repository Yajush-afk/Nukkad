import re
from urllib.parse import parse_qs

import httpx
import pytest
from test_maps import XML


def install_transport(monkeypatch, handler):
    client = httpx.Client
    monkeypatch.setattr(
        "nukkad.maps.httpx.Client",
        lambda **kwargs: client(transport=httpx.MockTransport(handler), **kwargs),
    )


def test_dense_area_uses_a_selective_query_without_shrinking_radius(
    registry, monkeypatch, tmp_path
):
    maps, _, _, area, _ = registry
    area = area.model_copy(update={"radius_meters": 2000})
    calls = []

    def provider(request):
        body = request.content.decode()
        calls.append((request.url.host, body))
        # Reproduces the real failure: bulk map requests time out on Overpass
        # and the main editing API rejects the dense area at its node limit.
        if request.url.host == "api.openstreetmap.org":
            return httpx.Response(400, text="You requested too many nodes (limit is 50000)")
        if "%5B%22highway%22%5D" not in body:
            return httpx.Response(504)
        return httpx.Response(200, text=XML)

    install_transport(monkeypatch, provider)
    target = tmp_path / "download.osm"
    assert maps.download(area, target).startswith("OpenStreetMap via Overpass")
    assert target.read_text() == XML
    assert len(calls) == 1
    query = parse_qs(calls[0][1])["data"][0]
    bounds = re.search(r'way\["highway"\]\(([^)]+)\)', query)
    assert bounds is not None
    south, west, north, east = map(float, bounds.group(1).split(","))
    assert north - south == pytest.approx(2 * (2000 + 700) / 111320)
    assert east > west
    assert "(._;>;);out body;" in query
    assert "out meta" not in query
    assert area.radius_meters == 2000


def test_overloaded_primary_uses_an_independent_overpass_provider(registry, monkeypatch, tmp_path):
    maps, _, _, area, _ = registry
    calls = []

    def provider(request):
        calls.append(request.url.host)
        if request.url.host == "overpass-api.de":
            return httpx.Response(504)
        assert request.url.host == "overpass.private.coffee"
        return httpx.Response(200, text=XML)

    install_transport(monkeypatch, provider)
    assert "Private.coffee" in maps.download(area, tmp_path / "download.osm")
    assert calls == ["overpass-api.de", "overpass.private.coffee"]


def test_failures_keep_provider_statuses_without_leaking_query_coordinates(
    registry, monkeypatch, tmp_path
):
    maps, store, snapshot, area, _ = registry
    install_transport(
        monkeypatch,
        lambda request: httpx.Response(504 if request.url.host == "overpass-api.de" else 429),
    )
    with pytest.raises(ValueError) as caught:
        maps.download(area, tmp_path / "failed.osm")
    message = str(caught.value)
    assert "504" in message and "429" in message
    assert "rate limit" in message.lower()
    assert str(area.start.lat) not in message and str(area.start.lon) not in message
    assert store.get("area", "active")["snapshot_id"] == snapshot["id"]


@pytest.mark.parametrize(
    "body", ["<html/>", "<osm><remark>runtime error: Query timed out</remark></osm>", "<osm>"]
)
def test_invalid_or_partial_success_uses_backup(registry, monkeypatch, tmp_path, body):
    maps, _, _, area, _ = registry

    def provider(request):
        return httpx.Response(200, text=body if request.url.host == "overpass-api.de" else XML)

    install_transport(monkeypatch, provider)
    assert "Private.coffee" in maps.download(area, tmp_path / "download.osm")


def test_busy_providers_recover_with_smaller_complete_tiles(registry, monkeypatch, tmp_path):
    maps, _, _, area, _ = registry
    calls = []

    def provider(request):
        query = parse_qs(request.content.decode())["data"][0]
        calls.append(query)
        if len(calls) <= 2:
            return httpx.Response(504 if len(calls) == 1 else 500)
        assert "out body;" in query and "out meta;" not in query
        return httpx.Response(200, text=XML)

    install_transport(monkeypatch, provider)
    path = tmp_path / "tiled.osm"
    assert "smaller sections" in maps.download(area, path)
    assert len(calls) == 6
    from defusedxml import ElementTree

    root = ElementTree.parse(path).getroot()
    assert len(root.findall("node")) == len(ElementTree.fromstring(XML).findall("node"))
    full = re.search(r'way\["highway"\]\(([^)]+)\)', calls[0]).group(1)
    tiled = [re.search(r'way\["highway"\]\(([^)]+)\)', q).group(1) for q in calls[2:]]
    assert len(set(tiled)) == 4 and full not in tiled
    acquired = maps.acquire(area, path, activate=False)
    assert acquired["graph_fingerprint"] and acquired["places"]


def test_failed_tile_keeps_previous_target_and_active_snapshot(registry, monkeypatch, tmp_path):
    maps, store, snapshot, area, _ = registry
    calls = []

    def provider(request):
        calls.append(request.url.host)
        if len(calls) == 3:
            return httpx.Response(200, text=XML)
        return httpx.Response(504)

    install_transport(monkeypatch, provider)
    target = tmp_path / "existing.osm"
    target.write_text("existing complete extract")
    with pytest.raises(ValueError):
        maps.download(area, target)
    assert target.read_text() == "existing complete extract"
    assert store.get("area", "active")["snapshot_id"] == snapshot["id"]
    assert len(calls) == 4


def test_rate_limits_are_not_retried_and_cancel_stops_sectional_requests(
    registry, monkeypatch, tmp_path
):
    maps, _, _, area, _ = registry
    calls = []
    rate_limited = True

    def limited(request):
        calls.append(request.url.host)
        return httpx.Response(429 if rate_limited else 504)

    install_transport(monkeypatch, limited)
    with pytest.raises(ValueError, match="rate limit"):
        maps.download(area, tmp_path / "limited.osm")
    assert len(calls) == 2
    from nukkad.jobs import Cancelled

    calls.clear()
    rate_limited = False

    def progress(message):
        if "smaller section" in message:
            raise Cancelled("Task cancelled")

    with pytest.raises(Cancelled):
        maps.download(area, tmp_path / "cancelled.osm", progress)
    assert len(calls) == 2 and not (tmp_path / "cancelled.osm").exists()
    assert not list(tmp_path.glob(".download-*"))


def test_sections_reject_inconsistent_entities_and_missing_references(tmp_path):
    from nukkad.maps import merge_sections

    first = tmp_path / "first.osm"
    second = tmp_path / "second.osm"
    target = tmp_path / "merged.osm"
    first.write_text(XML)
    second.write_text(XML.replace('lat="28.639"', 'lat="28.638"', 1))
    with pytest.raises(ValueError, match="changed between sections"):
        merge_sections([first, second], target)
    first.write_text('<osm><way id="1"><nd ref="missing"/></way></osm>')
    with pytest.raises(ValueError, match="missing referenced geometry"):
        merge_sections([first], target)
    assert not target.exists()
