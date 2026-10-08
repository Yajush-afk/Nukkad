import math
import textwrap
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

import cairosvg
from fastapi import APIRouter, Request
from fastapi.responses import Response

from nukkad.quests_api import quest_by_id

router = APIRouter(prefix="/api/quests")


def svg_card(quest: dict, snapshot: dict) -> str:
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1920" viewBox="0 0 1080 1920">',
        '<rect width="1080" height="1920" fill="#f6f2e8"/>',
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6" fill="none" stroke="#ce6336" stroke-width="1"/></marker></defs>',
    ]

    def text(x, y, value, size=28, fill="#243a31"):
        parts.append(
            f'<text x="{x}" y="{y}" font-family="DejaVu Sans,sans-serif" font-size="{size}" fill="{fill}">{escape(str(value))}</text>'
        )

    def lines(y, value, width=64, size=27, step=34, maximum=3):
        wrapped = textwrap.wrap(str(value), width=width) or [""]
        if len(wrapped) > maximum:
            wrapped = wrapped[:maximum]
            wrapped[-1] = wrapped[-1][:-1] + "…"
        for line in wrapped:
            text(64, y, line, size)
            y += step
        return y

    coordinates = [point for leg in quest["legs"] for point in leg["coordinates"]]
    lons, lats = zip(*coordinates, strict=True)
    midlat = sum(lats) / len(lats)
    coslat = math.cos(math.radians(midlat))
    xs = [lon * coslat for lon in lons]
    minx, maxx, miny, maxy = min(xs), max(xs), min(lats), max(lats)
    scale = min(880 / max(maxx - minx, 0.0001), 520 / max(maxy - miny, 0.0001))
    centerx, centery = (minx + maxx) / 2, (miny + maxy) / 2

    def project(point):
        return 540 + (point[0] * coslat - centerx) * scale, 535 - (point[1] - centery) * scale

    parts.append('<rect x="48" y="230" width="984" height="610" rx="20" fill="#e9ece2"/>')
    parts.append(
        '<clipPath id="mapclip"><rect x="48" y="230" width="984" height="610" rx="20"/></clipPath><g clip-path="url(#mapclip)">'
    )
    for feature in snapshot["geometry"]["features"]:
        geometry = feature["geometry"]
        if geometry["type"] == "LineString":
            points = " ".join(f"{x:.1f},{y:.1f}" for x, y in map(project, geometry["coordinates"]))
            parts.append(
                f'<polyline points="{points}" fill="none" stroke="#c8d0c5" stroke-width="3"/>'
            )
    for leg in quest["legs"]:
        points = " ".join(f"{x:.1f},{y:.1f}" for x, y in map(project, leg["coordinates"]))
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="#ce6336" stroke-width="8" stroke-linejoin="round" opacity=".85" marker-end="url(#arrow)"/>'
        )
    parts.append("</g>")
    for index, stop in enumerate(quest["stops"], 1):
        point = stop["entrance"]
        x, y = project([point["lon"], point["lat"]])
        parts.append(f'<circle cx="{x}" cy="{y}" r="24" fill="#243a31"/>')
        text(x - 9, y + 10, index, 29, "#fff")
    x, y = project([quest["start"]["lon"], quest["start"]["lat"]])
    parts.append(
        f'<circle cx="{x}" cy="{y}" r="18" fill="#f6f2e8" stroke="#243a31" stroke-width="5"/>'
    )
    text(64, 85, "NUKKAD / YOUR NEIGHBOURHOOD, NOTICED", 23)
    text(64, 154, "A little walk. A fresh look.", 48)
    zone = ZoneInfo(quest["timezone"])
    date = datetime.fromisoformat(quest["generated_at"]).astimezone(zone)
    text(
        64,
        205,
        f"{date:%d %b %Y}  ·  {quest['estimated_minutes']} min  ·  {quest['meters'] / 1000:.2f} km",
        29,
    )
    text(64, 881, "START + RETURN · open circle on the map", 25)
    y = 935
    for index, stop in enumerate(quest["stops"], 1):
        y = lines(y, f"{index:02d}  {stop['name']}", width=48, size=32, maximum=2, step=38)
        y = lines(y + 8, quest["prompts"][stop["id"]]["text"], maximum=2)
        street = " → ".join(quest["legs"][index - 1]["streets"])
        y = lines(y + 6, "Via " + street, width=76, size=23, step=28, maximum=2) + 22
    y = lines(
        y,
        "Return via " + " → ".join(quest["legs"][-1]["streets"]),
        width=76,
        size=23,
        step=28,
        maximum=2,
    )
    departure = datetime.fromisoformat(quest["latest_departure"]).astimezone(zone)
    sunset = datetime.fromisoformat(quest["sunset"]).astimezone(zone)
    text(64, 1642, f"Leave by {departure:%H:%M} · Sunset {sunset:%H:%M} · {quest['timezone']}", 25)
    lines(
        1685,
        f"{quest['ranking_mode']} ranking / {quest['prose_mode']} prompts",
        width=70,
        size=23,
        maximum=2,
    )
    lines(
        1768,
        "Mapped access is uncertain. Stay on public paths; turn back if blocked. This dated card has no live navigation.",
        width=74,
        size=23,
        step=29,
        maximum=3,
    )
    text(64, 1890, "Map data © OpenStreetMap contributors · openstreetmap.org/copyright", 19)
    parts.append("</svg>")
    return "".join(parts)


@router.get("/{key}/card.svg")
def card_svg(key: str, request: Request):
    quest = quest_by_id(key, request)
    snapshot = request.app.state.store.get("snapshot", quest["snapshot_id"])
    return Response(svg_card(quest, snapshot), media_type="image/svg+xml")


@router.get("/{key}/card.png")
def card_png(key: str, request: Request):
    quest = quest_by_id(key, request)
    if quest["status"] != "accepted":
        raise ValueError("Accept the quest after reviewing its route before downloading")
    snapshot = request.app.state.store.get("snapshot", quest["snapshot_id"])
    content = cairosvg.svg2png(bytestring=svg_card(quest, snapshot).encode())
    return Response(
        content,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="nukkad-{key}.png"'},
    )
