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
