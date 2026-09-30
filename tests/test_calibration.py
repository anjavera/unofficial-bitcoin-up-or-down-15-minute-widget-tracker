from datetime import datetime, timezone

import pytest

from btc15_widget.calibration import Calibration, fetch_candles, measure
from btc15_widget.model import Window

T1 = datetime(2026, 9, 30, 9, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 9, 30, 9, 15, tzinfo=timezone.utc)


def minute_before(t):
    return int(t.timestamp()) - 60


def test_measure_known_errors():
    windows = [Window(T1, open=100.0, close=101.0), Window(T2, open=200.0, close=201.0)]
    candles = {
        "a": {minute_before(T1): 96.0, minute_before(T2): 194.0},
        "b": {minute_before(T1): 96.0, minute_before(T2): 194.0},
    }
    cal = measure(windows, candles)
    assert cal == Calibration(n=2, bias=-5.0, mean_abs_error=5.0, max_abs_error=6.0)


def test_measure_skips_windows_without_open_or_candles():
    windows = [Window(T1, open=None, close=None), Window(T2, open=200.0, close=None)]
    candles = {"a": {minute_before(T2): 194.0}, "b": {}}
    cal = measure(windows, candles)
    assert cal.n == 1 and cal.bias == -6.0


def test_measure_none_when_empty():
    assert measure([Window(T1, open=100.0, close=None)], {"a": {}}) is None
    assert measure([], {}) is None


def test_fetch_candles_parses_each_exchange_and_skips_failures():
    t = 1_790_000_040
    o, h, l, c = 100.0, 110.0, 90.0, 104.0  # typical price = 101.0

    def get_json(url):
        if "coinbase" in url:
            return [[t, l, h, o, c, 1.0]]
        if "kraken" in url:
            return {"result": {"XXBTZUSD": [[t, str(o), str(h), str(l), str(c), "0", "1", 1]], "last": t}}
        if "bitstamp" in url:
            return {"data": {"ohlc": [{"timestamp": str(t), "open": str(o), "high": str(h), "low": str(l), "close": str(c)}]}}
        raise OSError("gemini down")

    out = fetch_candles(datetime.fromtimestamp(t - 600, timezone.utc), datetime.fromtimestamp(t + 600, timezone.utc), get_json)
    assert set(out) == {"coinbase", "kraken", "bitstamp"}  # gemini failed and is skipped
    assert all(v == {t: 101.0} for v in out.values())


def test_fetch_candles_gemini_uses_milliseconds():
    t = 1_790_000_040
    out = fetch_candles(
        datetime.fromtimestamp(t - 600, timezone.utc), datetime.fromtimestamp(t + 600, timezone.utc),
        lambda url: [[t * 1000, 100.0, 110.0, 90.0, 104.0, 1.0]] if "gemini" in url else (_ for _ in ()).throw(OSError()),
    )
    assert out == {"gemini": {t: 101.0}}
