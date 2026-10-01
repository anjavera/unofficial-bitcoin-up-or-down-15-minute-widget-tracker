"""Pure renderers: widget state in, rich Text out."""

import io
import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from rich import box
from rich.console import Console
from rich.style import Style
from rich.table import Table
from rich.text import Text

from btc15_widget.colors import BAND_EDGES, net_color, result_color, text_on
from btc15_widget.history import NO_MARKET
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
        text.append(f"{edge}{('+' if sign > 0 else '-') if edge == BAND_EDGES[-1] else ''} ")
    return text


def render_legend(theme: str, view: str = "strip") -> Text:
    text = Text()
    if view == "table":
        text.append("Result: ")
        text.append("UP", style=Style(color=result_color("UP", theme), bold=True))
        text.append(" green, ")
        text.append("DOWN", style=Style(color=result_color("DOWN", theme), bold=True))
        text.append(" red (filled once settled; UP?/DOWN? = live lean)\n")
        text.append("Chg $ and Chg % fill = net change: blue = up, orange = down, by size ($):\n")
    else:
        text.append("Cell ▌ left half = result: ")
        text.append("UP", style=Style(color=result_color("UP", theme)))
        text.append(" / ")
        text.append("DOWN", style=Style(color=result_color("DOWN", theme)))
        text.append(", right half = net change ($)\n")
    text.append("net up   ")
    text.append_text(_band_swatches(theme, +1))
    text.append("\nnet down ")
    text.append_text(_band_swatches(theme, -1))
    note = ("-  unsettled   none  no market   gap  fetch failed   ≈  exchange estimate" if view == "table"
            else "?  pending (not yet settled)   ·  gap (fetch failed)")
    text.append(f"\n{note}", style=DIM)
    return text


def _signed_money(value: float) -> str:
    return f"{'+' if value >= 0 else '-'}${abs(value):,.2f}"


def _countdown(now: datetime, start: datetime) -> str:
    seconds = math.ceil(seconds_remaining(now, start))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def render_header(state: WidgetState, now: datetime, theme: str) -> Text:
    live = state.live_window(now)
    price, gap, source = state.live_price(now), state.gap(now), state.price_source(now)
    if price is not None:
        price_text = f"${price:,.2f}"
    else:
        price_text = "stale" if state.quotes_at is not None and state.is_stale("quotes", now) else "—"
    if source == "index":  # the official index is exact: no estimate marker, no error margin
        approx, error = "", " (Polymarket index)"
    else:
        approx = "≈ "
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
    text.append(f"BTC {approx}{price_text}{error}  beat {beat}  gap {gap_text}  ends in {_countdown(now, live.start)}\n")
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
    mode = f" ({state.feed_mode})" if state.feed_mode else ""
    market = state.market_state_label(now)
    market = f" · market {market}" if market else ""
    if state.price_source(now) == "index":
        age = f"price: index {max(0, int((now - state.index_at).total_seconds()))}s ago"
    else:
        age = f"quotes {age}"
    text = Text(f"feed: {state.feed_status}{mode}{market} · {age}  ", style=DIM)
    text.append("Signals: off (see data/patterns.md)", style=DIM)
    if state.loading and not state.windows:
        text.append("\nloading 24h history… (first run takes a few minutes; later runs are cached)")
    if state.error:
        text.append(f"\nError: {state.error}")
    return text


# ---- table (shared by `pm btc15` and the live widget) ---------------------------------------------
COLUMN_WIDTHS = {"Window (ET)": 19, "Open": 12, "Close": 14, "Chg $": 11, "Chg %": 10, "Result": 7, "Volume": 11}
ZEBRA = {"dark": "#e6edf3 on #161b22"}  # own text colour: readable whatever the terminal's own colours
VOLUME_MIN_TERMINAL_WIDTH = 92


def _table_cell(text: str, width: int, align: str = ">", style: Style | None = None) -> Text:
    """A cell padded to its full column width so a fill colour covers the whole cell."""
    return Text(f" {text:{align}{width - 2}} ", style=style or Style())


