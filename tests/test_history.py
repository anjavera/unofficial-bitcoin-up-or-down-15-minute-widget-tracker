from datetime import datetime, timedelta, timezone

import pytest

from btc15_widget.history import fetch_window, load_history, with_retry
from btc15_widget.windows import event_slug

UTC = timezone.utc
NOW = datetime(2026, 9, 30, 8, 20, tzinfo=UTC)


def event(open_, close, status="MARKET_STATUS_RESOLVED"):
    terms = {"priceToBeat": {"value": str(open_)}}
    if close is not None:
        terms["settlementPrice"] = {"value": str(close)}
    return {"event": {"markets": [{"slug": "m", "status": status, "assetPriceTerms": terms}]}}


class FakeEvents:
    def __init__(self, fake):
        self.fake = fake

    def retrieve_by_slug(self, slug):
        self.fake.calls.append(slug)
        result = self.fake.responses.get(slug)
        if isinstance(result, Exception) or result is None:
            raise result or RuntimeError("404")
        return result


class FakeMarkets:
    def bbo(self, slug):
        return {"marketData": {"sharesTraded": "163510.71"}}


class FakeClient:
    def __init__(self, responses):
        self.responses, self.calls = responses, []
        self.events, self.markets = FakeEvents(self), FakeMarkets()


def nosleep(_):
    pass


def test_settled_window():
    start = datetime(2026, 9, 29, 9, 0, tzinfo=UTC)
    c = FakeClient({event_slug(start): event(83844.30, 83760.07)})
    w = fetch_window(c, start, sleep=nosleep)
    assert (w.open, w.close, w.result) == (83844.30, 83760.07, "DOWN")
    assert w.status == "RESOLVED"
    assert w.volume == pytest.approx(163510.71)


def test_live_window_has_no_close():
    start = datetime(2026, 9, 30, 8, 15, tzinfo=UTC)
    c = FakeClient({event_slug(start): event(84325.86, None, "MARKET_STATUS_OPEN")})
    w = fetch_window(c, start, sleep=nosleep)
    assert w.open == 84325.86 and w.close is None and w.result is None and w.error is None


def test_failed_window_is_gap_not_exception():
    start = datetime(2026, 9, 30, 8, 15, tzinfo=UTC)
    w = fetch_window(FakeClient({}), start, sleep=nosleep)
    assert w.error and w.open is None and w.start == start


def test_retry_backs_off_then_succeeds():
    attempts, sleeps = [], []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("1015")
        return "ok"

    assert with_retry(flaky, sleep=sleeps.append) == "ok"
    assert sleeps == [3, 6]


def settled_responses(n_hours=6):
    responses, start = {}, NOW.replace(minute=15, second=0) - timedelta(hours=n_hours)
    for i in range(n_hours * 4):
        s = start + timedelta(minutes=15 * i)
        responses[event_slug(s)] = event(100.0 + i, 101.0 + i)
    live = NOW.replace(minute=15, second=0)
    responses[event_slug(live)] = event(200.0, None, "MARKET_STATUS_OPEN")
    return responses


def test_load_history_length_and_order():
    ws = load_history(FakeClient(settled_responses()), NOW, hours=6, sleep=nosleep)
    assert len(ws) == 25
    assert [w.start for w in ws] == sorted(w.start for w in ws)
    assert ws[-1].start == datetime(2026, 9, 30, 8, 15, tzinfo=UTC)
    assert ws[-1].result is None


def test_cache_skips_settled_refetch(tmp_path):
    cache = tmp_path / "history.json"
    load_history(FakeClient(settled_responses()), NOW, hours=6, cache_path=cache, sleep=nosleep)
    second = FakeClient(settled_responses())
    ws = load_history(second, NOW, hours=6, cache_path=cache, sleep=nosleep)
    assert second.calls == [event_slug(NOW.replace(minute=15, second=0))]  # only the live window
    assert ws[0].settled and ws[0].close is not None


def test_one_bad_window_keeps_position():
    responses = settled_responses()
    bad_start = NOW.replace(minute=15, second=0) - timedelta(hours=6) + timedelta(minutes=15 * 5)
    responses[event_slug(bad_start)] = RuntimeError("boom")
    ws = load_history(FakeClient(responses), NOW, hours=6, sleep=nosleep)
    assert ws[5].error and ws[5].start == bad_start
    assert ws[6].start == bad_start + timedelta(minutes=15) and ws[6].settled


def test_outage_does_not_stall_for_minutes():
    sleeps = []
    ws = load_history(FakeClient({}), NOW, hours=6, sleep=sleeps.append)
    assert len(ws) == 25 and all(w.error for w in ws)
    assert sum(sleeps) < 120  # circuit breaker: later windows are tried once, no backoff
