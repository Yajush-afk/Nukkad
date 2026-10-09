import cairocffi as cairo


def text_width(text: str, size: float) -> float:
    context = cairo.Context(cairo.ImageSurface(cairo.FORMAT_ARGB32, 1, 1))
    context.select_font_face("DejaVu Sans")
    context.set_font_size(size)
    return context.text_extents(text)[4]


def wrap_text(text: str, size: float, width: float = 952) -> list[str]:
    lines = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if text_width(candidate, size) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        for char in word:
            if current and text_width(current + char, size) > width:
                lines.append(current)
                current = ""
            current += char
    if current:
        lines.append(current)
    return lines or [""]


def ellipsise(text: str, size: float, width: float = 952) -> str:
    while text and text_width(text + "…", size) > width:
        text = text[:-1]
    return text.rstrip() + "…"
