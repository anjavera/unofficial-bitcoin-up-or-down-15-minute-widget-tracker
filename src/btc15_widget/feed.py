"""Live Polymarket US price feed for the BTC 15m markets (read-only, reconnecting)."""

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone

from polymarket_us.websocket import MarketsWebSocket

from btc15_widget.client import load_credentials
from btc15_widget.model import LiveTick
from btc15_widget.windows import window_slugs

SESSION_SECONDS = 3600  # re-subscribe hourly so the window list stays current
WINDOWS_TO_FOLLOW = 3


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


class LiveFeed:
    def __init__(self, on_tick: Callable[[LiveTick], None], ws_factory=MarketsWebSocket,
                 creds: tuple[str, str] | None = None, sleep=asyncio.sleep) -> None:
        self.on_tick, self._factory, self._creds, self._sleep = on_tick, ws_factory, creds, sleep

    async def run(self, stop: asyncio.Event) -> None:
        creds = self._creds or load_credentials()
        failures = 0
        while not stop.is_set():
            dropped, got_tick = asyncio.Event(), False
            ws = self._factory(key_id=creds[0], secret_key=creds[1])

            def on_message(message: dict) -> None:
                nonlocal got_tick
                tick = parse_lite(message)
                if tick:
                    got_tick = True
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
            failures = 0 if (got_tick or timed_out) else failures + 1
            if not timed_out:
                await self._sleep(min(5 * failures, 60))
