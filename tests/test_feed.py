import asyncio

import pytest

from btc15_widget.feed import LiveFeed, parse_lite

LITE = {
    "marketDataLite": {
        "marketSlug": "cpc-btc-updown-15m-2026-09-30-0900z",
        "currentPx": {"value": "0.9550"},
        "lastTradePx": {"value": "0.9500"},
        "sharesTraded": "81932.6000",
        "bestAsk": {"value": "0.9600"},
        "bestBid": {"value": "0.9500"},
    }
}


def test_parse_lite():
    tick = parse_lite(LITE)
    assert tick.slug == "cpc-btc-updown-15m-2026-09-30-0900z"
    assert tick.up_price == 0.955
    assert (tick.best_bid, tick.best_ask, tick.last_trade) == (0.95, 0.96, 0.95)
    assert tick.shares_traded == 81932.6
    assert tick.spread == pytest.approx(0.01)


def test_parse_lite_null_prices():
    msg = {"marketDataLite": {**LITE["marketDataLite"], "bestBid": None, "currentPx": None}}
    tick = parse_lite(msg)
    assert tick.best_bid is None and tick.up_price is None and tick.spread is None


def test_parse_ignores_other_messages():
    assert parse_lite({"trade": {"marketSlug": "x"}}) is None
    assert parse_lite({"heartbeat": {}}) is None


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

    async def subscribe_market_data_lite(self, request_id, slugs):
        self.subscribed = slugs
        self.emit("close") if self.index == 0 else self.emit("message", LITE)

    async def close(self):
        self.closed = True


async def no_sleep(_delay, _stop):
    pass


def make_feed(ticks, stop):
    FakeWS.instances = []

    def on_tick(tick):
        ticks.append(tick)
        stop.set()

    return LiveFeed(on_tick, ws_factory=FakeWS, creds=("id", "secret"), sleep=no_sleep)


def test_feed_reconnects_after_close():
    async def scenario():
        ticks, stop = [], asyncio.Event()
        await asyncio.wait_for(make_feed(ticks, stop).run(stop), timeout=5)
        return ticks

    ticks = asyncio.run(scenario())
    assert len(ticks) == 1 and ticks[0].up_price == 0.955
    assert len(FakeWS.instances) == 2 and FakeWS.instances[0].closed
    assert len(FakeWS.instances[1].subscribed) >= 5  # must cover a whole SESSION_SECONDS session


def test_feed_stops_when_event_already_set():
    async def scenario():
        stop = asyncio.Event()
        stop.set()
        await asyncio.wait_for(make_feed([], stop).run(stop), timeout=5)

    asyncio.run(scenario())
    assert FakeWS.instances == []


class TickThenCloseWS(FakeWS):
    async def subscribe_market_data_lite(self, request_id, slugs):
        self.emit("message", LITE)
        self.emit("close")


def test_feed_backs_off_when_server_sends_a_tick_then_drops_every_time():
    async def scenario():
        FakeWS.instances, ticks, sleeps, stop = [], [], [], asyncio.Event()

        async def record_sleep(delay, _stop):
            sleeps.append(delay)

        def on_tick(tick):
            ticks.append(tick)
            if len(ticks) == 4:
                stop.set()

        feed = LiveFeed(on_tick, ws_factory=TickThenCloseWS, creds=("id", "s"), sleep=record_sleep)
        await asyncio.wait_for(feed.run(stop), timeout=5)
        return sleeps

    sleeps = asyncio.run(scenario())
    assert len(sleeps) >= 2 and all(d > 0 for d in sleeps)
    assert sleeps == sorted(sleeps)  # backoff grows instead of hammering the server


class AlwaysCloseWS(FakeWS):
    async def subscribe_market_data_lite(self, request_id, slugs):
        self.emit("close")


def test_backoff_wakes_immediately_on_stop():
    async def scenario():
        FakeWS.instances, stop = [], asyncio.Event()
        feed = LiveFeed(lambda t: None, ws_factory=AlwaysCloseWS, creds=("id", "s"))  # default sleep
        asyncio.get_running_loop().call_later(0.1, stop.set)
        await asyncio.wait_for(feed.run(stop), timeout=2)  # would hang for the 5s+ backoff if stop is ignored

    asyncio.run(scenario())
