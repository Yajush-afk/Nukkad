from datetime import UTC, datetime
from xml.etree import ElementTree

import cairosvg

from nukkad.cards import svg_card
from nukkad.planning import Planner, QuestInput, Settings, baseline
from nukkad.quests import TEMPLATES


def test_portrait_card_escapes_names_and_preserves_stop_order(registry):
    maps, _, snapshot, _, _ = registry
    planner = Planner(maps, Settings(), lambda: datetime(2026, 10, 8, 7, tzinfo=UTC))
    candidates = planner.candidates(QuestInput(), [])
    quest = planner.build(candidates, baseline(candidates, []), QuestInput())
    quest.update(
        ranking_mode="local AI",
        prose_mode="template fallback",
        prompts={place["id"]: {"text": TEMPLATES["detail"]} for place in quest["stops"]},
    )
    quest["stops"][0]["name"] = '<script>&"'
    card = svg_card(quest, snapshot)
    root = ElementTree.fromstring(card)
    assert root.attrib["width"] == "1080"
    assert root.attrib["height"] == "1920"
    assert "<script>" not in card
    assert "&lt;script&gt;" in card
    image = cairosvg.svg2png(bytestring=card.encode())
    assert image[:8] == b"\x89PNG\r\n\x1a\n"
    assert int.from_bytes(image[16:20], "big") == 1080
    assert int.from_bytes(image[20:24], "big") == 1920
