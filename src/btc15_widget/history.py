"""Exact window history from Polymarket's settled BRTI values, with a local cache.

History is fetched with one bulk request per 100 windows; a per-window path remains as a fallback.
"""

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from btc15_widget.model import Window
from btc15_widget.paths import cache_dir
from btc15_widget.windows import MARKET_SLUG, event_slug, floor_window

HISTORY_CACHE = cache_dir() / "history.json"
PAUSE_BETWEEN_FETCHES = 0.4  # stay clear of the Cloudflare 1015 rate limit (per-window paths only)
BREAKER_AFTER = 3  # consecutive failed windows before later ones are tried once, without backoff
BULK_CHUNK = 100  # slugs per events.list request
BULK_TRIES = 2


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


def _gap(start: datetime, reason: str) -> Window:
    return Window(start=start, open=None, close=None, error=reason[:60] or "unknown error")


def _window_from_event(start: datetime, event: dict) -> Window:
    markets = event.get("markets") or []
    if not markets:
        return _gap(start, "market has no data")
    market = markets[0]
    terms = market.get("assetPriceTerms") or {}
    return Window(
        start=start,
        open=_price(terms.get("priceToBeat")),
        close=_price(terms.get("settlementPrice")),
        status=(market.get("status") or "").removeprefix("MARKET_STATUS_"),
    )


def _attach_volume(client, window: Window, sleep=time.sleep) -> None:
    try:
        data = with_retry(lambda: client.markets.bbo(MARKET_SLUG.format(window.start)), 4, sleep)["marketData"]
        window.volume = float(data.get("sharesTraded") or 0)
    except Exception:
        pass  # volume is cosmetic; keep the window


def fetch_window(client, start: datetime, sleep=time.sleep, tries: int = 4, with_volume: bool = False) -> Window:
    """One window from the API. Never raises: a failure becomes a gap with `error` set."""
    try:
        event = with_retry(lambda: client.events.retrieve_by_slug(event_slug(start)), tries, sleep)["event"]
        window = _window_from_event(start, event)
    except Exception as e:
        return _gap(start, str(e) or type(e).__name__)
    if with_volume and not window.error:
        _attach_volume(client, window, sleep)
    return window


def fetch_windows_bulk(client, starts: list[datetime], sleep=time.sleep) -> dict[datetime, Window]:
    """Many windows with one request per 100: a window the API does not know becomes a gap in place."""
    found: dict[datetime, Window] = {}
    for i in range(0, len(starts), BULK_CHUNK):
        chunk = starts[i : i + BULK_CHUNK]
        slugs = [event_slug(s) for s in chunk]
        response = with_retry(lambda: client.events.list({"slug": slugs, "limit": BULK_CHUNK}), BULK_TRIES, sleep)
        by_slug = {e["slug"]: e for e in response.get("events", [])}
        for start, slug in zip(chunk, slugs):
            event = by_slug.get(slug)
            found[start] = _gap(start, "no such market") if event is None else _window_from_event(start, event)
    return found


def _fetch_each(client, starts: list[datetime], sleep=time.sleep) -> dict[datetime, Window]:
    """Fallback: one request per window, with a circuit breaker so an outage does not stall for minutes."""
    found, failures = {}, 0
    for start in starts:
        window = fetch_window(client, start, sleep, tries=4 if failures < BREAKER_AFTER else 1)
        failures = failures + 1 if window.error else 0
        found[start] = window
        sleep(PAUSE_BETWEEN_FETCHES)
    return found


def _read_cache(path: Path | None) -> dict[str, dict]:
    if path is None:
        return {}
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def load_history(client, now: datetime, hours: float = 24, cache_path: Path | None = None,
                 sleep=time.sleep, with_volume: bool = False) -> list[Window]:
    """Windows from `hours` ago through the live one, oldest first (hours*4 + 1 entries).

    Settled windows are cached and never refetched. Volume costs one extra request per window, so it is opt-in.
    """
    current = floor_window(now)
    starts = [current - timedelta(minutes=15 * i) for i in range(int(hours * 4), -1, -1)]
    cache = _read_cache(cache_path)
    windows: dict[datetime, Window] = {}
    for start in starts:
        entry = cache.get(start.isoformat())
        if entry and not (with_volume and entry.get("volume") is None):
            windows[start] = Window(start=start, **entry)
    need = [s for s in starts if s not in windows]
    if need:
        try:
            fetched = fetch_windows_bulk(client, need, sleep)
        except Exception:
            fetched = _fetch_each(client, need, sleep)
        if with_volume:
            for window in fetched.values():
                if not window.error:
                    _attach_volume(client, window, sleep)
                    sleep(PAUSE_BETWEEN_FETCHES)
        for start, window in fetched.items():
            if window.settled:
                cache[start.isoformat()] = {"open": window.open, "close": window.close,
                                            "status": window.status, "volume": window.volume}
        windows.update(fetched)
        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache))
    return [windows[s] for s in starts]
