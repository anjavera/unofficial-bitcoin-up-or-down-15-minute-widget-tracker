"""Live Polymarket US prices for the BTC 15m markets.

Two interchangeable feeds: `PollingFeed` polls the public order book and needs no API keys; `LiveFeed` uses the
authenticated WebSocket (push updates) and is used automatically when the user has set up API keys.
"""

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone

from polymarket_us.errors import NotFoundError
from polymarket_us.websocket import MarketsWebSocket

from btc15_widget.client import load_credentials
from btc15_widget.model import LiveTick
from btc15_widget.windows import MARKET_SLUG, floor_window, window_slugs

POLL_EVERY = 2.0  # seconds between price polls
MAX_BACKOFF = 60
NO_MARKET_RETRY = 10  # seconds between checks while Polymarket has no market for the live window
SESSION_SECONDS = 3600  # keyed feed: re-subscribe hourly so the window list stays current
WINDOWS_TO_FOLLOW = 6  # must cover SESSION_SECONDS plus the rest of the current window


def _px(d) -> float | None:
    try:
        return float(d["value"])
    except (TypeError, KeyError, ValueError):
        return None


def parse_lite(message: dict) -> LiveTick | None:
    data = message.get("marketDataLite")
    if not data:
        return None
    shares = data.get("sharesTraded")
    return LiveTick(
        slug=data["marketSlug"],
        up_price=_px(data.get("currentPx")),
        best_bid=_px(data.get("bestBid")),
        best_ask=_px(data.get("bestAsk")),
        last_trade=_px(data.get("lastTradePx")),
        shares_traded=float(shares) if shares else None,
    )



def parse_book(response) -> LiveTick:
    """A LiveTick from a `markets.book` response; raises ValueError when the response is not shaped as expected.

    The Up price is the midpoint of the best bid and ask, or the last trade when one side of the book is empty.
    """
    try:
        data = response["marketData"]
        slug = data["marketSlug"]
    except (KeyError, TypeError) as e:
        raise ValueError(f"unexpected order book response: {str(response)[:80]}") from e
    bids = [p for p in (_px(level.get("px")) for level in data.get("bids") or []) if p is not None]
    offers = [p for p in (_px(level.get("px")) for level in data.get("offers") or []) if p is not None]
    best_bid, best_ask = (max(bids) if bids else None), (min(offers) if offers else None)
    stats = data.get("stats") or {}
    last = _px(stats.get("lastTradePx"))
    shares = stats.get("sharesTraded")
    mid = (best_bid + best_ask) / 2 if best_bid is not None and best_ask is not None else last
    return LiveTick(slug=slug, up_price=mid, best_bid=best_bid, best_ask=best_ask, last_trade=last,
                    shares_traded=float(shares) if shares else None)


async def wait_or_stop(delay: float, stop: asyncio.Event) -> None:
    """Sleep up to `delay` seconds, returning early if `stop` is set."""
    try:
        await asyncio.wait_for(stop.wait(), timeout=delay)
    except asyncio.TimeoutError:
        pass


class PollingFeed:
    """Polls the live window's order book every couple of seconds and reports each price as a LiveTick."""

    def __init__(self, on_tick: Callable[[LiveTick], None], fetch_book: Callable[[str], dict], interval: float = POLL_EVERY,
                 clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc), sleep=wait_or_stop) -> None:
        self.on_tick, self._fetch, self._interval, self._clock, self._sleep = on_tick, fetch_book, interval, clock, sleep

    async def run(self, stop: asyncio.Event) -> None:
        failures = 0
        while not stop.is_set():
            slug = MARKET_SLUG.format(floor_window(self._clock()))  # re-read each time: follows the rollover
            try:
                tick = parse_book(await asyncio.to_thread(self._fetch, slug))
            except NotFoundError:  # no market published for this window: check again gently, this is not an outage
                delay = NO_MARKET_RETRY
            except Exception:  # network error, rate limit or odd response: back off and keep going
                failures += 1
                delay = min(5 * failures, MAX_BACKOFF)
            else:
                failures, delay = 0, self._interval
                self.on_tick(tick)
            await self._sleep(delay, stop)


class LiveFeed:
    def __init__(self, on_tick: Callable[[LiveTick], None], ws_factory=MarketsWebSocket,
                 creds: tuple[str, str] | None = None, sleep=wait_or_stop) -> None:
        self.on_tick, self._factory, self._creds, self._sleep = on_tick, ws_factory, creds, sleep

    async def run(self, stop: asyncio.Event) -> None:
        creds = self._creds or load_credentials()
        failures = 0
        while not stop.is_set():
            dropped = asyncio.Event()
            ws = self._factory(key_id=creds[0], secret_key=creds[1])

            def on_message(message: dict) -> None:
                tick = parse_lite(message)
                if tick:
                    self.on_tick(tick)

            ws.on("message", on_message)
            ws.on("close", dropped.set)
            ws.on("error", lambda _e: dropped.set())  # the SDK ends its read loop on errors
            try:
                await ws.connect()
                await ws.subscribe_market_data_lite("lite", window_slugs(datetime.now(timezone.utc), WINDOWS_TO_FOLLOW))
                waiters = {asyncio.ensure_future(dropped.wait()), asyncio.ensure_future(stop.wait())}
                _, pending = await asyncio.wait(waiters, timeout=SESSION_SECONDS, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                timed_out = not dropped.is_set() and not stop.is_set()
            except Exception:
                timed_out = False
            finally:
                try:
                    await ws.close()
                except Exception:
                    pass
            if stop.is_set():
                return
            failures = 0 if timed_out else failures + 1  # any early drop backs off, even after a tick
            if not timed_out:
                await self._sleep(min(5 * failures, 60), stop)

