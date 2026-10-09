import json
import math
import random
import socket
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from nukkad.cards import svg_card
from nukkad.config import Config
from nukkad.maps import Maps
from nukkad.places import AreaInput
from nukkad.planning import INTEREST_KINDS, NoQuest, Planner, QuestInput, Settings, baseline
from nukkad.quests import TEMPLATES, active_interests, generate
from nukkad.storage import Store

CASES = [
    ("short-low-energy", 20, [], "A slow walk today", False),
    ("nature", 30, ["nature"], "", False),
    ("markets", 30, ["markets"], "", False),
    ("architecture", 40, ["architecture"], "", False),
    ("visited-nature", 30, ["nature"], "Something different", True),
    ("accepted-interest", 30, [], "", False),
    ("sparse-notes", 30, ["art"], "", False),
    ("long-variety", 60, ["sports", "markets"], "A change of scene", False),
    ("purposeful-revisit", 40, ["nature"], "Revisit a familiar place", True),
    ("no-feasible-route", 20, ["trees"], "", False),
]


def synthetic_map(path: Path):
    # Artificial coordinates and names, not an assertion of real public paths or venues.
    nodes = []
    ways = []
    for index in range(1, 10):
        angle = (index - 2) * math.pi / 4
        radius = 0.0015 + (index - 2) * 0.00018 if index > 1 else 0
        lat = 28.6 + math.sin(angle) * radius
        lon = 77.3 + math.cos(angle) * radius / math.cos(math.radians(28.6))
        tags = '<tag k="entrance" v="yes"/>' if index > 1 else ""
        nodes.append(f'<node id="{index}" lat="{lat}" lon="{lon}">{tags}</node>')
    kinds = [
        ("leisure", "park"),
        ("leisure", "garden"),
        ("tourism", "artwork"),
        ("amenity", "marketplace"),
        ("historic", "memorial"),
        ("leisure", "pitch"),
        ("tourism", "attraction"),
        ("amenity", "place_of_worship"),
    ]
    for index in range(1, 9):
        ways.append(
            f'<way id="{100 + index}"><nd ref="1"/><nd ref="{index + 1}"/><tag k="highway" v="residential"/><tag k="name" v="Synthetic lane {index}"/></way>'
        )
    for index, (key, value) in enumerate(kinds, 2):
        # Node POIs on walking vertices provide clear street-frontage anchors in this fixture.
        old = '<tag k="entrance" v="yes"/>'
        nodes[index - 1] = nodes[index - 1].replace(
            old, old + f'<tag k="{key}" v="{value}"/><tag k="name" v="Sample destination {index}"/>'
        )
    path.write_text('<osm version="0.6">' + "".join(nodes + ways) + "</osm>")


@contextmanager
def loopback_only():
    """Process-level egress denial; leave user's machine/network settings unchanged."""
    original = socket.socket.connect
    attempts = []

    def guarded(sock, address):
        if sock.family in {socket.AF_INET, socket.AF_INET6}:
            if address[0] not in {"127.0.0.1", "::1"}:
                attempts.append(str(address[0]))
                raise OSError("Evaluation blocks non-loopback connections")
        return original(sock, address)

    socket.socket.connect = guarded
    try:
        yield attempts
    finally:
        socket.socket.connect = original


