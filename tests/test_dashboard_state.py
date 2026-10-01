from datetime import datetime, timedelta, timezone

from btc15_widget.dashboard.model import MarketQuote, MarketSummary
from btc15_widget.dashboard.state import DashboardState
from btc15_widget.dashboard.watchlist import Watchlist

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def summary(slug, category="crypto", volume=0.0):
    return MarketSummary(slug=slug, title=slug, category=category, event_slug="e", volume=volume)


def test_set_markets_indexes_by_slug_and_records_the_time():
    state = DashboardState()
    state.set_markets([summary("a"), summary("b")], NOW)
    assert set(state.markets) == {"a", "b"} and state.markets_at == NOW


def test_apply_quote_records_the_quote_and_its_time():
    state = DashboardState()
    quote = MarketQuote(slug="a", best_bid=0.4)
    state.apply_quote(quote, NOW)
    assert state.quotes["a"] is quote and state.quotes_at["a"] == NOW


def test_is_stale_true_with_no_quote_yet():
    state = DashboardState()
    assert state.is_stale("a", NOW) is True


def test_is_stale_false_just_after_a_quote_true_after_the_window():
    state = DashboardState()
    state.apply_quote(MarketQuote(slug="a"), NOW)
    assert state.is_stale("a", NOW + timedelta(seconds=5)) is False
    assert state.is_stale("a", NOW + timedelta(seconds=30)) is True


def test_slugs_combines_discovered_markets_and_the_watchlist(tmp_path):
    state = DashboardState(watchlist=Watchlist(tmp_path / "w.json"))
    state.set_markets([summary("a"), summary("b")], NOW)
    state.watchlist.add("c")  # pinned but not currently discovered
    assert state.slugs() == ["a", "b", "c"]


def test_rows_puts_pinned_markets_first(tmp_path):
    state = DashboardState(watchlist=Watchlist(tmp_path / "w.json"))
    state.set_markets([summary("low-volume", volume=1), summary("pinned", volume=0)], NOW)
    state.watchlist.add("pinned")
    rows = state.rows()
    assert [m.slug for m, _ in rows] == ["pinned", "low-volume"]


def test_rows_group_by_category_then_sort_by_volume_descending(tmp_path):
    state = DashboardState(watchlist=Watchlist(tmp_path / "w.json"))
    state.set_markets(
        [
            summary("sports-a", category="sports", volume=10),
            summary("crypto-b", category="crypto", volume=5),
            summary("crypto-a", category="crypto", volume=50),
        ],
        NOW,
    )
    rows = state.rows()
    assert [m.slug for m, _ in rows] == ["crypto-a", "crypto-b", "sports-a"]


def test_rows_pairs_each_market_with_its_latest_quote_or_none(tmp_path):
    state = DashboardState(watchlist=Watchlist(tmp_path / "w.json"))
    state.set_markets([summary("a"), summary("b")], NOW)
    quote = MarketQuote(slug="a", best_bid=0.4)
    state.apply_quote(quote, NOW)
    rows = dict((m.slug, q) for m, q in state.rows())
    assert rows["a"] is quote and rows["b"] is None
