"""Stable local place identities and reviewed source aliases."""

import hashlib
import itertools
import re

from nukkad.storage import now


def canonical_id(store, source_id, aliases=None):
    seen = set()
    while source_id not in seen:
        seen.add(source_id)
        alias = store.get("place_alias", source_id) if aliases is None else aliases.get(source_id)
        if not alias or alias["canonical_id"] == source_id:
            return source_id
        source_id = alias["canonical_id"]
    raise ValueError("Place aliases contain a cycle; restore or repair the registry")


def identity_records(store, places):
    records = []
    previous = {place["id"] for snapshot in store.list("snapshot") for place in snapshot["places"]}
    for place in places:
        sources = place.source_ids or [place.id]
        known = next(
            (key for key in sources if store.get("place_alias", key) or key in previous), sources[0]
        )
        root = canonical_id(store, known)
        old = store.get("place_identity", root) or {}
        identity = {
            "id": root,
            "record_version": 1,
            "source_ids": sorted(set([*old.get("source_ids", []), *sources])),
            "name": place.name,
            "created_at": old.get("created_at", now()),
        }
        records.append(("place_identity", root, identity))
        for source in sources:
            records.append(
                ("place_alias", source, {"id": source, "canonical_id": root, "record_version": 1})
            )
    return records


def duplicate_candidates(store, places, distance):
    result = []
    for first, second in itertools.combinations(places, 2):
        if first.id == second.id or first.kind != second.kind:
            continue

        def normal(name):
            return re.sub(r"\W+", " ", name.casefold()).strip()

        if normal(first.name) != normal(second.name) or distance(first.point, second.point) > 40:
            continue
        pair = sorted((first.id, second.id))
        key = hashlib.sha256("|".join(pair).encode()).hexdigest()[:32]
        reviewed = store.get("place_duplicate", key)
        if reviewed and reviewed["decision"] == "separate":
            continue
        result.append(
            {
                "id": key,
                "place_ids": pair,
                "names": [first.name, second.name],
                "distance_meters": round(distance(first.point, second.point), 1),
                "status": "pending",
            }
        )
    return result
