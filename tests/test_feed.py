import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from polymarket_us.errors import NotFoundError

from btc15_widget.feed import NO_MARKET_RETRY, PollingFeed, NoQuote, parse_bbo, parse_book, parse_event_quote, parse_lite
from btc15_widget.windows import MARKET_SLUG, floor_window

UTC = timezone.utc
T0 = datetime(2026, 9, 30, 9, 20, tzinfo=UTC)


def book_response(slug, bids=("0.9500", "0.9400"), offers=("0.9600", "0.9700"), last="0.9500", shares="81932.6000"):
    level = lambda px: {"px": {"value": px, "currency": "USD"}, "qty": "10.0000"}
    stats = {"lastTradePx": {"value": last, "currency": "USD"}, "sharesTraded": shares} if last else {}
    return {"marketData": {"marketSlug": slug, "state": "MARKET_STATE_OPEN", "stats": stats,
                           "bids": [level(px) for px in bids], "offers": [level(px) for px in offers]}}


def test_parse_book_takes_the_top_of_book_and_the_midpoint():
    tick = parse_book(book_response("cpc-btc-updown-15m-2026-09-30-0900z"))
    assert tick.slug == "cpc-btc-updown-15m-2026-09-30-0900z"
    assert (tick.best_bid, tick.best_ask, tick.last_trade) == (0.95, 0.96, 0.95)
    assert tick.up_price == pytest.approx(0.955)  # midpoint of 0.95 / 0.96
    assert tick.shares_traded == 81932.6 and tick.spread == pytest.approx(0.01)


def test_parse_book_does_not_assume_the_levels_are_sorted():
    tick = parse_book(book_response("s", bids=("0.2100", "0.2300", "0.2200"), offers=("0.2700", "0.2500", "0.2600")))
    assert (tick.best_bid, tick.best_ask) == (0.23, 0.25)


def test_parse_book_one_sided_book_falls_back_to_the_last_trade():
    tick = parse_book(book_response("s", bids=(), offers=("0.9600",), last="0.9500"))
    assert tick.best_bid is None and tick.best_ask == 0.96 and tick.up_price == 0.95 and tick.spread is None


def test_parse_book_empty_market_has_no_prices_but_is_not_an_error():
    tick = parse_book(book_response("s", bids=(), offers=(), last=None))
    assert tick.up_price is None and tick.best_bid is None and tick.last_trade is None and tick.shares_traded is None


@pytest.mark.parametrize("bad", [{}, {"marketData": None}, {"marketData": {}}, None])
def test_parse_book_rejects_malformed_responses(bad):
    with pytest.raises(ValueError):
        parse_book(bad)


def make_feed(fetch, ticks, clock=lambda: T0, sleeps=None, interval=2.0):
    async def sleep(delay, stop):
        if sleeps is not None:
            sleeps.append(delay)
        await asyncio.sleep(0)

    return PollingFeed(ticks.append, fetch, interval=interval, clock=clock, sleep=sleep)


def run_until(feed, ticks, count, timeout=5):
    async def scenario():
        stop = asyncio.Event()
        task = asyncio.create_task(feed.run(stop))
        for _ in range(500):
            if len(ticks) >= count:
                break
            await asyncio.sleep(0.005)
        stop.set()
        await asyncio.wait_for(task, timeout)

    asyncio.run(scenario())


def test_feed_polls_the_live_window_and_delivers_ticks():
    asked, ticks = [], []

    def fetch(slug):
        asked.append(slug)
        return book_response(slug)

    run_until(make_feed(fetch, ticks), ticks, 3)
    live_slug = MARKET_SLUG.format(floor_window(T0))
    assert set(asked) == {live_slug} and ticks[0].slug == live_slug and ticks[0].up_price == pytest.approx(0.955)


def test_feed_follows_the_rollover_to_the_next_window():
    now, asked, ticks = {"t": T0}, [], []

    def fetch(slug):
        asked.append(slug)
        now["t"] = T0 + timedelta(minutes=15)  # the clock crosses 09:30 after the first poll
        return book_response(slug)

    run_until(make_feed(fetch, ticks, clock=lambda: now["t"]), ticks, 3)
    assert asked[0].endswith("0915z") and asked[-1].endswith("0930z")


def test_feed_backs_off_on_failures_and_recovers():
    calls, ticks, sleeps = {"n": 0}, [], []

    def fetch(slug):
        calls["n"] += 1
        if calls["n"] <= 3:
            raise RuntimeError("Error 1015: rate limited")
        return book_response(slug)

    run_until(make_feed(fetch, ticks, sleeps=sleeps), ticks, 2)
    assert sleeps[:3] == [5, 10, 15]  # growing backoff
    assert sleeps[3] == 2.0  # a good answer returns to the normal rhythm


def test_feed_survives_a_malformed_response():
    calls, ticks = {"n": 0}, []

    def fetch(slug):
        calls["n"] += 1
        return {"unexpected": True} if calls["n"] == 1 else book_response(slug)

    run_until(make_feed(fetch, ticks), ticks, 1)
    assert len(ticks) >= 1


def test_backoff_wakes_immediately_on_stop():
    async def scenario():
        stop = asyncio.Event()
        feed = PollingFeed(lambda t: None, lambda slug: (_ for _ in ()).throw(RuntimeError("down")), clock=lambda: T0)
        task = asyncio.create_task(feed.run(stop))  # default sleep: would wait 5 s after the first failure
        await asyncio.sleep(0.1)
        stop.set()
        await asyncio.wait_for(task, 2)

    asyncio.run(scenario())


def test_feed_stops_when_event_already_set():
    async def scenario():
        stop = asyncio.Event()
        stop.set()
        await asyncio.wait_for(PollingFeed(lambda t: None, lambda s: book_response(s), clock=lambda: T0).run(stop), 2)

    asyncio.run(scenario())


def test_a_missing_market_is_polled_gently_not_with_growing_backoff():
    from polymarket_us.errors import NotFoundError

    def not_found(slug):
        err = NotFoundError.__new__(NotFoundError)
        Exception.__init__(err, "unable to process")
        raise err

    sleeps, ticks = [], []
    feed = make_feed(not_found, ticks, sleeps=sleeps)

    async def scenario():
        stop = asyncio.Event()
        task = asyncio.create_task(feed.run(stop))
        for _ in range(200):
            if len(sleeps) >= 4:
                break
            await asyncio.sleep(0.005)
        stop.set()
        await asyncio.wait_for(task, 5)

    asyncio.run(scenario())
    assert sleeps[:4] == [10, 10, 10, 10]  # steady, polite re-checks while the market does not exist


def test_parse_book_and_lite_carry_the_market_state():
    assert parse_book(book_response("s")).state == "MARKET_STATE_OPEN"
    lite = parse_lite({"marketDataLite": {"marketSlug": "s", "state": "MARKET_STATE_HALTED"}})
    assert lite.state == "MARKET_STATE_HALTED"
    assert parse_lite({"marketDataLite": {"marketSlug": "s"}}).state is None


def _not_found():
    err = NotFoundError.__new__(NotFoundError)
    Exception.__init__(err, "unable to process")
    return err


def bbo_response(slug, px="0.5250", bid="0.5200", ask="0.5300"):
    amount = lambda v: {"value": v, "currency": "USD"}
    return {"marketData": {"marketSlug": slug, "currentPx": amount(px), "bestBid": amount(bid), "bestAsk": amount(ask),
                           "lastTradePx": amount("0.5300"), "sharesTraded": "31134.0400", "state": "MARKET_STATE_OPEN"}}


def test_parse_bbo_reads_the_lightweight_quote():
    tick = parse_bbo(bbo_response("s"))
    assert (tick.slug, tick.up_price, tick.best_bid, tick.best_ask, tick.state) == ("s", 0.525, 0.52, 0.53, "MARKET_STATE_OPEN")
    with pytest.raises(ValueError):
        parse_bbo({"nope": 1})


