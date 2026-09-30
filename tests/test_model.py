from datetime import datetime, timedelta, timezone

import pytest

from btc15_widget.model import LiveTick, Window

T0 = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)


def test_result_up_when_close_equals_open():
    w = Window(start=T0, open=100.0, close=100.0)
    assert w.result == "UP"
    assert w.net == 0.0


def test_result_up_and_down():
    assert Window(start=T0, open=100.0, close=101.5).result == "UP"
    down = Window(start=T0, open=100.0, close=90.0)
    assert down.result == "DOWN"
    assert down.net == -10.0


def test_unsettled_window_has_no_net_or_result():
    w = Window(start=T0, open=100.0, close=None)
    assert w.net is None
    assert w.result is None
    assert w.settled is False


def test_end_is_start_plus_15_minutes():
    assert Window(start=T0, open=None, close=None).end == T0 + timedelta(minutes=15)


def test_spread():
    tick = LiveTick(slug="s", up_price=0.955, best_bid=0.95, best_ask=0.96, last_trade=0.95, shares_traded=1.0)
    assert tick.spread == pytest.approx(0.01)
    assert LiveTick(slug="s", up_price=None, best_bid=None, best_ask=0.96, last_trade=None, shares_traded=None).spread is None
