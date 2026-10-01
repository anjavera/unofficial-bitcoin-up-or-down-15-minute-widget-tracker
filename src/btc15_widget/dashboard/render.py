"""Pure renderer: dashboard state in, a rich Table out."""

from datetime import datetime

from rich import box
from rich.style import Style
from rich.table import Table

from btc15_widget.dashboard.state import DashboardState

STAR = "★"
ZEBRA = "#e6edf3 on #161b22"
DIM = Style(dim=True)
COLUMNS = ["", "Category", "Market", "Last", "Bid", "Ask", "Spread", "Bid Depth", "Ask Depth"]


def _fmt_price(value: float | None) -> str:
    return f"{value:.3f}" if value is not None else "-"


def _fmt_qty(value: float) -> str:
    return f"{value:,.0f}" if value else "-"


def build_dashboard_table(state: DashboardState, now: datetime) -> Table:
    table = Table(box=box.SQUARE, padding=(0, 1), show_lines=False, row_styles=["", ZEBRA],
                  border_style="grey50", header_style="bold")
    for name in COLUMNS:
        table.add_column(name, justify="left" if name in ("", "Category", "Market") else "right", no_wrap=True)
    for summary, quote in state.rows():
        pinned = summary.slug in state.watchlist
        live = quote is not None and not state.is_stale(summary.slug, now)
        style = None if live else DIM
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
            style=style,
        )
    return table
