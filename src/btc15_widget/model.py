"""Data model shared by history, feed and widgets."""

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class Window:
    start: datetime
    open: float | None
    close: float | None
    status: str = ""
    volume: float | None = None
    error: str | None = None

    @property
    def end(self) -> datetime:
        return self.start + timedelta(minutes=15)

    @property
    def settled(self) -> bool:
        return self.open is not None and self.close is not None

    @property
    def net(self) -> float | None:
        return self.close - self.open if self.settled else None

    @property
    def result(self) -> str | None:
        return None if self.net is None else ("UP" if self.net >= 0 else "DOWN")


@dataclass
class LiveTick:
    slug: str
    up_price: float | None
    best_bid: float | None
    best_ask: float | None
    last_trade: float | None
    shares_traded: float | None
    state: str | None = None  # e.g. MARKET_STATE_OPEN / _HALTED, when the source reports it

    @property
    def spread(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid
