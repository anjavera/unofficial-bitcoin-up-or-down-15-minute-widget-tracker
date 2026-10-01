import asyncio

import pytest

from btc15_widget.dashboard.feed import MultiMarketFeed, parse_market_data

BOOK = {
    "marketData": {
        "marketSlug": "crypto-eth-up",
        "bids": [{"px": {"value": "0.4000"}, "qty": "100"}, {"px": {"value": "0.3900"}, "qty": "50"}],
        "offers": [{"px": {"value": "0.4200"}, "qty": "80"}],
        "stats": {"lastTradePx": {"value": "0.4100"}},
    }
}


def test_parse_market_data():
    quote = parse_market_data(BOOK)
    assert quote.slug == "crypto-eth-up"
    assert (quote.best_bid, quote.best_ask, quote.last_trade) == (0.40, 0.42, 0.41)
    assert quote.bid_depth == 150 and quote.ask_depth == 80


def test_parse_market_data_with_empty_book():
    msg = {"marketData": {"marketSlug": "s", "bids": [], "offers": []}}
    quote = parse_market_data(msg)
    assert quote.best_bid is None and quote.best_ask is None and quote.last_trade is None
    assert quote.bid_depth == 0 and quote.ask_depth == 0


def test_parse_market_data_skips_malformed_levels():
    msg = {"marketData": {"marketSlug": "s", "bids": [{"px": {"value": "bad"}, "qty": "10"}], "offers": []}}
    quote = parse_market_data(msg)
    assert quote.bids == [] and quote.best_bid is None


def test_parse_ignores_other_messages():
    assert parse_market_data({"marketDataLite": {"marketSlug": "x"}}) is None
    assert parse_market_data({"heartbeat": {}}) is None


class FakeWS:
    instances: list["FakeWS"] = []

    def __init__(self, **kwargs):
        self.listeners, self.subscribed, self.closed = {}, [], False
        self.index = len(FakeWS.instances)
        FakeWS.instances.append(self)

    def on(self, event, cb):
        self.listeners.setdefault(event, []).append(cb)

    def emit(self, event, *args):
        for cb in self.listeners.get(event, []):
            cb(*args)

    async def connect(self):
        pass

    async def subscribe_market_data(self, request_id, slugs):
        self.subscribed = slugs
        self.emit("close") if self.index == 0 else self.emit("message", BOOK)

    async def close(self):
        self.closed = True


async def no_sleep(_delay, _stop):
    pass


def make_feed(quotes, stop, get_slugs=lambda: ["crypto-eth-up"]):
    FakeWS.instances = []

    def on_quote(quote):
        quotes.append(quote)
        stop.set()

    return MultiMarketFeed(on_quote, get_slugs, ws_factory=FakeWS, creds=("id", "secret"), sleep=no_sleep)


def test_feed_reconnects_after_close():
    async def scenario():
        quotes, stop = [], asyncio.Event()
        await asyncio.wait_for(make_feed(quotes, stop).run(stop), timeout=5)
        return quotes

    quotes = asyncio.run(scenario())
    assert len(quotes) == 1 and quotes[0].best_bid == 0.40
    assert len(FakeWS.instances) == 2 and FakeWS.instances[0].closed


def test_feed_subscribes_whatever_get_slugs_returns_each_connection():
    seen = []

    def get_slugs():
        slugs = ["a", "b", "c"][: len(seen) + 1]
        seen.append(slugs)
        return slugs

    async def scenario():
        stop = asyncio.Event()
        await asyncio.wait_for(make_feed([], stop, get_slugs).run(stop), timeout=5)

    asyncio.run(scenario())
    assert FakeWS.instances[0].subscribed == ["a"]
    assert FakeWS.instances[1].subscribed == ["a", "b"]


def test_feed_waits_when_there_are_no_slugs_yet():
    calls = []

    async def record_sleep(delay, stop):
        calls.append(delay)
        stop.set()

    async def scenario():
        FakeWS.instances, stop = [], asyncio.Event()
        feed = MultiMarketFeed(lambda q: None, lambda: [], ws_factory=FakeWS, creds=("id", "s"), sleep=record_sleep)
        await asyncio.wait_for(feed.run(stop), timeout=5)

    asyncio.run(scenario())
    assert calls == [1.0]
    assert FakeWS.instances == []


def test_feed_stops_when_event_already_set():
    async def scenario():
        stop = asyncio.Event()
        stop.set()
        await asyncio.wait_for(make_feed([], stop).run(stop), timeout=5)

    asyncio.run(scenario())
    assert FakeWS.instances == []


class StayOpenWS(FakeWS):
    async def subscribe_market_data(self, request_id, slugs):
        self.subscribed = slugs
        self.emit("message", BOOK)
        # does not close or drop: stays "connected" until resubscribe/stop fires


def test_request_resubscribe_forces_a_clean_reconnect_without_backoff():
    async def scenario():
        FakeWS.instances, quotes, sleeps, stop = [], [], [], asyncio.Event()

        async def record_sleep(delay, _stop):
            sleeps.append(delay)

        feed = MultiMarketFeed(
            lambda q: quotes.append(q), lambda: ["a"], ws_factory=StayOpenWS, creds=("id", "s"), sleep=record_sleep
        )

        async def trigger_and_stop():
            await asyncio.sleep(0.05)
            feed.request_resubscribe()
            await asyncio.sleep(0.05)
            stop.set()

        await asyncio.wait_for(asyncio.gather(feed.run(stop), trigger_and_stop()), timeout=5)
        return quotes, sleeps

    quotes, sleeps = asyncio.run(scenario())
    assert len(FakeWS.instances) == 2  # resubscribe closed the first connection and opened a second
    assert sleeps == []  # a forced resubscribe is not treated as a failure/backoff
    assert len(quotes) == 2  # one quote delivered per connection
