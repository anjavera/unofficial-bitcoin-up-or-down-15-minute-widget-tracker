import pytest

from btc15_widget.dashboard.model import BookLevel, MarketQuote


def test_spread_is_ask_minus_bid():
    quote = MarketQuote(slug="s", best_bid=0.40, best_ask=0.45)
    assert quote.spread == pytest.approx(0.05)


def test_spread_is_none_when_either_side_missing():
    assert MarketQuote(slug="s", best_bid=0.40, best_ask=None).spread is None
    assert MarketQuote(slug="s", best_bid=None, best_ask=0.45).spread is None


def test_depth_sums_level_quantities():
    quote = MarketQuote(
        slug="s",
        bids=[BookLevel(price=0.40, qty=100), BookLevel(price=0.39, qty=50)],
        offers=[BookLevel(price=0.45, qty=30)],
    )
    assert quote.bid_depth == 150
    assert quote.ask_depth == 30


def test_depth_is_zero_for_an_empty_book():
    quote = MarketQuote(slug="s")
    assert quote.bid_depth == 0 and quote.ask_depth == 0
