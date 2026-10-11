"""Shared personalisation inputs for deterministic previews and local AI."""


def active_interests(store):
    explicit = (store.get("profile", "active") or {}).get("interests", [])
    accepted = [
        item["theme"] for item in store.list("interest") if item.get("status") == "accepted"
    ]
    return list(dict.fromkeys([*explicit, *accepted]))[:20]
