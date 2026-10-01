"""Terminal multi-market dashboard: crypto/sports/politics side by side, with a watchlist (Textual)."""

import argparse
import asyncio
import sys
import threading
from collections.abc import Callable
from datetime import datetime, timezone

from rich.console import Console
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Static

from btc15_widget.dashboard.discovery import DEFAULT_CATEGORIES, DEFAULT_PER_CATEGORY
from btc15_widget.dashboard.model import MarketQuote
from btc15_widget.dashboard.render import COLUMNS, build_dashboard_table
from btc15_widget.dashboard.sources import DISCOVERY_EVERY, DashboardSources, default_dashboard_sources
from btc15_widget.dashboard.state import DashboardState
from btc15_widget.dashboard.watchlist import Watchlist

STAR = "★"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _fmt_price(value: float | None) -> str:
    return f"{value:.3f}" if value is not None else "-"


def _fmt_qty(value: float) -> str:
    return f"{value:,.0f}" if value else "-"


class DashboardApp(App):
    CSS = """
    #status { dock: bottom; height: auto; }
    DataTable { height: 1fr; }
    """
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("w", "toggle_watch", "Pin/unpin"),
        ("r", "refresh_markets", "Refresh"),
    ]

    def __init__(
        self,
        sources: DashboardSources | None = None,
        categories: tuple[str, ...] = DEFAULT_CATEGORIES,
        per_category: int = DEFAULT_PER_CATEGORY,
        clock: Callable[[], datetime] = utcnow,
        watchlist: Watchlist | None = None,
    ) -> None:
        super().__init__()
        self._sources, self._categories, self._per_category, self.clock = sources, categories, per_category, clock
        self.state = DashboardState(watchlist=watchlist or Watchlist())
        self._row_slugs: list[str] = []
        self._stop = threading.Event()
        self._feed_stop = asyncio.Event()
        self._feed: object | None = None
        self._discovering = False

    def compose(self) -> ComposeResult:
        yield DataTable(id="table")
        yield Static(id="status")

    # ---- lifecycle -------------------------------------------------------------------------
    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        for name in COLUMNS:
            table.add_column(name)
        if self._sources is None:
            try:
                self._sources = default_dashboard_sources(self._categories, self._per_category)
            except Exception as e:  # missing credentials etc.: show it in the app, never a traceback
                self.state.error = str(e)[:200]
        self.refresh_view()
        if self._sources is not None:
            self._discover_now()
            self.run_worker(self._run_feed(), exit_on_error=False, group="feed")
        self.set_interval(1.0, self._on_second)

    def on_unmount(self) -> None:
        self._stop.set()
        self._feed_stop.set()
        if self._sources is not None:
            try:
                self._sources.close()
            except Exception:
                pass

    async def action_quit(self) -> None:
        self._stop.set()
        self._feed_stop.set()
        self.exit()

    # ---- background work -------------------------------------------------------------------
    def _apply(self, fn, *args) -> None:
        if self._stop.is_set():
            return
        try:
            self.call_from_thread(fn, *args)
        except Exception:
            pass

    def _discover_now(self) -> None:
        if self._discovering or self._sources is None:
            return
        self._discovering = True
        threading.Thread(target=self._discover, daemon=True, name="dashboard-discovery").start()

    def _discover(self) -> None:
        try:
            markets = self._sources.discover()
            self._apply(self.state.set_markets, markets, self.clock())
            self._apply(setattr, self.state, "error", None)
            if self._feed is not None:
                self._feed.request_resubscribe()
        except Exception as e:
            self._apply(setattr, self.state, "error", str(e)[:200])
        finally:
            self._discovering = False

    async def _run_feed(self) -> None:
        # the feed runs as a worker on the app's own event loop (not a separate thread), so it can
        # update state directly, the same way btc15_widget.app.WidgetApp._run_feed does
        self._feed = self._sources.feed_factory(lambda quote: self.state.apply_quote(quote, self.clock()), self.state.slugs)
        await self._feed.run(self._feed_stop)

    # ---- painting --------------------------------------------------------------------------
    def _on_second(self) -> None:
        now = self.clock()
        if self.state.markets_at is None or (now - self.state.markets_at).total_seconds() > DISCOVERY_EVERY:
            self._discover_now()
        self.refresh_view()

    def refresh_view(self) -> None:
        table = self.query_one(DataTable)
        now = self.clock()
        selected = (
            self._row_slugs[table.cursor_row]
            if self._row_slugs and table.cursor_row < len(self._row_slugs)
            else None
        )
        table.clear()
        self._row_slugs = []
        for summary, quote in self.state.rows():
            pinned = summary.slug in self.state.watchlist
            live = quote is not None and not self.state.is_stale(summary.slug, now)
            table.add_row(
                STAR if pinned else "",
                summary.category,
                summary.title,
                _fmt_price(quote.last_trade if quote else None),
                _fmt_price(quote.best_bid if quote else None),
                _fmt_price(quote.best_ask if quote else None),
                _fmt_price(quote.spread if quote else None),
                _fmt_qty(quote.bid_depth if quote else 0),
                _fmt_qty(quote.ask_depth if quote else 0),
            )
            self._row_slugs.append(summary.slug)
        if selected in self._row_slugs:
            table.cursor_coordinate = (self._row_slugs.index(selected), 0)
        parts = [f"markets: {len(self.state.markets)}", f"pinned: {len(self.state.watchlist)}"]
        parts.append(f"error: {self.state.error}" if self.state.error else "feed: live")
        self.query_one("#status", Static).update("  ".join(parts))

    # ---- actions ---------------------------------------------------------------------------
    def action_toggle_watch(self) -> None:
        table = self.query_one(DataTable)
        if not self._row_slugs or table.cursor_row >= len(self._row_slugs):
            return
        self.state.watchlist.toggle(self._row_slugs[table.cursor_row])
        if self._feed is not None:
            self._feed.request_resubscribe()
        self.refresh_view()

    def action_refresh_markets(self) -> None:
        self.state.markets_at = None  # forces discovery on the next second


