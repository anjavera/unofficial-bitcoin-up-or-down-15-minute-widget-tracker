import asyncio
from datetime import datetime, timezone

from textual.widgets import DataTable

from btc15_widget.dashboard.app import DashboardApp
from btc15_widget.dashboard.model import MarketQuote, MarketSummary
from btc15_widget.dashboard.sources import DashboardSources
from btc15_widget.dashboard.watchlist import Watchlist

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def summary(slug, category="crypto", volume=0.0):
    return MarketSummary(slug=slug, title=slug.upper(), category=category, event_slug="e", volume=volume)


class FakeFeed:
    def __init__(self, on_quote, get_slugs):
        self.on_quote, self.get_slugs, self.resubscribes = on_quote, get_slugs, 0

    def request_resubscribe(self):
        self.resubscribes += 1

    async def run(self, stop):
        self.on_quote(MarketQuote(slug="a", best_bid=0.4, best_ask=0.42))
        await stop.wait()


def make_sources(markets):
    feeds = []

    def feed_factory(on_quote, get_slugs):
        feed = FakeFeed(on_quote, get_slugs)
        feeds.append(feed)
        return feed

    return DashboardSources(discover=lambda: markets, feed_factory=feed_factory), feeds


def make_app(tmp_path, markets=None):
    markets = markets if markets is not None else [summary("a"), summary("b", category="sports")]
    sources, feeds = make_sources(markets)
    app = DashboardApp(sources=sources, clock=lambda: NOW, watchlist=Watchlist(tmp_path / "watchlist.json"))
    return app, feeds


async def until(pilot, cond, tries=100):
    for _ in range(tries):
        if cond():
            return True
        await pilot.pause(0.05)
    return False


def run(coro):
    asyncio.run(asyncio.wait_for(coro, timeout=30))


def test_dashboard_discovers_markets_and_shows_live_quotes(tmp_path):
    async def scenario():
        app, _ = make_app(tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            assert await until(pilot, lambda: app.state.markets and app.state.quotes)
            app.refresh_view()
            table = app.query_one(DataTable)
            assert table.row_count == 2

    run(scenario())


def test_w_toggles_watch_on_the_highlighted_row(tmp_path):
    async def scenario():
        app, feeds = make_app(tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            assert await until(pilot, lambda: app.state.markets)
            app.refresh_view()
            first_slug = app._row_slugs[0]
            await pilot.press("w")
            await pilot.pause(0.1)
            assert first_slug in app.state.watchlist
            assert feeds[0].resubscribes >= 1
            await pilot.press("w")
            await pilot.pause(0.1)
            assert first_slug not in app.state.watchlist

    run(scenario())


def test_pinned_markets_are_persisted_via_the_watchlist(tmp_path):
    path = tmp_path / "watchlist.json"

    async def scenario():
        app, _ = make_app(tmp_path)
        app.state.watchlist = Watchlist(path)
        async with app.run_test(size=(100, 30)) as pilot:
            assert await until(pilot, lambda: app.state.markets)
            app.refresh_view()
            await pilot.press("w")
            await pilot.pause(0.1)

    run(scenario())
    assert len(Watchlist(path)) == 1


def test_q_quits(tmp_path):
    async def scenario():
        app, _ = make_app(tmp_path)
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press("q")
            await pilot.pause(0.2)
        assert app._stop.is_set()

    run(scenario())


def test_startup_error_is_shown_not_raised(tmp_path, monkeypatch):
    from btc15_widget.dashboard import app as dashboard_app_module

    def no_creds(categories, per_category):
        raise RuntimeError("Missing POLYMARKET_KEY_ID / POLYMARKET_SECRET_KEY")

    monkeypatch.setattr(dashboard_app_module, "default_dashboard_sources", no_creds)

    async def scenario():
        app = DashboardApp(clock=lambda: NOW, watchlist=Watchlist(tmp_path / "w.json"))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.2)
            assert app.state.error and "Missing POLYMARKET_KEY_ID" in app.state.error

    run(scenario())


def test_rows_survive_with_no_markets_discovered_yet(tmp_path):
    async def scenario():
        app, _ = make_app(tmp_path, markets=[])
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause(0.2)
            table = app.query_one(DataTable)
            assert table.row_count == 0

    run(scenario())
