"""Live Polymarket US order-book feed for an arbitrary, changeable set of markets (read-only).

Mirrors `btc15_widget.feed.LiveFeed`'s reconnect loop, generalised for a dynamic slug list
(up to the gateway's 100-markets-per-connection limit) and full order-book depth instead of
the lightweight BTC-15 ticks.
"""

import asyncio
from collections.abc import Callable

from polymarket_us.websocket import MarketsWebSocket

from btc15_widget.client import load_credentials
from btc15_widget.dashboard.model import BookLevel, MarketQuote
from btc15_widget.feed import wait_or_stop

MAX_SLUGS_PER_CONNECTION = 100
SESSION_SECONDS = 3600  # re-subscribe hourly so the market list stays current even with no manual refresh


def _amount(value) -> float | None:
    try:
        return float(value["value"])
    except (TypeError, KeyError, ValueError):
        return None


def _levels(raw) -> list[BookLevel]:
    out = []
    for level in raw or []:
        price, qty = _amount(level.get("px")), level.get("qty")
        try:
            qty = float(qty)
        except (TypeError, ValueError):
            qty = None
        if price is not None and qty is not None:
            out.append(BookLevel(price=price, qty=qty))
    return out


def parse_market_data(message: dict) -> MarketQuote | None:
    """The book arrives best-first, so the top bid/offer are the first elements."""
    data = message.get("marketData")
    if not data:
        return None
    bids, offers = _levels(data.get("bids")), _levels(data.get("offers"))
    stats = data.get("stats") or {}
    return MarketQuote(
        slug=data["marketSlug"],
        best_bid=bids[0].price if bids else None,
        best_ask=offers[0].price if offers else None,
        last_trade=_amount(stats.get("lastTradePx")),
        bids=bids,
        offers=offers,
    )


class MultiMarketFeed:
    """Subscribes to full order-book data for whatever `get_slugs()` returns, reconnecting on drop.

    `get_slugs` is re-read on every (re)connect, so discovery refreshes or watchlist pins/unpins take
    effect on the next reconnect; call `request_resubscribe()` to force one immediately.
    """

    def __init__(
        self,
        on_quote: Callable[[MarketQuote], None],
        get_slugs: Callable[[], list[str]],
        ws_factory=MarketsWebSocket,
        creds: tuple[str, str] | None = None,
        sleep=wait_or_stop,
    ) -> None:
        self.on_quote, self.get_slugs = on_quote, get_slugs
        self._factory, self._creds, self._sleep = ws_factory, creds, sleep
        self._resubscribe = asyncio.Event()

    def request_resubscribe(self) -> None:
        self._resubscribe.set()

    async def run(self, stop: asyncio.Event) -> None:
        creds = self._creds or load_credentials()
        failures = 0
        while not stop.is_set():
            slugs = self.get_slugs()[:MAX_SLUGS_PER_CONNECTION]
            if not slugs:
                await self._sleep(1.0, stop)
                continue
            self._resubscribe.clear()
            dropped = asyncio.Event()
            ws = self._factory(key_id=creds[0], secret_key=creds[1])

            def on_message(message: dict) -> None:
                quote = parse_market_data(message)
                if quote:
                    self.on_quote(quote)

            ws.on("message", on_message)
            ws.on("close", dropped.set)
            ws.on("error", lambda _e: dropped.set())
            try:
                await ws.connect()
                await ws.subscribe_market_data("depth", slugs)
                waiters = {
                    asyncio.ensure_future(dropped.wait()),
                    asyncio.ensure_future(stop.wait()),
                    asyncio.ensure_future(self._resubscribe.wait()),
                }
                _, pending = await asyncio.wait(waiters, timeout=SESSION_SECONDS, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                clean = not dropped.is_set() and not stop.is_set()
            except Exception:
                clean = False
            finally:
                try:
                    await ws.close()
                except Exception:
                    pass
            if stop.is_set():
                return
            failures = 0 if clean else failures + 1  # a forced resubscribe counts as clean, not a failure
            if not clean:
                await self._sleep(min(5 * failures, 60), stop)
