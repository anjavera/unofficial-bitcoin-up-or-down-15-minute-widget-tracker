"""Injectable data sources for the dashboard: REST discovery plus the live order-book feed."""

from collections.abc import Callable
from dataclasses import dataclass

from btc15_widget.client import get_client
from btc15_widget.dashboard.discovery import DEFAULT_CATEGORIES, DEFAULT_PER_CATEGORY, discover_markets
from btc15_widget.dashboard.feed import MultiMarketFeed
from btc15_widget.dashboard.model import MarketQuote, MarketSummary

DISCOVERY_EVERY = 300  # seconds between re-running market discovery


@dataclass
class DashboardSources:
    discover: Callable[[], list[MarketSummary]]
    feed_factory: Callable[[Callable[[MarketQuote], None], Callable[[], list[str]]], MultiMarketFeed]
    close: Callable[[], None] = lambda: None


def default_dashboard_sources(
    categories: tuple[str, ...] = DEFAULT_CATEGORIES, per_category: int = DEFAULT_PER_CATEGORY
) -> DashboardSources:
    """Real sources. Raises RuntimeError when Polymarket credentials are missing."""
    api = get_client()
    return DashboardSources(
        discover=lambda: discover_markets(api, categories, per_category),
        feed_factory=lambda on_quote, get_slugs: MultiMarketFeed(on_quote, get_slugs),
        close=api.close,
    )
