"""Side panel art: an analog countdown dial and the Bitcoin logo, drawn in terminal half-block pixels."""

import math

from rich.style import Style
from rich.text import Text

from btc15_widget.colors import result_color
from btc15_widget.logo import LOGOS, PALETTE

WINDOW_SECONDS = 900.0
TAU = 2 * math.pi
NEUTRAL = "#8b949e"


def dial_pixels(remaining: float, size: int, window: float = WINDOW_SECONDS) -> list[list[str]]:
    """Classify each pixel of a `size` x `size` clock face; one full revolution per window, starting at 12.

    The hand sits at the elapsed angle; the wedge from the hand clockwise back to 12 is the time remaining.
    """
    remaining = min(max(remaining, 0.0), window)
    elapsed = TAU * (1 - remaining / window)
    sin_e, cos_e = math.sin(elapsed), math.cos(elapsed)
    c, r = (size - 1) / 2, size / 2
    grid = []
    for y in range(size):
        row = []
        for x in range(size):
            dx, dy = x - c, y - c
            dist = math.hypot(dx, dy)
            if dist > r:
                row.append("out")
                continue
            if dist > r - 1.2:
                row.append("rim")
                continue
            along, across = dx * sin_e - dy * cos_e, abs(dx * cos_e + dy * sin_e)
            if dist < 1.2:
                row.append("center")
            elif 0 <= along <= r - 2.2 and across <= 0.75:
                row.append("hand")
            elif r - 3.0 <= dist and any(
                    abs((math.atan2(dx, -dy) - k * TAU / 15 + math.pi) % TAU - math.pi) * dist < 0.65 for k in range(15)):
                row.append("tick")
            else:
                theta = math.atan2(dx, -dy) % TAU
                row.append("remaining" if theta >= elapsed else "elapsed")
        grid.append(row)
    return grid


def _blocks(colors: list[list[str | None]]) -> Text:
    """Two pixel rows per text line using half blocks; None is transparent."""
    lines = []
    for top_row, bottom_row in zip(colors[0::2], colors[1::2]):
        line = Text()
        for top, bottom in zip(top_row, bottom_row):
            if top is None and bottom is None:
                line.append(" ")
            elif bottom is None:
                line.append("▀", Style(color=top))
            elif top is None:
                line.append("▄", Style(color=bottom))
            else:
                line.append("▀", Style(color=top, bgcolor=bottom))
        lines.append(line)
    return Text("\n").join(lines)


def render_dial(remaining: float, lean: str | None, theme: str, diameter: int = 20) -> Text:
    """Analog countdown with the digital time underneath; the wedge takes the colour of the current lean."""
    dark = theme == "dark"
    hand = "#ffffff" if dark else "#1f2328"
    palette = {
        "remaining": result_color(lean, theme) if lean else NEUTRAL,
        "elapsed": "#2b3138" if dark else "#d8dee4",
        "rim": "#6e7681", "tick": "#c9d1d9" if dark else "#57606a", "hand": hand, "center": hand, "out": None,
    }
    grid = dial_pixels(remaining, diameter)
    art = _blocks([[palette[kind] for kind in row] for row in grid])
    seconds = math.ceil(min(max(remaining, 0.0), WINDOW_SECONDS))
    digits = Text(f"{seconds // 60:02d}:{seconds % 60:02d}".center(diameter), style=Style(bold=True))
    return Text("\n").join([art, digits])


def render_logo(size: int = 20) -> Text:
    if size not in LOGOS:
        raise ValueError(f"no logo at size {size}; available: {sorted(LOGOS)}")
    return _blocks([[PALETTE.get(key) for key in row] for row in LOGOS[size]])


def panel_layout(width: int, height: int) -> tuple[int, bool] | None:
    """(dial/logo size, show logo) that fits beside the 80-column table, or None to hide the panel."""
    if width >= 112 and height >= 41:
        return 28, True
    if width >= 104 and height >= 33:
        return 20, True
    if width >= 104 and height >= 22:
        return 20, False
    return None
