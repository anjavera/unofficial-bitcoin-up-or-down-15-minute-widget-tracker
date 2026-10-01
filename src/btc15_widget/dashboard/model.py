"""Data model for the multi-market dashboard."""

from dataclasses import dataclass, field


@dataclass
class MarketSummary:
    """A market discovered via the REST Events/Markets APIs."""

    slug: str
    title: str
    category: str
    event_slug: str
    volume: float = 0.0
    active: bool = True


@dataclass
class BookLevel:
    price: float
    qty: float


@dataclass
class MarketQuote:
    """Live best bid/ask plus order-book depth for one market."""

    slug: str
    best_bid: float | None = None
    best_ask: float | None = None
    last_trade: float | None = None
    bids: list[BookLevel] = field(default_factory=list)
    offers: list[BookLevel] = field(default_factory=list)

    @property
    def spread(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid

    @property
    def bid_depth(self) -> float:
        return sum(level.qty for level in self.bids)

    @property
    def ask_depth(self) -> float:
        return sum(level.qty for level in self.offers)
