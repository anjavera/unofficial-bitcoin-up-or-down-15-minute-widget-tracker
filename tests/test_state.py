from datetime import datetime, timedelta, timezone

import pytest

from btc15_widget.calibration import Calibration
from btc15_widget.model import LiveTick, Window
from btc15_widget.state import STALE_SECONDS, WidgetState
from btc15_widget.windows import MARKET_SLUG, floor_window

UTC = timezone.utc
NOW = datetime(2026, 9, 30, 9, 20, tzinfo=UTC)  # live window starts 09:15Z
STEP = timedelta(minutes=15)


def history(now=NOW, count=97, settled_until=None):
    """`count` windows ending at floor(now); all settled except the live one."""
    live = floor_window(now)
    out = []
    for i in range(count - 1, -1, -1):
        start = live - i * STEP
        is_live = i == 0
        out.append(Window(start, open=100.0 + i, close=None if is_live else 101.0 + i, status="OPEN" if is_live else "RESOLVED"))
    return out


def state_with(now=NOW, **kw):
    s = WidgetState(**kw)
    s.set_history(history(now), now)
    return s


def test_strip_windows_is_96_ending_before_live():
    strip = state_with().strip_windows(NOW)
    live = floor_window(NOW)
    assert len(strip) == 96
    assert strip[-1].start == live - STEP
    assert strip[0].start == live - timedelta(hours=24)


def test_strip_fills_missing_windows_in_place():
    ws = history()
    removed = ws.pop(10)
    s = WidgetState()
    s.set_history(ws, NOW)
    strip = s.strip_windows(NOW)
    assert len(strip) == 96
    cell = next(w for w in strip if w.start == removed.start)
    assert cell.open is None and cell.close is None
    starts = [w.start for w in strip]
    assert starts == sorted(starts) and len(set(starts)) == 96  # nothing shifted or duplicated


def test_rollover_keeps_previous_window_pending():
    loaded_at = datetime(2026, 9, 30, 9, 10, tzinfo=UTC)  # live window then was 09:00Z, unsettled
    s = WidgetState()
    s.set_history(history(loaded_at), loaded_at)
    now = datetime(2026, 9, 30, 9, 16, tzinfo=UTC)
    live = s.live_window(now)
    assert live.start == datetime(2026, 9, 30, 9, 15, tzinfo=UTC) and live.open is None
    strip = s.strip_windows(now)
    assert strip[-1].start == datetime(2026, 9, 30, 9, 0, tzinfo=UTC) and not strip[-1].settled


def quotes_state(calibration=None, age=0):
    s = state_with(calibration=calibration)
    s.apply_quotes({"a": 100.0, "b": 102.0}, NOW - timedelta(seconds=age))
    return s


def test_proxy_price_applies_bias_only_with_enough_samples():
    assert quotes_state(Calibration(n=8, bias=-4.0, mean_abs_error=4.0, max_abs_error=9.0)).proxy_price(NOW) == 105.0
    assert quotes_state(Calibration(n=3, bias=-4.0, mean_abs_error=4.0, max_abs_error=9.0)).proxy_price(NOW) == 101.0
    assert quotes_state().proxy_price(NOW) == 101.0


def test_proxy_price_none_when_stale_or_empty():
    assert quotes_state(age=STALE_SECONDS + 1).proxy_price(NOW) is None
    s = state_with()
    assert s.proxy_price(NOW) is None
    s.apply_quotes({}, NOW)
    assert s.proxy_price(NOW) is None


def test_gap_none_without_open_or_proxy():
    assert state_with().gap(NOW) is None  # no quotes yet
    s = WidgetState()
    s.set_history([Window(floor_window(NOW), open=None, close=None)], NOW)
    s.apply_quotes({"a": 105.0}, NOW)
    assert s.gap(NOW) is None  # live window has no price to beat


def test_gap_value():
    s = state_with()
    s.apply_quotes({"a": 105.0}, NOW)
    assert s.gap(NOW) == pytest.approx(5.0)  # live open is 100.0


def live_tick(price, start=None):
    slug = MARKET_SLUG.format(start or floor_window(NOW))
    return LiveTick(slug, price, price - 0.01, price + 0.01, price, 1.0)


def test_staleness_flags():
    s = state_with()
    assert s.is_stale("tick", NOW) and s.is_stale("quotes", NOW)
    s.apply_tick(live_tick(0.6), NOW - timedelta(seconds=3))
    assert not s.is_stale("tick", NOW)
    assert s.is_stale("tick", NOW + timedelta(seconds=30))


def test_live_tick_ignores_other_windows_ticks():
    s = state_with()
    s.apply_tick(live_tick(0.62), NOW)
    s.apply_tick(live_tick(0.50, floor_window(NOW) + STEP), NOW)  # next window's market, arrives last
    assert s.live_tick(NOW).up_price == 0.62
    later = NOW + timedelta(minutes=12)  # 09:32Z: the 09:30 window is now live
    assert s.live_tick(later).up_price == 0.50


def test_tick_for_a_different_window_is_not_a_fresh_live_tick():
    s = state_with()
    s.apply_tick(live_tick(0.50, floor_window(NOW) + STEP), NOW)
    assert s.live_tick(NOW) is None and s.is_stale("tick", NOW)


def test_old_ticks_are_pruned():
    s = state_with()
    s.apply_tick(live_tick(0.6), NOW)
    s.apply_tick(live_tick(0.7), NOW + timedelta(hours=2))
    assert len(s.ticks) == 1


def test_needs_refresh_rules():
    assert WidgetState().needs_history_refresh(NOW)  # empty
    assert not state_with().needs_history_refresh(NOW)  # fresh and complete
    # live window missing (clock rolled past the boundary)
    assert state_with().needs_history_refresh(datetime(2026, 9, 30, 9, 31, tzinfo=UTC))
    # an unsettled past window: refresh only once the last load is over 20 s old
    ws = history()
    ws[-2] = Window(ws[-2].start, open=100.0, close=None)
    s = WidgetState()
    s.set_history(ws, NOW - timedelta(seconds=25))
    assert s.needs_history_refresh(NOW)
    s.set_history(ws, NOW - timedelta(seconds=10))
    assert not s.needs_history_refresh(NOW)
    # complete history still refreshes after 300 s
    s.set_history(history(), NOW - timedelta(seconds=301))
    assert s.needs_history_refresh(NOW)


def test_table_windows_are_the_strip_plus_the_live_window():
    s = state_with()
    rows = s.table_windows(NOW)
    assert len(rows) == 97
    assert rows[-1].start == floor_window(NOW) and rows[:-1] == s.strip_windows(NOW)
