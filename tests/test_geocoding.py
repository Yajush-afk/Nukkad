import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from nukkad import geocoding
from nukkad.app import create_app
from nukkad.config import Config
from nukkad.storage import Store

MATCH = {
    "name": "Sample place",
    "display_name": "Sample place, Sample city, India",
    "lat": "28.6394",
    "lon": "77.3606",
}


@pytest.fixture
def geocoder(tmp_path, monkeypatch):
    config = Config(data_dir=tmp_path)
    config.prepare()
    store = Store(tmp_path)
    monkeypatch.delenv("NUKKAD_GEOCODING_URL", raising=False)
    monkeypatch.setattr(geocoding, "_next_request", 0.0)
    monkeypatch.setattr(geocoding, "_lock", threading.Lock())
    real_client = httpx.Client
    calls = []

    def install(handler):
        def capture(request):
            calls.append(request)
            return handler(request)

        monkeypatch.setattr(
            geocoding.httpx,
            "Client",
            lambda **kw: real_client(transport=httpx.MockTransport(capture), **kw),
        )

    return config, store, calls, install


def test_search_normalizes_validates_and_caches_offline(geocoder):
    _, store, calls, install = geocoder
    install(lambda request: httpx.Response(200, json=[MATCH, MATCH, {**MATCH, "lat": "nan"}]))
    first = geocoding.search(store, "  Sample   city  ")
    assert first["matches"] == [
        {
            "name": MATCH["name"],
            "label": MATCH["display_name"],
            "point": {"lat": 28.6394, "lon": 77.3606},
        }
    ]
    assert not first["cached"]
    assert calls[0].url.params["q"] == "Sample city"
    assert calls[0].headers["User-Agent"] == geocoding.USER_AGENT
    install(lambda request: (_ for _ in ()).throw(httpx.ConnectError("offline", request=request)))
    assert geocoding.search(store, "sample city")["cached"]
    assert len(calls) == 1
    cached = store.list("location_search")[0]
    assert "query" not in cached
    assert cached["expires_at"] > time.time()


def test_empty_result_is_cached_without_guessing(geocoder):
    _, store, calls, install = geocoder
    install(lambda request: httpx.Response(200, json=[]))
    assert geocoding.search(store, "Unknown building")["matches"] == []
    assert geocoding.search(store, "Unknown building")["cached"]
    assert len(calls) == 1


@pytest.mark.parametrize("payload", [{"error": "failed"}, [{**MATCH, "lon": "181"}]])
def test_bad_responses_do_not_poison_cache(geocoder, payload):
    _, store, _, install = geocoder
    install(lambda request: httpx.Response(200, json=payload))
    with pytest.raises(geocoding.SearchUnavailable):
        geocoding.search(store, "Sample city")
    assert store.list("location_search") == []


def test_rate_limit_cooldown_does_not_retry_provider(geocoder):
    _, store, calls, install = geocoder
    install(lambda request: httpx.Response(429))
    with pytest.raises(geocoding.SearchUnavailable, match="rate-limited") as limited:
        geocoding.search(store, "Sample city")
    assert limited.value.status == 429
    with pytest.raises(geocoding.SearchUnavailable, match="cooling down"):
        geocoding.search(store, "Different city")
    assert len(calls) == 1


def test_concurrent_searches_share_one_process_gate(geocoder):
    _, store, calls, install = geocoder
    install(lambda request: httpx.Response(200, json=[MATCH]))
    with geocoding._lock, pytest.raises(geocoding.SearchUnavailable, match="already running"):
        geocoding.search(store, "Sample city")
    assert calls == []


def test_request_starts_are_spaced(geocoder, monkeypatch):
    _, store, calls, install = geocoder
    clock = [10.0]
    monkeypatch.setattr(geocoding.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        geocoding.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    )
    starts = []

    def respond(request):
        starts.append(clock[0])
        return httpx.Response(200, json=[MATCH])

    install(respond)
    geocoding.search(store, "First city")
    geocoding.search(store, "Second city")
    assert starts[1] - starts[0] >= 1
    assert len(calls) == 2


def test_local_route_rejects_unapproved_queries_and_keeps_active_area(geocoder):
    config, store, calls, install = geocoder
    install(lambda request: httpx.Response(200, json=[MATCH]))
    store.put("area", "active", {"id": "existing"})
    with TestClient(create_app(config), base_url="http://127.0.0.1") as client:
        assert (
            client.post("/api/locations/search", json={"query": "Sample city"}).status_code == 403
        )
        token = client.get("/api/session").json()["token"]
        headers = {"X-Nukkad-Token": token}
        assert (
            client.post("/api/locations/search", json={"query": "   "}, headers=headers).status_code
            == 422
        )
        result = client.post(
            "/api/locations/search", json={"query": "Sample city"}, headers=headers
        )
        assert result.status_code == 200
        assert result.json()["matches"][0]["point"]["lat"] == 28.6394
    assert store.get("area", "active") == {"id": "existing"}
    assert len(calls) == 1


def test_provider_can_change_without_editing_code(geocoder, monkeypatch):
    _, store, calls, install = geocoder
    install(lambda request: httpx.Response(200, json=[MATCH]))
    monkeypatch.setenv("NUKKAD_GEOCODING_URL", "http://127.0.0.1:8080/search")
    geocoding.search(store, "Sample city")
    assert str(calls[0].url).startswith("http://127.0.0.1:8080/search?")
    monkeypatch.setenv("NUKKAD_GEOCODING_URL", "https://example.invalid/search")
    assert not geocoding.search(store, "Sample city")["cached"]
    assert len(calls) == 2


@pytest.mark.parametrize(
    "url",
    [
        "http://example.invalid/search",
        "https://user:secret@example.invalid/search",
        "https://example.invalid/search?key=secret",
        "https://[broken/search",
        "https://example.invalid:broken/search",
    ],
)
def test_invalid_provider_configuration_makes_no_request(geocoder, monkeypatch, url):
    _, store, calls, install = geocoder
    install(lambda request: httpx.Response(200, json=[MATCH]))
    monkeypatch.setenv("NUKKAD_GEOCODING_URL", url)
    with pytest.raises(geocoding.SearchUnavailable, match="valid Nominatim endpoint"):
        geocoding.search(store, "Sample city")
    assert calls == []
