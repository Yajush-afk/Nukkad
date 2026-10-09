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
    assert area.radius_meters == 500


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
