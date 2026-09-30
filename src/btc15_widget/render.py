"""Pure renderers: widget state in, rich Text out."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from rich.style import Style
from rich.text import Text

from btc15_widget.colors import BAND_EDGES, net_color, result_color
from btc15_widget.model import Window

ET = ZoneInfo("America/New_York")
CELLS_PER_ROW = 24
DIM = Style(dim=True)


def _cell(window: Window, theme: str) -> tuple[str, Style]:
    if window.error:
        return "·", DIM
    if not window.settled:
        return "?", DIM
    return "▌", Style(color=result_color(window.result, theme), bgcolor=net_color(window.net, theme))


def render_strip(windows: list[Window], theme: str) -> Text:
    """Rows of 24 cells, oldest first; left half = result colour, right half = net-change colour."""
    text = Text()
    for i in range(0, len(windows), CELLS_PER_ROW):
        row = windows[i : i + CELLS_PER_ROW]
        if i:
            text.append("\n")
        text.append(f"{row[0].start.astimezone(ET):%m-%d %H:%M} ")
        for window in row:
            glyph, style = _cell(window, theme)
            text.append(glyph, style=style)
    return text


def _band_swatches(theme: str, sign: int) -> Text:
    text = Text()
    lowers = (0, *BAND_EDGES[:-1])
    for lower, edge in zip(lowers, BAND_EDGES):
        mid = (lower + edge) / 2
        text.append("█", style=Style(color=net_color(sign * mid, theme)))
        text.append(f"{edge}{'+' if edge == BAND_EDGES[-1] else ''} ")
    return text


def render_legend(theme: str) -> Text:
    text = Text()
    text.append("Cell ▌  left half = result: ")
    text.append("UP", style=Style(color=result_color("UP", theme)))
    text.append(" / ")
    text.append("DOWN", style=Style(color=result_color("DOWN", theme)))
    text.append("   right half = net change ($, bands by size)\n")
    text.append("net up   ")
    text.append_text(_band_swatches(theme, +1))
    text.append("\nnet down ")
    text.append_text(_band_swatches(theme, -1))
    text.append("\n?  pending (not yet settled)   ·  gap (fetch failed)", style=DIM)
    return text
