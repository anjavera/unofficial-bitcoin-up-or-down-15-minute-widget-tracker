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


async def no_sleep(_):
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
    assert len(FakeWS.instances[1].subscribed) == 3  # current window plus two ahead


def test_feed_stops_when_event_already_set():
    async def scenario():
        stop = asyncio.Event()
        stop.set()
        await asyncio.wait_for(make_feed([], stop).run(stop), timeout=5)

    asyncio.run(scenario())
    assert FakeWS.instances == []
