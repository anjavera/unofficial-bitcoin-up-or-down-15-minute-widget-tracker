"""Band and colour lookup for net change and result marks."""

BAND_EDGES = (10, 25, 50, 100, 200, 300, 400, 500, 1000)
STEPS = len(BAND_EDGES)
BACKGROUND = {"dark": "#0e1117", "light": "#ffffff"}

# (pale end, saturated end) per theme; steps are linear RGB interpolations
_BLUE = {"dark": ("#cfe3ff", "#1f5fd6"), "light": ("#c2d8ff", "#0b3c9c")}
_ORANGE = {"dark": ("#ffe0c2", "#e0620d"), "light": ("#ffd2a8", "#a84300")}
_RESULT = {
    "dark": {"UP": "#2ecc71", "DOWN": "#ff5252"},
    "light": {"UP": "#1e8e3e", "DOWN": "#d93025"},
}


def band_index(net: float) -> int:
    """0..8: the first band whose upper edge exceeds |net|; |net| >= 1000 stays in the last band."""
    size = abs(net)
    for i, edge in enumerate(BAND_EDGES):
        if size < edge:
            return i
    return STEPS - 1


def _lerp(start: str, end: str, step: int) -> str:
    a = [int(start[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(end[i : i + 2], 16) for i in (1, 3, 5)]
    t = step / (STEPS - 1)
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def net_color(net: float, theme: str) -> str:
    """Blue for net >= 0, orange for net < 0; intensity grows with the band."""
    pale, deep = (_BLUE if net >= 0 else _ORANGE)[theme]
    return _lerp(pale, deep, band_index(net))


def result_color(result: str, theme: str) -> str:
    try:
        return _RESULT[theme][result]
    except KeyError:
        raise ValueError(f"unknown result {result!r} or theme {theme!r}") from None


def _luminance(hex_color: str) -> float:
    def lin(c: int) -> float:
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(int(hex_color[i : i + 2], 16)) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def text_on(background: str) -> str:
    """Black or white, whichever reads better on `background`."""
    lum = _luminance(background)
    return "#000000" if (lum + 0.05) / 0.05 >= 1.05 / (lum + 0.05) else "#ffffff"
