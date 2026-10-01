from datetime import datetime, timezone

from btc15_widget.dashboard.model import MarketQuote, MarketSummary
from btc15_widget.dashboard.render import build_dashboard_table
from btc15_widget.dashboard.state import DashboardState
from btc15_widget.dashboard.watchlist import Watchlist

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def test_table_has_the_expected_columns(tmp_path):
    state = DashboardState(watchlist=Watchlist(tmp_path / "w.json"))
    table = build_dashboard_table(state, NOW)
    assert [c.header for c in table.columns] == ["", "Category", "Market", "Last", "Bid", "Ask", "Spread", "Bid Depth", "Ask Depth"]


def cells(table, name):
    col = next(c for c in table.columns if c.header == name)
    return [getattr(cell, "plain", cell) for cell in col._cells]


def test_table_shows_a_star_for_pinned_markets(tmp_path):
    state = DashboardState(watchlist=Watchlist(tmp_path / "w.json"))
    state.set_markets([MarketSummary(slug="a", title="A", category="crypto", event_slug="e")], NOW)
    state.watchlist.add("a")
    table = build_dashboard_table(state, NOW)
    assert cells(table, "")[0] == "★"


def test_table_shows_dashes_for_markets_with_no_quote_yet(tmp_path):
    state = DashboardState(watchlist=Watchlist(tmp_path / "w.json"))
    state.set_markets([MarketSummary(slug="a", title="A", category="crypto", event_slug="e")], NOW)
    table = build_dashboard_table(state, NOW)
    for name in ("Last", "Bid", "Ask", "Spread"):
        assert cells(table, name)[0] == "-"
    assert cells(table, "Bid Depth")[0] == "-"


def test_table_shows_quote_values_and_depth(tmp_path):
    state = DashboardState(watchlist=Watchlist(tmp_path / "w.json"))
    state.set_markets([MarketSummary(slug="a", title="A", category="crypto", event_slug="e")], NOW)
    from btc15_widget.dashboard.model import BookLevel

    quote = MarketQuote(
        slug="a", best_bid=0.40, best_ask=0.42, last_trade=0.41,
        bids=[BookLevel(price=0.40, qty=100)], offers=[BookLevel(price=0.42, qty=50)],
    )
    state.apply_quote(quote, NOW)
    table = build_dashboard_table(state, NOW)
    assert cells(table, "Last")[0] == "0.410"
    assert cells(table, "Bid")[0] == "0.400"
    assert cells(table, "Ask")[0] == "0.420"
    assert cells(table, "Spread")[0] == "0.020"
    assert cells(table, "Bid Depth")[0] == "100"
    assert cells(table, "Ask Depth")[0] == "50"
