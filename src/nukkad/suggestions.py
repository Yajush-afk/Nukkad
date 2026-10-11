"""Local location suggestions: document metadata only, never the routing graph."""

import hashlib
import math
import time
from typing import Literal

from fastapi import APIRouter, Request

from nukkad.cache import RevisionCache
from nukkad.domain import Point
from nukkad.geocoding import SearchInput
from nukkad.identities import canonical_id
from nukkad.maps import distance

router = APIRouter(prefix="/api/locations")


class SuggestInput(SearchInput):
    scope: Literal["neighbourhood", "place"] = "neighbourhood"
    online: bool = False


def bounds(area):
    if not area:
        return None
    start, radius = area["start"], area["radius_meters"]
    dy = radius / 111320
    dx = radius / (111320 * max(0.01, math.cos(math.radians(start["lat"]))))
    return [start["lon"] - dx, start["lat"] - dy, start["lon"] + dx, start["lat"] + dy]


def within_area(point, area):
    return bool(
        area
        and distance(Point.model_validate(point), Point.model_validate(area["start"]))
        <= area["radius_meters"]
    )


def suggestion(name, label, point, source, group, *, place_id=None, source_id=None, entrance=False):
    point = Point.model_validate(point).model_dump()
    key = place_id or source_id or hashlib.sha256(f"{label}|{point}".encode()).hexdigest()[:24]
    return {
        "id": f"{group}:{key}",
        "name": str(name)[:200],
        "label": str(label)[:1000],
        "point": point,
        "source": source,
        "group": group,
        "place_id": place_id,
        "source_id": source_id,
        "entrance_confirmed": entrance,
    }


def build_index(store):
    active = store.get("area", "active")
    snapshot = store.get("snapshot", active["snapshot_id"]) if active else None
    aliases = store.keyed("place_alias")
    corrections = store.keyed("place")
    items, seen = [], set()
    for original in [*(snapshot or {}).get("places", []), *corrections.values()]:
        root = canonical_id(store, original["id"], aliases)
        data = {**original, **corrections.get(original["id"], {}), **corrections.get(root, {})}
        if root in seen or not within_area(data["point"], active):
            continue
        seen.add(root)
        tags = data.get("tags", {})
        address = ", ".join(
            str(tags[key]) for key in ("addr:street", "addr:suburb", "addr:city") if tags.get(key)
        )
        items.append(
            suggestion(
                data["name"],
                address or active["name"],
                data.get("entrance") or data["point"],
                "Saved place",
                "On your map",
                place_id=root,
                source_id=original["id"],
                entrance=bool(
                    data.get("entrance") and data.get("access") in {"mapped", "confirmed"}
                ),
            )
        )
    # Street geometry is display metadata already stored in the snapshot.
    for index, feature in enumerate((snapshot or {}).get("geometry", {}).get("features", [])):
        name = feature.get("properties", {}).get("name")
        coordinates = feature.get("geometry", {}).get("coordinates", [])
        if not name or feature.get("geometry", {}).get("type") != "LineString" or not coordinates:
            continue
        lon, lat = coordinates[len(coordinates) // 2][:2]
        key = (name, lat, lon)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            suggestion(
                name,
                active["name"],
                {"lat": lat, "lon": lon},
                "Saved street",
                "On your map",
                source_id=f"street-{index}",
            )
        )
    for kind in ("location_search", "location_suggestion"):
        for cached in store.list(kind):
            if cached.get("expires_at", 0) <= time.time():
                continue
            for item in cached.get("matches", []):
                source_id = item.get("source_id")
                root = canonical_id(store, source_id, aliases) if source_id in aliases else None
                items.append(
                    suggestion(
                        item["name"],
                        item["label"],
                        item["point"],
                        "Cached search",
                        "Previous searches",
                        place_id=root,
                        source_id=source_id,
                    )
                )
    return items


def local_matches(store, cache, value):
    revision = store.revision_key(
        ("area", "snapshot", "place", "place_alias", "location_search", "location_suggestion")
    )
    items = cache.get("suggestions", (revision, int(time.time() // 60)), lambda: build_index(store))
    words = value.query.casefold().split()
    active = store.get("area", "active")
    result, seen = [], set()
    for item in items:
        if not all(word in (item["name"] + " " + item["label"]).casefold() for word in words):
            continue
        if value.scope == "place" and not within_area(item["point"], active):
            continue
        key = item["place_id"] or (item["name"], tuple(item["point"].values()))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) == 12:
            break
    return result


@router.post("/suggest")
def suggest(value: SuggestInput, request: Request):
    state = request.app.state
    matches = local_matches(state.store, state.suggestion_index, value)
    online = {"status": "not_requested", "cooldown_seconds": 0}
    if value.online:
        remote, online = state.photon.search(state.store, value)
        existing = {item["place_id"] for item in matches if item["place_id"]}
        matches.extend(
            item for item in remote if not item["place_id"] or item["place_id"] not in existing
        )
    return {"matches": matches, "online": online}


def install(app):
    # Separate from the small walking graph/map cache.
    from nukkad.photon import Photon

    app.state.photon = Photon()
    app.state.suggestion_index = RevisionCache(capacity=2)
    app.include_router(router)