def test_feed_uses_bbo_while_the_book_is_not_yet_published():
    """Polymarket lists a new window's book about two minutes after it opens; bbo answers sooner."""
    ticks, sleeps = [], []

    def book(slug):
        raise _not_found()

    feed = PollingFeed(ticks.append, book, fetch_bbo=lambda slug: bbo_response(slug), interval=0.0,
                       clock=lambda: T0, sleep=lambda d, s: _record(sleeps, d))
    run_until(feed, ticks, 2)
    assert ticks[0].up_price == pytest.approx(0.525) and sleeps[0] == 0.0  # normal pace, not the slow no-market retry


def test_feed_waits_gently_when_neither_book_nor_bbo_exist():
    ticks, sleeps = [], []
    feed = PollingFeed(ticks.append, lambda s: (_ for _ in ()).throw(_not_found()),
                       fetch_bbo=lambda s: (_ for _ in ()).throw(_not_found()), interval=0.0,
                       clock=lambda: T0, sleep=lambda d, s: _record(sleeps, d))

    async def scenario():
        stop = asyncio.Event()
        task = asyncio.create_task(feed.run(stop))
        for _ in range(200):
            if len(sleeps) >= 3:
                break
            await asyncio.sleep(0.005)
        stop.set()
        await asyncio.wait_for(task, 5)

    asyncio.run(scenario())
    assert ticks == [] and sleeps[:3] == [NO_MARKET_RETRY] * 3


async def _record(sleeps, delay):
    sleeps.append(delay)
    await asyncio.sleep(0)


def event_response(slug, bid="0.5800", ask="0.5900", status="MARKET_STATUS_OPEN"):
    amount = lambda v: {"value": v, "currency": "USD"}
    market = {"slug": slug, "status": status}
    if bid:
        market.update(bestBidQuote=amount(bid), bestAskQuote=amount(ask))
    return {"events": [{"slug": slug.removeprefix("cpc-"), "markets": [market]}]}


def test_parse_event_quote_uses_the_events_best_bid_and_ask():
    tick = parse_event_quote(event_response("cpc-x"), "cpc-x")
    assert (tick.up_price, tick.best_bid, tick.best_ask, tick.state) == (pytest.approx(0.585), 0.58, 0.59, "MARKET_STATE_OPEN")


@pytest.mark.parametrize("bad", [{"events": []}, {}, event_response("cpc-x", bid=None), event_response("cpc-other")])
def test_parse_event_quote_without_a_quote_raises_noquote(bad):
    with pytest.raises(NoQuote):
        parse_event_quote(bad, "cpc-x")


def test_feed_falls_through_book_then_bbo_then_the_event_quote():
    ticks = []

    def gone(slug):
        raise _not_found()

    feed = PollingFeed(ticks.append, gone, fetch_bbo=gone, fetch_event=lambda slug: event_response(slug),
                       interval=0.0, clock=lambda: T0, sleep=lambda d, s: _record([], d))
    run_until(feed, ticks, 2)
    assert ticks[0].up_price == pytest.approx(0.585)


def test_an_odd_book_response_still_backs_off_like_a_failure():
    sleeps, ticks = [], []
    feed = PollingFeed(ticks.append, lambda slug: {"garbage": 1}, fetch_bbo=lambda s: bbo_response(s),
                       interval=0.0, clock=lambda: T0, sleep=lambda d, s: _record(sleeps, d))

    async def scenario():
        stop = asyncio.Event()
        task = asyncio.create_task(feed.run(stop))
        for _ in range(200):
            if len(sleeps) >= 2:
                break
            await asyncio.sleep(0.005)
        stop.set()
        await asyncio.wait_for(task, 5)

    asyncio.run(scenario())
    assert ticks == [] and sleeps[:2] == [5, 10]  # growing backoff, bbo is not used to paper over a bad book
