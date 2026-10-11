"""Task-specific checks complement source links; they do not prove interpretation."""

import re

from nukkad.typography import wrap_text

OBJECTS = {
    "kingfisher",
    "fountain",
    "statue",
    "sculpture",
    "temple",
    "shrine",
    "wildlife",
    "bench",
    "pond",
    "doorway",
    "stall",
    "tree",
    "trees",
    "flowers",
}
FORBIDDEN = re.compile(
    r"\b(safe|safest|guaranteed|ancient|built|founded|historic|historical|cure|treat|therapy|permission|enter|cross|turn left|turn right)\b",
    re.I,
)


def validate_evidence(ids, catalog):
    if not ids or len(ids) != len(set(ids)) or not set(ids) <= catalog.keys():
        raise ValueError("Use distinct evidence IDs from the supplied catalogue")
    return " ".join(catalog[key] for key in ids)


def validate_invitation(text, evidence=""):
    if len(wrap_text(text, 27)) > 2:
        raise ValueError("Keep the observation to two readable phone-card lines")
    if re.search(r"\d", text) or FORBIDDEN.search(text):
        raise ValueError("Do not add numbers, history, directions, access or health claims")
    if not re.match(
        r"^(notice|look|listen|pause|find|take|if|compare|observe|try|focus|choose|what|which)\b",
        text,
        re.I,
    ):
        raise ValueError("Write an observation invitation")
    words = set(re.findall(r"[a-z]+", text.lower()))
    supported = set(re.findall(r"[a-z]+", evidence.lower()))
    if (words & OBJECTS) - supported:
        raise ValueError("A named feature requires supplied evidence")
    named = re.findall(r"(?<![.!?] )\b[A-Z][a-z]+\b", text[1:])
    if any(name.lower() not in supported for name in named):
        raise ValueError("Do not add unsupported names")


def validate_rationale(text, evidence):
    if len(text.split()) > 12 or not text.startswith(("Suggestion:", "Idea:")):
        raise ValueError("Use a short subjective Suggestion: or Idea: explanation")
    if FORBIDDEN.search(text) or re.search(r"\d", text):
        raise ValueError("Do not assert route, access, historical or health facts")
    words = set(re.findall(r"[a-z]+", text.lower()))
    if (words & OBJECTS) - set(re.findall(r"[a-z]+", evidence.lower())):
        raise ValueError("The explanation names an unsupported feature")
