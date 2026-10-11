"""Shared personalisation inputs for deterministic previews and local AI."""

from nukkad.identities import canonical_id


def outing_context(store, request, interests, candidates=()):
    candidate_ids = {canonical_id(store, place.id) for place in candidates}
    outcomes = store.list("outcome")
    relevant, recent = [], []
    for item in outcomes:
        reached = [canonical_id(store, key) for key in item.get("reached_ids", [])]
        if item.get("note", "").strip():
            note = {
                "id": item["id"],
                "text": item["note"][:600],
                "place_ids": reached,
                "reporting": "self-reported",
            }
            (relevant if candidate_ids.intersection(reached) else recent).append(note)
    notes = (relevant[:3] + recent[:4])[:4]
    visited = sorted(
        {canonical_id(store, key) for outcome in outcomes for key in outcome.get("reached_ids", [])}
        & candidate_ids
    )
    return {
        "minutes": request.minutes,
        "state": request.state,
        "mode": request.mode,
        "interests": interests,
        "notes": notes,
        "reported_visits": visited,
    }


def candidate_facts(place):
    return {
        "id": place.id,
        "name": place.name,
        "kind": place.kind,
        "visited": place.visited,
        "descriptors": place.descriptors,
        "recorded_features": {
            key: value
            for key, value in place.tags.items()
            if key in {"description", "species", "sport", "artwork_type"}
        },
        "round_trip_meters": place.round_trip_meters,
    }


def evidence_catalog(context, candidates):
    return {
        "request": f"{context['minutes']} minutes; {context['state']}; {context['mode']}",
        **{f"interest:{index}": theme for index, theme in enumerate(context["interests"])},
        **{f"note:{note['id']}": note["text"] for note in context["notes"]},
        **{f"place:{place.id}": str(candidate_facts(place)) for place in candidates},
    }


def active_interests(store):
    explicit = (store.get("profile", "active") or {}).get("interests", [])
    accepted = [
        item["theme"] for item in store.list("interest") if item.get("status") == "accepted"
    ]
    return list(dict.fromkeys([*explicit, *accepted]))[:20]