def build_table(windows: list[Window], theme: str, volume: bool = True,
                live_start: datetime | None = None, live_price: float | None = None) -> Table:
    """Grid table: Chg $ / Chg % filled with the blue/orange net gradient, Result filled green/red.

    The window starting at `live_start` (if unsettled) shows `live_price` as a provisional close: its change
    cells get the gradient and Result shows the lean (UP?/DOWN?) without a fill, until Polymarket settles it.
    """
    width = COLUMN_WIDTHS
    columns = [c for c in width if volume or c != "Volume"]
    table = Table(box=box.SQUARE, padding=0, pad_edge=False, show_lines=False,
                  row_styles=["", ZEBRA[theme]], border_style="grey50", header_style="bold")
    for name in columns:
        table.add_column(name, width=width[name], no_wrap=True, justify="center")
    dim = Style(dim=True)
    fmt = lambda v: f"{v:,.2f}" if v is not None else "-"
    for w in windows:
        t = w.start.astimezone(ET)
        label = f"{t:%m-%d %H:%M}-{(t + timedelta(minutes=15)):%H:%M}"
        close_text = fmt(w.close)
        empty = (_table_cell("-", width["Chg $"], style=dim), _table_cell("-", width["Chg %"], style=dim))
        is_live = live_start is not None and w.start == live_start and not w.settled and not w.error
        if w.error:
            result = _table_cell("none" if w.error == NO_MARKET else "gap", width["Result"], "^", dim)
            chg, pct = empty
        elif w.net is not None or (is_live and live_price is not None and w.open is not None):
            provisional = w.net is None
            net = live_price - w.open if provisional else w.net
            fill = net_color(net, theme)
            style = Style(color=text_on(fill), bgcolor=fill)
            chg = _table_cell(f"{net:+,.2f}", width["Chg $"], style=style)
            pct = _table_cell(f"{net / w.open * 100:+.3f}%", width["Chg %"], style=style)
            outcome = "UP" if net >= 0 else "DOWN"
            if provisional:
                close_text = f"≈ {live_price:,.2f}"
                result = _table_cell(f"{outcome}?", width["Result"], "^", Style(color=result_color(outcome, theme), bold=True))
            else:
                mark = result_color(outcome, theme)
                result = _table_cell(outcome, width["Result"], "^", Style(color=text_on(mark), bgcolor=mark, bold=True))
        else:
            live = w.status in ("OPEN", "ACTIVE", "")
            result = _table_cell("LIVE" if live else "-", width["Result"], "^", dim)
            chg, pct = empty
        row = {
            "Window (ET)": _table_cell(label, width["Window (ET)"], "<"),
            "Open": _table_cell(fmt(w.open), width["Open"]), "Close": _table_cell(close_text, width["Close"]),
            "Chg $": chg, "Chg %": pct, "Result": result,
            "Volume": _table_cell(f"{w.volume:,.0f}" if w.volume else "-", width["Volume"]),
        }
        table.add_row(*(row[c] for c in columns))
    return table


def split_table(table: Table) -> tuple[Text, Text]:
    """Render `table` into (header, rows): the top border + column names + separator, and everything below.

    Both are styled `Text` of identical width, so the header can be pinned above a scrolling body.
    """
    width = sum(c.width or 0 for c in table.columns) + len(table.columns) + 1
    console = Console(width=width, file=io.StringIO(), color_system="truecolor", force_terminal=True)
    lines = console.render_lines(table, console.options.update(width=width), pad=False)

    def as_text(line) -> Text:
        text = Text(no_wrap=True)
        for segment in line:
            if segment.text:
                text.append(segment.text, segment.style)
        return text

    head, body = lines[:3], lines[3:]
    return Text("\n").join(as_text(line) for line in head), Text("\n").join(as_text(line) for line in body)


def print_table(windows: list[Window], theme: str = "dark") -> None:
    console = Console()
    console.print("BTC 15-min Up/Down — all times ET, prices are BRTI (Chg columns: blue = up, orange = down)", style="bold")
    show_volume = console.width >= VOLUME_MIN_TERMINAL_WIDTH and any(w.volume for w in windows)
    console.print(build_table(windows, theme, volume=show_volume))
    settled = [w for w in windows if w.settled]
    ups = sum(w.result == "UP" for w in windows)
    downs = sum(w.result == "DOWN" for w in windows)
    if settled:
        lo = min(min(w.open, w.close) for w in settled)
        hi = max(max(w.open, w.close) for w in settled)
        net = settled[-1].close - settled[0].open
        console.print(f"{ups} up / {downs} down   range ${lo:,.2f} – ${hi:,.2f}   net {net:+,.2f}", highlight=False)
