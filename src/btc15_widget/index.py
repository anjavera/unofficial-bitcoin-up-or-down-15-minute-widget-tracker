"""Polymarket's own BTC reference index price (public, no keys): the index the markets settle on."""

import math

from btc15_widget.proxy import http_get_json

INDEX_URL = ("https://gateway.polymarket.us/v1/asset-prices/history"
             "?assets=crypto:btc&bucket=ASSET_PRICE_BUCKET_1S&to=0&from={from_ts}")
LOOKBACK_SECONDS = 15  # recent enough to be live, wide enough to hold a real tick if one second is missing


def parse_index(payload) -> tuple[float, int] | None:
    """(price, unix seconds) of the newest real BTC index tick, or None. Gap-filled candles (tickCount 0) are skipped."""
    try:
        series = next(s for s in payload["series"] if (s.get("asset") or {}).get("symbol") == "btc")
    except (TypeError, KeyError, StopIteration, AttributeError):
        series = None
    if series is None:  # tolerate a single-series reply that omits the asset field
        try:
            series = payload["series"][0] if len(payload["series"]) == 1 and "asset" not in payload["series"][0] else None
        except (TypeError, KeyError, IndexError):
            return None
    if series is None:
        return None
    for candle in reversed(series.get("candles") or []):
        if not candle.get("tickCount"):
            continue
        try:
            price = float(candle["close"])
            when = int(candle["timestamp"])
        except (KeyError, TypeError, ValueError):
            return None
        return (price, when) if math.isfinite(price) and price > 0 else None
    return None


def fetch_index(get_json=http_get_json, now: float | None = None) -> tuple[float, int] | None:
    """Latest index tick as (price, unix seconds); None on any failure so callers can fall back."""
    import time

    try:
        return parse_index(get_json(INDEX_URL.format(from_ts=int((now or time.time()) - LOOKBACK_SECONDS))))
    except Exception:
        return None
