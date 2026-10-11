"""Strict OSM multipolygon reconstruction; incomplete rings never become places."""

from shapely.geometry import MultiPolygon, Polygon, mapping

from nukkad.places import place_kind


def element_tags(element):
    return {tag.attrib["k"]: tag.attrib["v"] for tag in element.findall("tag")}


def rings(parts, relation_id):
    remaining = [list(part) for part in parts]
    result = []
    while remaining:
        ring = remaining.pop(0)
        while ring[0] != ring[-1]:
            match = next(
                (i for i, part in enumerate(remaining) if ring[-1] in (part[0], part[-1])), None
            )
            if match is None:
                raise ValueError(f"Multipolygon {relation_id} has an incomplete boundary")
            part = remaining.pop(match)
            if part[-1] == ring[-1]:
                part.reverse()
            ring.extend(part[1:])
        if len(ring) < 4:
            raise ValueError(f"Multipolygon {relation_id} has an invalid ring")
        result.append(ring)
    return result


def multipolygons(root, points):
    ways = {way.attrib["id"]: way for way in root.findall("way")}
    result, suppressed = {}, set()
    for relation in root.findall("relation"):
        tags = element_tags(relation)
        if tags.get("type") != "multipolygon" or not place_kind(tags):
            continue
        key = relation.attrib["id"]
        parts = {"outer": [], "inner": []}
        aliases, members = [], []
        for member in relation.findall("member"):
            role = member.attrib.get("role") or "outer"
            if role not in parts:
                continue
            way = ways.get(member.attrib["ref"])
            if member.attrib["type"] != "way" or way is None:
                raise ValueError(f"Multipolygon {key} is missing a boundary member")
            refs = [int(item.attrib["ref"]) for item in way.findall("nd")]
            if len(refs) < 2 or any(ref not in points for ref in refs):
                raise ValueError(f"Multipolygon {key} is missing boundary vertices")
            parts[role].append(refs)
            members.append(f"osm-way-{way.attrib['id']}")
            own = element_tags(way)
            if (
                role == "outer"
                and place_kind(own) == place_kind(tags)
                and all(
                    own.get(name, "") == tags.get(name, "") for name in ("name", "access", "foot")
                )
            ):
                suppressed.add(way.attrib["id"])
                aliases.append(f"osm-way-{way.attrib['id']}")
        outer, inner = rings(parts["outer"], key), rings(parts["inner"], key)
        if not outer:
            raise ValueError(f"Multipolygon {key} has no outer boundary")

        def coordinates(refs):
            return [(points[ref].lon, points[ref].lat) for ref in refs]

        shells = [Polygon(coordinates(refs)) for refs in outer]
        holes = [[] for _ in shells]
        for refs in inner:
            hole = Polygon(coordinates(refs))
            owners = [i for i, shell in enumerate(shells) if shell.contains(hole)]
            if len(owners) != 1:
                raise ValueError(f"Multipolygon {key} has an invalid inner boundary")
            holes[owners[0]].append(coordinates(refs))
        shape = MultiPolygon([Polygon(coordinates(refs), holes[i]) for i, refs in enumerate(outer)])
        if not shape.is_valid or shape.is_empty:
            raise ValueError(f"Multipolygon {key} geometry is invalid")
        result[key] = {
            "geometry": mapping(shape),
            "point": shape.representative_point(),
            "nodes": [ref for ring in outer for ref in ring],
            "aliases": aliases,
            "members": members,
        }
    return result, suppressed
