"""Pure renderers: widget state in, rich Text out."""

import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from rich.style import Style
from rich.text import Text

from btc15_widget.colors import BAND_EDGES, net_color, result_color
from btc15_widget.model import Window
from btc15_widget.state import WidgetState
from btc15_widget.windows import seconds_remaining

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
    text.append("Cell ▌ left half = result: ")
    text.append("UP", style=Style(color=result_color("UP", theme)))
    text.append(" / ")
    text.append("DOWN", style=Style(color=result_color("DOWN", theme)))
    text.append(", right half = net change ($)\n")
    text.append("net up   ")
    text.append_text(_band_swatches(theme, +1))
    text.append("\nnet down ")
    text.append_text(_band_swatches(theme, -1))
    text.append("\n?  pending (not yet settled)   ·  gap (fetch failed)", style=DIM)
    return text


def _signed_money(value: float) -> str:
    return f"{'+' if value >= 0 else '-'}${abs(value):,.2f}"


def _countdown(now: datetime, start: datetime) -> str:
    seconds = math.ceil(seconds_remaining(now, start))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def render_header(state: WidgetState, now: datetime, theme: str) -> Text:
    live = state.live_window(now)
    price, gap = state.proxy_price(now), state.gap(now)
    if price is not None:
        price_text = f"${price:,.2f}"
    else:
        price_text = "stale" if state.quotes_at is not None and state.is_stale("quotes", now) else "—"
    error = f" (±${state.calibration.mean_abs_error:.1f})" if state.calibration else ""
    beat = f"${live.open:,.2f}" if live.open is not None else "—"
    gap_text = "—" if gap is None else f"{_signed_money(gap)} ({'UP' if gap >= 0 else 'DOWN'})"

    tick = state.live_tick(now)
    if tick is None:
        up = down = spread = "—"
    elif state.is_stale("tick", now):
        up = down = "stale"
        spread = "—"
    else:
        up = "—" if tick.up_price is None else f"{tick.up_price:.2f}"
        down = "—" if tick.up_price is None else f"{1 - tick.up_price:.2f}"
        spread = "—" if tick.spread is None else f"{tick.spread:.2f}"

    text = Text()
    text.append(f"BTC ≈ {price_text}{error}  beat {beat}  gap {gap_text}  ends in {_countdown(now, live.start)}\n")
    text.append(f"Up {up}  Down {down}  spread {spread}   ")
    text.append("provisional ", style=DIM)
    if gap is None:
        text.append("—", style=DIM)
    else:
        text.append("▌", style=Style(color=result_color("UP" if gap >= 0 else "DOWN", theme),
                                      bgcolor=net_color(gap, theme), dim=True))
    return text


def render_status(state: WidgetState, now: datetime, theme: str) -> Text:
    age = "—" if state.quotes_at is None else f"{max(0, int((now - state.quotes_at).total_seconds()))}s ago"
    text = Text(f"feed: {state.feed_status} · quotes {age}  ", style=DIM)
    text.append("Signals: off (see data/patterns.md)", style=DIM)
    if state.loading and not state.windows:
        text.append("\nloading 24h history… (first run takes a few minutes; later runs are cached)")
    if state.error:
        text.append(f"\nError: {state.error}")
    return text
