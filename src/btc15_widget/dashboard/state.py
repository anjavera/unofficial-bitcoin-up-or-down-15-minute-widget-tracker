"""Dashboard state: discovered markets, live quotes and the watchlist. No I/O, injected clock."""

from dataclasses import dataclass, field
from datetime import datetime

from btc15_widget.dashboard.model import MarketQuote, MarketSummary
from btc15_widget.dashboard.watchlist import Watchlist

STALE_SECONDS = 15


@dataclass
class DashboardState:
    markets: dict[str, MarketSummary] = field(default_factory=dict)
    quotes: dict[str, MarketQuote] = field(default_factory=dict)
    quotes_at: dict[str, datetime] = field(default_factory=dict)
    watchlist: Watchlist = field(default_factory=Watchlist)
    markets_at: datetime | None = None
    error: str | None = None

    def set_markets(self, markets: list[MarketSummary], now: datetime) -> None:
        self.markets = {m.slug: m for m in markets}
        self.markets_at = now

    def apply_quote(self, quote: MarketQuote, now: datetime) -> None:
        self.quotes[quote.slug], self.quotes_at[quote.slug] = quote, now

    def is_stale(self, slug: str, now: datetime) -> bool:
        at = self.quotes_at.get(slug)
        return at is None or (now - at).total_seconds() > STALE_SECONDS

    def slugs(self) -> list[str]:
        """Everything the live feed should subscribe to: discovered markets plus any pinned slug."""
        return sorted(set(self.markets) | set(self.watchlist))

    def rows(self) -> list[tuple[MarketSummary, MarketQuote | None]]:
        """Pinned markets first, then the rest grouped by category and sorted by volume."""

        def key(summary: MarketSummary) -> tuple:
            pinned_rank = 0 if summary.slug in self.watchlist else 1
            return (pinned_rank, summary.category, -summary.volume, summary.slug)

        ordered = sorted(self.markets.values(), key=key)
        return [(m, self.quotes.get(m.slug)) for m in ordered]
