from datetime import datetime, timedelta, timezone

import pytest
from rich.color import Color
from rich.console import Console

from btc15_widget.colors import net_color, result_color
from btc15_widget.model import Window
from btc15_widget.render import CELLS_PER_ROW, render_legend, render_strip

UTC = timezone.utc
T0 = datetime(2026, 9, 29, 13, 0, tzinfo=UTC)  # 09:00 ET
PREFIX = len("09-29 09:00 ")


def windows(n=96, **kw):
    return [Window(T0 + timedelta(minutes=15 * i), open=100.0, close=110.0, **kw) for i in range(n)]


def style_at(text, row, col):
    offset = sum(len(line) + 1 for line in text.plain.split("\n")[:row]) + PREFIX + col
    return text.get_style_at_offset(Console(), offset), text.plain[offset]


def hex_of(color: Color) -> str:
    return color.get_truecolor().hex


def test_strip_layout():
    text = render_strip(windows(), "dark")
    lines = text.plain.split("\n")
    assert CELLS_PER_ROW == 24
    assert len(lines) == 4 and all(len(line) == PREFIX + 24 for line in lines)


def test_first_prefix_is_eastern_time():
    assert render_strip(windows(), "dark").plain.startswith("09-29 09:00 ")


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_settled_cell_uses_result_fg_and_net_bg(theme):
    ws = windows()
    ws[0] = Window(T0, open=100.0, close=150.0)       # UP, net +50
    ws[1] = Window(T0 + timedelta(minutes=15), open=400.0, close=100.0)  # DOWN, net -300
    text = render_strip(ws, theme)
    up, glyph = style_at(text, 0, 0)
    assert glyph == "▌"
    assert hex_of(up.color) == result_color("UP", theme) and hex_of(up.bgcolor) == net_color(50, theme)
    down, _ = style_at(text, 0, 1)
    assert hex_of(down.color) == result_color("DOWN", theme) and hex_of(down.bgcolor) == net_color(-300, theme)


def test_pending_and_gap_cells_are_dim_and_uncoloured():
    ws = windows()
    ws[0] = Window(T0, open=None, close=None)
    ws[1] = Window(T0 + timedelta(minutes=15), open=None, close=None, error="boom")
    text = render_strip(ws, "dark")
    pending, g0 = style_at(text, 0, 0)
    gap, g1 = style_at(text, 0, 1)
    assert (g0, g1) == ("?", "·")
    assert pending.dim and gap.dim
    assert pending.bgcolor is None and gap.bgcolor is None


def test_legend_lists_all_bands():
    plain = render_legend("dark").plain
    for edge in ("10", "25", "50", "100", "200", "300", "400", "500", "1000"):
        assert edge in plain
    assert "UP" in plain and "DOWN" in plain


# ---- header and status -------------------------------------------------------------------------
from btc15_widget.calibration import Calibration
from btc15_widget.model import LiveTick
from btc15_widget.render import render_header, render_status
from btc15_widget.state import WidgetState
from btc15_widget.windows import MARKET_SLUG, floor_window

NOW = datetime(2026, 9, 30, 9, 20, tzinfo=UTC)  # live window starts 09:15Z
LIVE = floor_window(NOW)


def full_state(open_=83874.16, quote=83874.95, quote_age=0, tick_age=0, calibrated=True):
    s = WidgetState()
    s.set_history([Window(LIVE, open=open_, close=None, status="OPEN")], NOW)
    if quote is not None:
        s.apply_quotes({"a": quote}, NOW - timedelta(seconds=quote_age))
    s.apply_tick(LiveTick(MARKET_SLUG.format(LIVE), 0.62, 0.61, 0.62, 0.62, 10.0), NOW - timedelta(seconds=tick_age))
    if calibrated:
        s.calibration = Calibration(n=3, bias=-4.0, mean_abs_error=4.5, max_abs_error=9.0)  # n<8: bias not applied
    s.feed_status = "live"
    return s


def header(state, now=NOW, theme="dark"):
    return render_header(state, now, theme).plain


def test_header_full():
    out = header(full_state())
    for piece in ("≈ $83,874.95", "(±$4.5)", "beat $83,874.16", "gap +$0.79 (UP)", "ends in 10:00",
                  "Up 0.62  Down 0.38", "spread 0.01", "provisional"):
        assert piece in out, piece


def test_header_down_gap_sign():
    assert "gap -$12.16 (DOWN)" in header(full_state(quote=83862.00))


def test_provisional_block_uses_gap_colours():
    text = render_header(full_state(quote=83862.00), NOW, "dark")
    offset = text.plain.index("▌")
    style = text.get_style_at_offset(Console(), offset)
    assert hex_of(style.color) == result_color("DOWN", "dark") and hex_of(style.bgcolor) == net_color(-12.16, "dark")


def test_header_no_open_shows_dash():
    out = header(full_state(open_=None))
    assert "beat —" in out and "gap —" in out and "None" not in out


def test_header_no_proxy_shows_dash():
    out = header(full_state(quote=None))
    assert "≈ —" in out and "gap —" in out and "None" not in out


def test_stale_data_is_labelled_not_shown():
    out = header(full_state(quote_age=15, tick_age=30))
    assert "≈ stale" in out and "83,874.95" not in out
    assert "Up stale" in out and "0.62" not in out


def test_countdown_format():
    s = full_state()
    assert "ends in 10:00" in header(s, NOW)
    assert "ends in 00:01" in header(s, datetime(2026, 9, 30, 9, 29, 59, tzinfo=UTC))
    assert "ends in 15:00" in header(s, datetime(2026, 9, 30, 9, 30, tzinfo=UTC))  # the next window has begun


def test_status_shows_feed_error_and_signals_off():
    s = full_state(quote_age=2)
    s.error = "Missing credentials"
    out = render_status(s, NOW, "dark").plain
    assert "feed: live" in out and "quotes 2s ago" in out
    assert "Signals: off" in out and "Error: Missing credentials" in out


def test_status_explains_the_first_load_wait():
    s = WidgetState()
    s.loading = True
    out = render_status(s, NOW, "dark").plain
    assert "loading" in out and "first run" in out
    s.set_history([Window(LIVE, open=1.0, close=None)], NOW)
    assert "loading" not in render_status(s, NOW, "dark").plain  # once history exists the note is gone


def test_text_blocks_fit_the_minimum_terminal_width():
    from btc15_widget.app import MIN_WIDTH

    s = full_state()
    s.apply_quotes({"a": 100123.45}, NOW)  # widest realistic price
    s.set_history([Window(LIVE, open=99000.12, close=None, status="OPEN")], NOW)
    s.feed_status = "reconnecting"
    blocks = [render_header(s, NOW, "dark"), render_legend("dark"), render_status(s, NOW, "dark")]
    for block in blocks:
        for line in block.plain.split("\n"):
            assert len(line) <= MIN_WIDTH, (len(line), line)
