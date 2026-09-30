from datetime import datetime, timedelta, timezone

import pytest

from btc15_widget import client
from btc15_widget.model import Window
from btc15_widget.sources import CALIBRATION_EVERY, QUOTES_EVERY, DataSources, default_sources, run_calibration
from btc15_widget.state import WidgetState
from btc15_widget.windows import floor_window

UTC = timezone.utc
NOW = datetime(2026, 9, 30, 9, 20, tzinfo=UTC)
STEP = timedelta(minutes=15)


def history():
    live = floor_window(NOW)
    return [Window(live - i * STEP, open=84000.0 + i, close=None if i == 0 else 84001.0 + i) for i in range(96, -1, -1)]


def fake_sources(candles_fn=None, calls=None):
    def fetch_candles(start, end):
        if calls is not None:
            calls.append((start, end))
        if candles_fn is None:
            raise OSError("down")
        return candles_fn()

    return DataSources(
        load_history=lambda now: history(),
        fetch_quotes=lambda: {"a": 84000.0},
        fetch_candles=fetch_candles,
        feed_factory=lambda on_tick: None,
    )


def candles_4_below_open():
    """Every window's minute-before candle sits $4 below the window's BRTI open (two exchanges agree)."""
    series = {int(w.start.timestamp()) - 60: w.open - 4.0 for w in history()}
    return {"a": dict(series), "b": dict(series)}


def test_constants():
    assert CALIBRATION_EVERY == 1800 and QUOTES_EVERY == 2.0


def test_default_sources_needs_credentials(monkeypatch):
    monkeypatch.delenv("POLYMARKET_KEY_ID", raising=False)
    monkeypatch.delenv("POLYMARKET_SECRET_KEY", raising=False)
    monkeypatch.setattr(client, "load_dotenv", lambda *a, **k: False)
    with pytest.raises(RuntimeError, match="POLYMARKET_KEY_ID"):
        default_sources()


def test_run_calibration_uses_last_four_hours():
    state, calls = WidgetState(), []
    state.set_history(history(), NOW)
    cal = run_calibration(state, fake_sources(candles_4_below_open, calls), NOW)
    expected = sum(1 for w in history() if w.settled and w.start >= NOW - timedelta(hours=4))
    assert cal.n == expected and cal.bias == pytest.approx(-4.0)
    (start, end), = calls
    assert end - start <= timedelta(hours=4.5)  # Coinbase rejects ranges over 300 one-minute candles
    assert state.calibration is cal


def test_run_calibration_failure_keeps_state():
    state = WidgetState()
    state.set_history(history(), NOW)
    assert run_calibration(state, fake_sources(None), NOW) is None
    assert state.calibration is None


def test_run_calibration_with_no_usable_data_returns_none():
    state = WidgetState()
    state.set_history(history(), NOW)
    assert run_calibration(state, fake_sources(lambda: {"a": {}}), NOW) is None
    assert state.calibration is None


def test_widget_uses_its_own_cache_and_skips_volume(monkeypatch, tmp_path):
    from btc15_widget import sources as sources_module

    seen = {}

    class FakeApi:
        def close(self):
            pass

    monkeypatch.setattr(sources_module, "get_client", lambda: FakeApi())
    monkeypatch.setattr(sources_module, "load_history", lambda api, now, **kw: seen.update(kw) or [])
    default_sources().load_history(NOW)
    assert seen["with_volume"] is False
    assert seen["cache_path"] == sources_module.WIDGET_HISTORY_CACHE
    assert sources_module.WIDGET_HISTORY_CACHE != sources_module.HISTORY_CACHE  # the CLI cache keeps volumes
