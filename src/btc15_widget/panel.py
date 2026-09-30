"""Side panel: an ASCII coin (a white $ "B" inside a ring of orange *) whose ring is the analog countdown.

One lap of the ring is one 15-minute window, clockwise from 12. Orange is time left; the arc already used takes
the colour of the current lean (green for UP, red for DOWN) and a white * marks the hand.
"""

import math

from rich.style import Style
from rich.text import Text

from btc15_widget.colors import result_color

WINDOW_SECONDS = 900.0
TAU = 2 * math.pi
COIN_ROWS, COIN_COLS = 15, 31
RADIUS = 7.45  # in row units: a text cell is about twice as tall as it is wide, so columns count half
RING_INNER, RING_OUTER = 1.05, 0.3
ORANGE = "#f7931a"
USED_WITHOUT_LEAN = "#9a6a2a"
B_GLYPH = [
    "   $  $    ",
    " $$$$$$$$  ",
    " $$$   $$$ ",
    " $$$    $$$",
    " $$$   $$$ ",
    " $$$$$$$$  ",
    " $$$   $$$ ",
    " $$$    $$$",
    " $$$   $$$ ",
    " $$$$$$$$  ",
    "   $  $    ",
]
B_TOP, B_LEFT = 2, 10


def coin_cells(elapsed: float) -> list[list[tuple[str, str]]]:
    """(character, kind) for every cell; kinds: space, b, ring_left, ring_used, hand (elapsed is 0..1)."""
    elapsed = min(max(elapsed, 0.0), 1.0)
    angle = TAU * elapsed
    cy, cx = (COIN_ROWS - 1) / 2, (COIN_COLS - 1) / 2
    grid = [[(" ", "space")] * COIN_COLS for _ in range(COIN_ROWS)]
    ring = []
    for r in range(COIN_ROWS):
        for c in range(COIN_COLS):
            x, y = (c - cx) / 2, r - cy
            dist = math.hypot(x, y)
            if RADIUS - RING_INNER <= dist <= RADIUS + RING_OUTER:
                ring.append((r, c, math.atan2(x, -y) % TAU, dist))
            else:
                br, bc = r - B_TOP, c - B_LEFT
                if 0 <= br < len(B_GLYPH) and 0 <= bc < len(B_GLYPH[0]) and B_GLYPH[br][bc] == "$":
                    grid[r][c] = ("$", "b")
    hand = min(ring, key=lambda cell: (abs((cell[2] - angle + math.pi) % TAU - math.pi), -cell[3]))
    for r, c, theta, _ in ring:
        kind = "hand" if (r, c) == hand[:2] else ("ring_used" if theta < angle else "ring_left")
        grid[r][c] = ("*", kind)
    return grid


def render_coin(remaining: float, lean: str | None, theme: str) -> Text:
    """The coin as styled text; `lean` is "UP", "DOWN" or None (no price yet)."""
    elapsed = 1 - min(max(remaining, 0.0), WINDOW_SECONDS) / WINDOW_SECONDS
    dark = theme == "dark"
    ink = "#ffffff" if dark else "#1f2328"  # white on a dark terminal; a white B would vanish on a light one
    styles = {
        "space": Style(),
        "b": Style(color=ink, bold=True),
        "ring_left": Style(color=ORANGE),
        "ring_used": Style(color=result_color(lean, theme) if lean else USED_WITHOUT_LEAN),
        "hand": Style(color=ink, bold=True),
    }
    lines = []
    for row in coin_cells(elapsed):
        line = Text(no_wrap=True)
        for char, kind in row:
            line.append(char, styles[kind])
        lines.append(line)
    return Text("\n").join(lines)


def panel_layout(width: int, height: int) -> bool:
    """True when the coin fits beside the 80-column table and its scrollbar."""
    return width >= 116 and height >= 28
