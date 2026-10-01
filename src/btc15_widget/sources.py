"""Injectable data sources for the widget, plus price-proxy calibration."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from btc15_widget.calibration import Calibration, fetch_candles, measure
from btc15_widget.client import get_public_client
from btc15_widget.feed import PollingFeed
from btc15_widget.history import HISTORY_CACHE, load_history
from btc15_widget.model import LiveTick, Window
from btc15_widget.proxy import fetch_quotes
from btc15_widget.state import WidgetState

QUOTES_EVERY = 2.0  # seconds between exchange quote polls
CALIBRATION_EVERY = 1800  # seconds between calibration runs
CALIBRATION_HOURS = 4  # keeps the candle range under Coinbase's 300-candle cap


@dataclass
class DataSources:
    load_history: Callable[[datetime], list[Window]]
    fetch_quotes: Callable[[], dict[str, float | None]]
    fetch_candles: Callable[[datetime, datetime], dict]
    feed_factory: Callable[[Callable[[LiveTick], None]], PollingFeed | None]
    close: Callable[[], None] = lambda: None


def default_sources() -> DataSources:
    """Real sources. Everything is public data, so no credentials are needed."""
    api = get_public_client()
    return DataSources(
        load_history=lambda now: load_history(api, now, hours=24, cache_path=HISTORY_CACHE, with_volume=False),
        fetch_quotes=fetch_quotes,
        fetch_candles=fetch_candles,
        feed_factory=lambda on_tick: PollingFeed(on_tick, api.markets.book),
        close=api.close,
    )


def run_calibration(state: WidgetState, sources: DataSources, now: datetime) -> Calibration | None:
    """Measure proxy error over the last few hours of settled windows; state is untouched on failure."""
    since = now - timedelta(hours=CALIBRATION_HOURS)
    windows = [w for w in state.windows if w.settled and w.start >= since]
    try:
        candles = sources.fetch_candles(since - timedelta(minutes=15), now)
        calibration = measure(windows, candles)
    except Exception:
        return None
    if calibration is not None:
        state.calibration = calibration
    return calibration
