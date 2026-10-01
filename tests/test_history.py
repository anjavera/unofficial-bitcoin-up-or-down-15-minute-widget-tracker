from datetime import datetime, timedelta, timezone

import pytest

from polymarket_us.errors import NotFoundError

from btc15_widget.history import NO_MARKET, fetch_window, load_history, with_retry
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

    def list(self, params):
        self.fake.list_calls.append(list(params["slug"]))
        if self.fake.list_error:
            raise self.fake.list_error
        found = []
        for slug in params["slug"]:
            result = self.fake.responses.get(slug)
            if result is None or isinstance(result, Exception):
                continue  # no such market
            found.append({**result["event"], "slug": slug})
        return {"events": found}

    def retrieve_by_slug(self, slug):
        self.fake.calls.append(slug)
        result = self.fake.responses.get(slug)
        if isinstance(result, Exception) or result is None:
            raise result or RuntimeError("404")
        return result


class FakeMarkets:
    def __init__(self):
        self.calls = []

    def bbo(self, slug):
        self.calls.append(slug)
        return {"marketData": {"sharesTraded": "163510.71"}}


class FakeClient:
    def __init__(self, responses, list_error=None):
        self.responses, self.calls, self.list_calls, self.list_error = responses, [], [], list_error
        self.events, self.markets = FakeEvents(self), FakeMarkets()


def nosleep(_):
    pass


def test_settled_window():
    start = datetime(2026, 9, 29, 9, 0, tzinfo=UTC)
    c = FakeClient({event_slug(start): event(83844.30, 83760.07)})
    w = fetch_window(c, start, sleep=nosleep, with_volume=True)
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


def test_volume_fetch_can_be_skipped():
    start = datetime(2026, 9, 29, 9, 0, tzinfo=UTC)
    c = FakeClient({event_slug(start): event(83844.30, 83760.07)})
    w = fetch_window(c, start, sleep=nosleep, with_volume=False)
    assert w.close == 83760.07 and w.volume is None and c.markets.calls == []
    ws = load_history(FakeClient(settled_responses()), NOW, hours=6, sleep=nosleep, with_volume=False)
    assert all(w.volume is None for w in ws)


# ---- bulk history: one request for many windows ---------------------------------------------------
def test_bulk_history_uses_a_single_request():
    c = FakeClient(settled_responses())
    ws = load_history(c, NOW, hours=6, sleep=nosleep)
    assert len(c.list_calls) == 1 and len(c.list_calls[0]) == 25 and c.calls == []  # no per-window requests
    assert len(ws) == 25 and [w.start for w in ws] == sorted(w.start for w in ws)
    assert ws[0].result == "UP" and ws[-1].result is None and ws[-1].status == "OPEN"


def test_bulk_history_chunks_large_ranges_to_100_slugs_per_request():
    c = FakeClient({})
    ws = load_history(c, NOW, hours=48, sleep=nosleep)
    assert len(ws) == 193 and len(c.list_calls) == 2 and all(len(batch) <= 100 for batch in c.list_calls)


def test_bulk_history_missing_market_is_a_gap_in_place():
    responses = settled_responses()
    missing = NOW.replace(minute=15, second=0) - timedelta(hours=6) + timedelta(minutes=15 * 5)
    del responses[event_slug(missing)]
    ws = load_history(FakeClient(responses), NOW, hours=6, sleep=nosleep)
    assert ws[5].error and ws[5].start == missing and ws[6].settled and ws[4].settled


def test_bulk_failure_falls_back_to_per_window_requests():
    c = FakeClient(settled_responses(), list_error=RuntimeError("filter not supported"))
    ws = load_history(c, NOW, hours=6, sleep=nosleep)
    assert len(ws) == 25 and ws[0].result == "UP" and len(c.calls) == 25


def test_cache_means_later_loads_only_request_what_is_new_or_unsettled(tmp_path):
    cache = tmp_path / "history.json"
    load_history(FakeClient(settled_responses()), NOW, hours=6, cache_path=cache, sleep=nosleep)
    second = FakeClient(settled_responses())
    load_history(second, NOW, hours=6, cache_path=cache, sleep=nosleep)
    assert second.list_calls == [[event_slug(NOW.replace(minute=15, second=0))]]  # just the live window


def test_volume_is_only_fetched_when_asked():
    c = FakeClient(settled_responses())
    ws = load_history(c, NOW, hours=1, sleep=nosleep)
    assert c.markets.calls == [] and all(w.volume is None for w in ws)
    c2 = FakeClient(settled_responses())
    ws2 = load_history(c2, NOW, hours=1, sleep=nosleep, with_volume=True)
    assert len(c2.markets.calls) == 5 and all(w.volume == pytest.approx(163510.71) for w in ws2)


def test_cached_windows_without_a_volume_are_refetched_when_volume_is_wanted(tmp_path):
    cache = tmp_path / "history.json"
    load_history(FakeClient(settled_responses()), NOW, hours=1, cache_path=cache, sleep=nosleep)  # cached with volume None
    c = FakeClient(settled_responses())
    ws = load_history(c, NOW, hours=1, cache_path=cache, sleep=nosleep, with_volume=True)
    assert all(w.volume == pytest.approx(163510.71) for w in ws)


def not_found():
    err = NotFoundError.__new__(NotFoundError)
    Exception.__init__(err, "The server was unable to process your request.")
    return err


def test_a_missing_market_is_labelled_as_no_market_in_the_bulk_path():
    ws = load_history(FakeClient({}), NOW, hours=1, sleep=nosleep)
    assert all(w.error == NO_MARKET for w in ws) and NO_MARKET == "no such market"


def test_not_found_is_not_retried_and_is_labelled_no_market():
    sleeps, calls = [], []

    def boom():
        calls.append(1)
        raise not_found()

    with pytest.raises(NotFoundError):
        with_retry(boom, tries=4, sleep=sleeps.append)
    assert calls == [1] and sleeps == []  # a 404 will not change by asking again right away

    class Client404:
        class events:
            @staticmethod
            def retrieve_by_slug(slug):
                raise not_found()

    w = fetch_window(Client404(), datetime(2026, 9, 29, 9, 0, tzinfo=UTC), sleep=sleeps.append)
    assert w.error == NO_MARKET and sleeps == []
