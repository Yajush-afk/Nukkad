"""Bounded Photon autocomplete; explicit Nominatim search is a separate service."""

import hashlib
import json
import os
import threading
import time
from urllib.parse import urlsplit

import httpx

from nukkad.geocoding import USER_AGENT, SearchUnavailable
from nukkad.identities import canonical_id
from nukkad.suggestions import bounds, suggestion, within_area

DEFAULT_ENDPOINT = "https://photon.komoot.io/api/"


def endpoint():
    url = os.environ.get("NUKKAD_PHOTON_URL", DEFAULT_ENDPOINT)
    try:
        parsed = urlsplit(url)
        _ = parsed.port
    except ValueError as error:
        raise SearchUnavailable("Online suggestions have an invalid Photon endpoint.") from error
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if (
        (parsed.scheme != "https" and not (local and parsed.scheme == "http"))
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise SearchUnavailable("Online suggestions have an invalid Photon endpoint.")
    return url


class Photon:
    def __init__(self):
        self.condition = threading.Condition()
        self.busy = False
        self.pending = None
        self.sequence = 0
        self.next_start = 0.0
        self.cooldown_until = 0.0

    def search(self, store, value):
        status = {"status": "available", "cooldown_seconds": 0}
        try:
            url = endpoint()
            area = store.get("area", "active")
            if value.scope == "place" and not area:
                raise SearchUnavailable("Save a neighbourhood before searching for places.")
            context = {
                "scope": value.scope,
                "bounds": bounds(area),
                "start": area["start"] if area else None,
            }
            key = hashlib.sha256(
                json.dumps([url, value.query.casefold(), context], sort_keys=True).encode()
            ).hexdigest()
            cached = store.get("location_suggestion", key)
            if cached and cached["expires_at"] > time.time():
                return self.resolve(store, cached["matches"]), {**status, "cached": True}
            with self.condition:
                if self.cooldown_until > time.monotonic():
                    return [], {
                        "status": "cooldown",
                        "cooldown_seconds": max(1, int(self.cooldown_until - time.monotonic())),
                        "message": "Online suggestions are cooling down. Local matches still work.",
                    }
                self.sequence += 1
                ticket = self.sequence
                self.pending = ticket
                self.condition.notify_all()
                deadline = time.monotonic() + 7
                while self.busy:
                    self.condition.wait(timeout=max(0.01, deadline - time.monotonic()))
                    if self.pending != ticket:
                        return [], {"status": "superseded", "cooldown_seconds": 0}
                    if time.monotonic() >= deadline:
                        raise SearchUnavailable(
                            "Online suggestions are busy. Use a local match or Search."
                        )
                if self.pending != ticket:
                    return [], {"status": "superseded", "cooldown_seconds": 0}
                self.pending = None
                self.busy = True
            try:
                wait = self.next_start - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                # A request queued behind a 429 must not bypass its cooldown.
                if self.cooldown_until > time.monotonic():
                    raise SearchUnavailable("Online suggestions are cooling down.", 429)
                self.next_start = time.monotonic() + 1
                params = {"q": value.query, "lang": "en", "limit": 5}
                if area:
                    params.update(lat=area["start"]["lat"], lon=area["start"]["lon"])
                    if value.scope == "place":
                        params["bbox"] = ",".join(map(str, bounds(area)))
                with httpx.Client(
                    timeout=5,
                    trust_env=False,
                    follow_redirects=False,
                    headers={"User-Agent": USER_AGENT},
                ) as client:
                    response = client.get(url, params=params)
                    if response.status_code == 429:
                        self.cooldown_until = time.monotonic() + 60
                    response.raise_for_status()
                    matches = self.parse(response.json(), area if value.scope == "place" else None)
                store.put(
                    "location_suggestion",
                    key,
                    {
                        "record_version": 1,
                        "matches": matches,
                        "expires_at": time.time() + (86400 if matches else 600),
                    },
                )
                # Dedicated provider cache: expired and oldest entries cannot grow indefinitely.
                with store.connect() as connection:
                    rows = connection.execute(
                        "SELECT id,data FROM records WHERE kind='location_suggestion' ORDER BY updated DESC"
                    ).fetchall()
                    expired = [
                        row[0]
                        for row in rows
                        if json.loads(row[1]).get("expires_at", 0) <= time.time()
                    ]
                    excess = [row[0] for row in rows if row[0] not in expired][256:]
                    connection.executemany(
                        "DELETE FROM records WHERE kind='location_suggestion' AND id=?",
                        [(key,) for key in [*expired, *excess]],
                    )
                return self.resolve(store, matches), status
            finally:
                with self.condition:
                    self.busy = False
                    self.condition.notify_all()
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 429:
                self.cooldown_until = time.monotonic() + 60
                return [], {
                    "status": "cooldown",
                    "cooldown_seconds": 60,
                    "message": "Online suggestions are rate-limited. Local matches still work.",
                }
            return [], {
                "status": "unavailable",
                "cooldown_seconds": 0,
                "message": "Online suggestions are unavailable. Use a local match or Search.",
            }
        except (httpx.HTTPError, ValueError, KeyError, TypeError, SearchUnavailable) as error:
            return [], {
                "status": "unavailable",
                "cooldown_seconds": max(0, int(self.cooldown_until - time.monotonic())),
                "message": str(error)
                if isinstance(error, SearchUnavailable)
                else "Online suggestions are unavailable. Local matches still work.",
            }

    @staticmethod
    def parse(data, area):
        if not isinstance(data, dict) or not isinstance(data.get("features"), list):
            raise ValueError("Malformed Photon response")
        matches = []
        for feature in data["features"][:5]:
            if (
                not isinstance(feature, dict)
                or not isinstance(feature.get("geometry"), dict)
                or feature["geometry"].get("type") != "Point"
            ):
                raise ValueError("Malformed Photon feature")
            lon, lat = feature["geometry"]["coordinates"]
            properties = feature["properties"]
            if not isinstance(properties, dict):
                raise ValueError("Malformed Photon properties")
            name = properties.get("name") or properties.get("street") or properties.get("city")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Photon result has no readable name")
            parts = list(
                dict.fromkeys(
                    str(properties[key])
                    for key in (
                        "street",
                        "housenumber",
                        "district",
                        "city",
                        "state",
                        "postcode",
                        "country",
                    )
                    if properties.get(key)
                )
            )
            source_type = {"N": "node", "W": "way", "R": "relation"}.get(properties.get("osm_type"))
            source_id = (
                f"osm-{source_type}-{properties['osm_id']}"
                if source_type and properties.get("osm_id")
                else None
            )
            item = suggestion(
                name,
                ", ".join(parts) or name,
                {"lat": lat, "lon": lon},
                "OpenStreetMap / Photon",
                "Online results",
                source_id=source_id,
            )
            if area and not within_area(item["point"], area):
                continue
            matches.append(item)
        return matches

    @staticmethod
    def resolve(store, matches):
        aliases = store.keyed("place_alias")
        return [
            {
                **item,
                "place_id": canonical_id(store, item["source_id"], aliases)
                if item.get("source_id") in aliases
                else None,
            }
            for item in matches
        ]
