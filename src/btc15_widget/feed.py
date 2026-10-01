"""Live Polymarket US prices for the current 15-minute window, polled from the public order book (no keys)."""

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone

from btc15_widget.model import LiveTick
from btc15_widget.windows import MARKET_SLUG, floor_window

POLL_EVERY = 2.0  # seconds between price polls
MAX_BACKOFF = 60


def _px(d) -> float | None:
    try:
        return float(d["value"])
    except (TypeError, KeyError, ValueError):
        return None


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
            except Exception:  # network error, rate limit or odd response: back off and keep going
                failures += 1
                delay = min(5 * failures, MAX_BACKOFF)
            else:
                failures, delay = 0, self._interval
                self.on_tick(tick)
            await self._sleep(delay, stop)
