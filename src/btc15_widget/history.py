"""Exact window history from Polymarket's settled BRTI values, with a local cache."""

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from btc15_widget.model import Window
from btc15_widget.windows import event_slug, floor_window

HISTORY_CACHE = Path.home() / ".cache" / "btc15-widget" / "history.json"
PAUSE_BETWEEN_FETCHES = 0.4  # stay clear of the Cloudflare 1015 rate limit
BREAKER_AFTER = 3  # consecutive failed windows before later ones are tried once, without backoff


def with_retry(fn, tries: int = 4, sleep=time.sleep):
    for attempt in range(tries):
        try:
            return fn()
        except Exception:
            if attempt == tries - 1:
                raise
            sleep(3 * (attempt + 1))


def _price(d) -> float | None:
    try:
        return float(d["value"])
    except (TypeError, KeyError, ValueError):
        return None


def fetch_window(client, start: datetime, sleep=time.sleep, tries: int = 4, with_volume: bool = True) -> Window:
    """One window from the API. Never raises: a failure becomes a gap with `error` set."""
    try:
        event = with_retry(lambda: client.events.retrieve_by_slug(event_slug(start)), tries, sleep)["event"]
        market = event["markets"][0]
        terms = market.get("assetPriceTerms") or {}
        window = Window(
            start=start,
            open=_price(terms.get("priceToBeat")),
            close=_price(terms.get("settlementPrice")),
            status=market.get("status", "").removeprefix("MARKET_STATUS_"),
        )
    except Exception as e:
        return Window(start=start, open=None, close=None, error=str(e)[:60] or type(e).__name__)
    if not with_volume:
        return window
    try:
        data = with_retry(lambda: client.markets.bbo(market["slug"]), tries, sleep)["marketData"]
        window.volume = float(data.get("sharesTraded") or 0)
    except Exception:
        pass  # volume is cosmetic; keep the window
    return window


def _read_cache(path: Path | None) -> dict[str, dict]:
    if path is None:
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def load_history(client, now: datetime, hours: float = 24, cache_path: Path | None = None,
                 sleep=time.sleep, with_volume: bool = True) -> list[Window]:
    """Windows from `hours` ago through the live one, oldest first (hours*4 + 1 entries)."""
    current = floor_window(now)
    starts = [current - timedelta(minutes=15 * i) for i in range(int(hours * 4), -1, -1)]
    cache = _read_cache(cache_path)
    windows, failures = [], 0
    for start in starts:
        cached = cache.get(start.isoformat())
        if cached:
            windows.append(Window(start=start, **cached))
            continue
        window = fetch_window(client, start, sleep, tries=4 if failures < BREAKER_AFTER else 1, with_volume=with_volume)
        failures = failures + 1 if window.error else 0
        windows.append(window)
        if window.settled:
            cache[start.isoformat()] = {"open": window.open, "close": window.close,
                                        "status": window.status, "volume": window.volume}
        sleep(PAUSE_BETWEEN_FETCHES)
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache))
    return windows