def evaluate(config: Config, output: Path):
    output.mkdir(parents=True, exist_ok=False)
    isolated = Config(data_dir=output / "private-data", model=config.model)
    isolated.prepare()
    store = Store(isolated.data_dir)
    source = output / "synthetic.osm"
    synthetic_map(source)
    maps = Maps(isolated, store)
    snapshot = maps.acquire(
        AreaInput(
            name="Synthetic evaluation neighbourhood",
            start={"lat": 28.6, "lon": 77.3},
            radius_meters=1500,
            public_start_confirmed=True,
        ),
        source,
    )
    snapshot["synthetic"] = True
    store.put("snapshot", snapshot["id"], snapshot)
    report = {
        "scope": "Synthetic map cases with actual local inference and process-level non-loopback socket denial; not physical field trials",
        "model": config.model,
        "rules": {
            "interest_kinds": {key: sorted(value) for key, value in INTEREST_KINDS.items()},
            "formula": "interest matches + unvisited bonus 1 - round-trip kilometres",
            "candidate_cap": 15,
            "max_stops": 3,
        },
        "cases": [],
        "human_ratings": "pending",
    }
    key = []
    with loopback_only() as blocked:
        for index, (name, minutes, interests, state, visited) in enumerate(CASES, 1):
            store.put("profile", "active", {"interests": interests})
            for kind in ("outcome", "interest"):
                for item in store.list(kind):
                    store.delete(kind, item["id"])
            if visited:
                store.put(
                    "outcome",
                    "reported",
                    {
                        "id": "reported",
                        "note": "I enjoyed looking at tree shapes.",
                        "reached_ids": ["osm-node-2", "osm-node-3"],
                    },
                )
            if name == "accepted-interest":
                store.put(
                    "outcome",
                    "reviewed",
                    {"id": "reviewed", "note": "I enjoyed tree shapes.", "reached_ids": []},
                )
                store.put(
                    "interest",
                    "reviewed",
                    {
                        "id": "reviewed",
                        "theme": "trees",
                        "quote": "I enjoyed tree shapes.",
                        "source_note_id": "reviewed",
                        "status": "accepted",
                    },
                )
            settings = Settings(
                model=config.model, max_distance_meters=200 if name == "no-feasible-route" else 4000
            )
            request = QuestInput(minutes=minutes, state=state)
            planner = Planner(maps, settings, lambda: datetime(2026, 10, 8, 7, tzinfo=UTC))
            candidates = planner.candidates(request, active_interests(store))
            row = {
                "name": name,
                "input": request.model_dump(),
                "interests": active_interests(store),
                "settings": settings.model_dump(),
                "candidate_ids": [place.id for place in candidates],
                "results": {},
            }
            variants = []
            for mode in ("nearest", "interests", "ai"):
                try:
                    if mode == "ai":
                        quest = generate(
                            maps,
                            store,
                            isolated,
                            settings,
                            request,
                            lambda _: None,
                            planner=planner,
                        )
                    else:
                        quest = planner.build(
                            candidates, baseline(candidates, active_interests(store), mode), request
                        )
                        quest.update(
                            ranking_mode=mode,
                            prose_mode="templates",
                            prompts={
                                stop["id"]: {"text": TEMPLATES["detail"]} for stop in quest["stops"]
                            },
                        )
                    row["results"][mode] = {
                        "stops": [stop["id"] for stop in quest["stops"]],
                        "ranked_ids": quest["ranked_ids"],
                        "prompts": quest["prompts"],
                        "meters": quest["meters"],
                        "minutes": quest["estimated_minutes"],
                        "ranking_mode": quest["ranking_mode"],
                        "prose_mode": quest["prose_mode"],
                        "generation_seconds": quest.get("generation_seconds"),
                        "metrics": quest.get("metrics", {}),
                    }
                    variants.append((mode, quest))
                except NoQuest as error:
                    row["results"][mode] = {"no_quest": str(error)}
            random.SystemRandom().shuffle(variants)
            for letter, (mode, quest) in zip("ABC", variants, strict=False):
                blinded = {**quest, "ranking_mode": "comparison", "prose_mode": "comparison"}
                filename = f"case-{index:02d}-{letter}.svg"
                (output / filename).write_text(svg_card(blinded, snapshot))
                key.append({"case": index, "letter": letter, "mode": mode, "file": filename})
            report["cases"].append(row)
            report["blocked_non_loopback_attempts"] = list(blocked)
            (output / "diagnostics.json").write_text(json.dumps(report, indent=2))
            print(f"{index}/10: {name}", flush=True)
    (output / "blinding-key.json").write_text(json.dumps(key, indent=2))
    ratings = {
        "instructions": "Review cards before opening the blinding key. Rate each 1–5 for interest fit, willingness to go, variety and prompt usefulness. Record ties, losses and comments. These are descriptive ratings, not statistical evidence.",
        "ratings": [
            {
                "case": item["case"],
                "letter": item["letter"],
                "interest_fit": None,
                "willingness": None,
                "variety": None,
                "prompt_usefulness": None,
                "comment": "",
            }
            for item in key
        ],
    }
    (output / "ratings.json").write_text(json.dumps(ratings, indent=2))
    return report
