"""15-minute window maths for Polymarket US BTC Up/Down markets."""

from datetime import datetime, timedelta, timezone

EVENT_SLUG = "btc-updown-15m-{:%Y-%m-%d-%H%M}z"
MARKET_SLUG = "cpc-btc-updown-15m-{:%Y-%m-%d-%H%M}z"


def floor_window(now: datetime) -> datetime:
    """Start of the 15-minute window containing `now` (UTC)."""
    now = now.astimezone(timezone.utc)
    return now.replace(minute=now.minute // 15 * 15, second=0, microsecond=0)


def window_slugs(now: datetime, ahead: int, back: int = 0) -> list[str]:
    """Market slugs from `back` windows ago through the current window plus `ahead - 1` more."""
    start = floor_window(now)
    return [MARKET_SLUG.format(start + timedelta(minutes=15 * i)) for i in range(-back, ahead)]