async def _collect_quotes(sources: DashboardSources, state: DashboardState, clock: Callable[[], datetime], timeout: float = 5.0) -> None:
    """Listen to the live feed until at least one quote arrives (or `timeout`)."""
    got = asyncio.Event()

    def on_quote(quote: MarketQuote) -> None:
        state.apply_quote(quote, clock())
        got.set()

    feed = sources.feed_factory(on_quote, state.slugs)
    stop = asyncio.Event()
    task = asyncio.create_task(feed.run(stop))
    try:
        await asyncio.wait_for(got.wait(), timeout)
    except asyncio.TimeoutError:
        pass
    stop.set()
    await asyncio.wait({task}, timeout=2)


def _print_snapshot(sources: DashboardSources, clock: Callable[[], datetime]) -> None:
    state = DashboardState()
    state.set_markets(sources.discover(), clock())
    asyncio.run(_collect_quotes(sources, state, clock))
    Console().print(build_dashboard_table(state, clock()))


def main(
    argv: list[str] | None = None, sources: DashboardSources | None = None, clock: Callable[[], datetime] = utcnow
) -> None:
    parser = argparse.ArgumentParser(prog="market-dashboard", description="Live multi-market terminal dashboard")
    parser.add_argument("--snapshot", action="store_true", help="print one plain-text frame and exit")
    parser.add_argument(
        "--categories", default=",".join(DEFAULT_CATEGORIES), help="comma-separated categories, e.g. crypto,sports,politics"
    )
    parser.add_argument("--per-category", type=int, default=DEFAULT_PER_CATEGORY, help="top markets to show per category")
    args = parser.parse_args(argv)
    categories = tuple(c.strip() for c in args.categories.split(",") if c.strip())

    if not args.snapshot:
        DashboardApp(sources=sources, categories=categories, per_category=args.per_category, clock=clock).run()
        return
    try:
        _print_snapshot(sources or default_dashboard_sources(categories, args.per_category), clock)
    except Exception as e:
        print(f"Error: {str(e)[:300]}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
