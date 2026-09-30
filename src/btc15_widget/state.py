"""Widget state: everything the renderers need, with no I/O and an injected clock."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from btc15_widget.calibration import Calibration
from btc15_widget.model import LiveTick, Window
from btc15_widget.proxy import apply_bias, composite
from btc15_widget.windows import MARKET_SLUG, floor_window

STALE_SECONDS = 10
STRIP_WINDOWS = 96
MIN_CALIBRATION_SAMPLES = 8
RETRY_UNSETTLED_AFTER = 20  # seconds between reloads while a past window is unsettled
REFRESH_EVERY = 300  # seconds between reloads of a complete history
STEP = timedelta(minutes=15)
TICK_KEEP = timedelta(hours=1)


@dataclass
class WidgetState:
    windows: list[Window] = field(default_factory=list)
    ticks: dict[str, LiveTick] = field(default_factory=dict)  # latest tick per market slug
    ticks_at: dict[str, datetime] = field(default_factory=dict)
    quotes: dict[str, float | None] = field(default_factory=dict)
    quotes_at: datetime | None = None
    calibration: Calibration | None = None
    feed_status: str = "connecting"
    error: str | None = None
    history_at: datetime | None = None
    loading: bool = False  # a history load is in progress

    def set_history(self, windows: list[Window], now: datetime) -> None:
        self.windows, self.history_at = windows, now

    def apply_tick(self, tick: LiveTick, now: datetime) -> None:
        """The feed follows several windows at once, so ticks are kept per market slug."""
        self.ticks[tick.slug], self.ticks_at[tick.slug] = tick, now
        for slug in [k for k, at in self.ticks_at.items() if now - at > TICK_KEEP]:
            del self.ticks[slug], self.ticks_at[slug]

    def live_tick(self, now: datetime) -> LiveTick | None:
        return self.ticks.get(MARKET_SLUG.format(floor_window(now)))

    def apply_quotes(self, quotes: dict[str, float | None], now: datetime) -> None:
        self.quotes, self.quotes_at = quotes, now

    def _by_start(self) -> dict[datetime, Window]:
        return {w.start: w for w in self.windows}

    def strip_windows(self, now: datetime) -> list[Window]:
        """The 96 windows before the live one; a missing start becomes an empty placeholder in place."""
        live = floor_window(now)
        known = self._by_start()
        starts = [live - i * STEP for i in range(STRIP_WINDOWS, 0, -1)]
        return [known.get(s) or Window(start=s, open=None, close=None) for s in starts]

    def table_windows(self, now: datetime) -> list[Window]:
        """Table rows, oldest first: the 96 past windows, then the live one."""
        return self.strip_windows(now) + [self.live_window(now)]

    def live_window(self, now: datetime) -> Window:
        start = floor_window(now)
        return self._by_start().get(start) or Window(start=start, open=None, close=None)

    def is_stale(self, kind: str, now: datetime) -> bool:
        at = self.ticks_at.get(MARKET_SLUG.format(floor_window(now))) if kind == "tick" else self.quotes_at
        return at is None or (now - at).total_seconds() > STALE_SECONDS

    def proxy_price(self, now: datetime) -> float | None:
        if self.is_stale("quotes", now):
            return None
        price = composite(self.quotes)
        if price is not None and self.calibration and self.calibration.n >= MIN_CALIBRATION_SAMPLES:
            price = apply_bias(price, -self.calibration.bias)  # bias = proxy - BRTI, so subtract it
        return price

    def gap(self, now: datetime) -> float | None:
        price, open_ = self.proxy_price(now), self.live_window(now).open
        return None if price is None or open_ is None else price - open_

    def needs_history_refresh(self, now: datetime) -> bool:
        if not self.windows or self.history_at is None:
            return True
        live = floor_window(now)
        if live not in self._by_start():
            return True
        age = (now - self.history_at).total_seconds()
        if any(not w.settled for w in self.windows if w.start < live) and age > RETRY_UNSETTLED_AFTER:
            return True
        return age > REFRESH_EVERY
