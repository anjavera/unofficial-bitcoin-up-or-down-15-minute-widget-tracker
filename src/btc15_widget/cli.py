"""Read-only command line tool for live Polymarket US data.

Usage: uv run pm <command> [args] [--json]
"""

import argparse
import json
import sys
from datetime import datetime, timezone


from btc15_widget.client import get_client, get_public_client
from btc15_widget.history import HISTORY_CACHE, load_history
from btc15_widget.model import Window
from btc15_widget.render import build_table, print_table  # noqa: F401  (re-exported for callers and tests)



def usd(amount) -> str:
    if not amount:
        return "-"
    return f"${float(amount['value']):.4f}"


def cmd_balances(client, args):
    data = client.account.balances()
    if args.json:
        return data
    for b in data["balances"]:
        print(f"Balance:        ${b['currentBalance']:.2f} {b['currency']}")
        print(f"Buying power:   ${b['buyingPower']:.2f}")
        print(f"Withdrawable:   ${b['availableToWithdraw']:.2f}")
        print(f"Open orders:    ${b['openOrders']:.2f}")


def cmd_positions(client, args):
    data = client.portfolio.positions()
    if args.json:
        return data
    positions = data.get("positions") or {}
    if not positions:
        print("No positions.")
        return
    for slug, p in positions.items():
        meta = p.get("marketMetadata", {})
        bbo = client.markets.bbo(slug)["marketData"]
        print(f"{meta.get('title', slug)} — {meta.get('outcome', '')}")
        print(f"  slug: {slug}")
        print(f"  net position: {p['netPosition']}  cost: {usd(p.get('cost'))}  realized: {usd(p.get('realized'))}")
        print(f"  now: bid {usd(bbo.get('bestBid'))} / ask {usd(bbo.get('bestAsk'))}  last {usd(bbo.get('lastTradePx'))}")


def cmd_orders(client, args):
    data = client.orders.list()
    if args.json:
        return data
    orders = data.get("orders") or []
    if not orders:
        print("No open orders.")
    for o in orders:
        print(json.dumps(o, indent=2))


def cmd_account(client, args):
    if args.json:
        return {
            "balances": client.account.balances(),
            "positions": client.portfolio.positions(),
            "orders": client.orders.list(),
        }
    print("== Balances"); cmd_balances(client, args)
    print("\n== Positions"); cmd_positions(client, args)
    print("\n== Open orders"); cmd_orders(client, args)


def cmd_search(client, args):
    data = client.search.query({"query": args.query, "limit": args.limit, "status": args.status})
    if args.json:
        return data
    for e in data.get("events", []):
        print(f"{e['title']}  ({e.get('startDate', '')})  event: {e['slug']}")
        for m in e.get("markets", []):
            prices = dict(zip(json.loads(m.get("outcomes", "[]")), json.loads(m.get("outcomePrices", "[]"))))
            price_str = "  ".join(f"{k} {v}" for k, v in prices.items())
            print(f"  - {m.get('question', m['slug'])}\n      {m['slug']}  {price_str}")


def cmd_price(client, args):
    data = client.markets.bbo(args.slug)
    if args.json:
        return data
    d = data["marketData"]
    print(f"{d['marketSlug']}  [{d.get('state', '')}]")
    print(f"  bid {usd(d.get('bestBid'))}  ask {usd(d.get('bestAsk'))}  last {usd(d.get('lastTradePx'))}")
    print(f"  traded {d.get('sharesTraded')}  open interest {d.get('openInterest')}")


def cmd_book(client, args):
    data = client.markets.book(args.slug)
    if args.json:
        return data
    d = data["marketData"]
    print(f"{d['marketSlug']}  [{d.get('state', '')}]")
    print(f"{'BID qty':>12} {'price':>8} | {'price':<8} {'ASK qty':<12}")
    bids, asks = d.get("bids", [])[: args.depth], d.get("offers", [])[: args.depth]
    for i in range(max(len(bids), len(asks))):
        b = bids[i] if i < len(bids) else None
        a = asks[i] if i < len(asks) else None
        left = f"{float(b['qty']):>12.0f} {b['px']['value']:>8}" if b else " " * 21
        right = f"{a['px']['value']:<8} {float(a['qty']):<12.0f}" if a else ""
        print(f"{left} | {right}")


def cmd_market(client, args):
    data = client.markets.retrieve_by_slug(args.slug)
    if args.json:
        return data
    m = data["market"]
    print(m.get("question") or m.get("title"))
    print(f"  {m['slug']}  status {m.get('status')}  ends {m.get('endDate')}")
    prices = dict(zip(json.loads(m.get("outcomes", "[]")), json.loads(m.get("outcomePrices", "[]"))))
    print("  " + "  ".join(f"{k} {v}" for k, v in prices.items()))
    print(f"  {m.get('description', '')}")


def cmd_event(client, args):
    return client.events.retrieve_by_slug(args.slug)


def windows_to_json(windows: list[Window]) -> list[dict]:
    return [
        {"start": w.start.isoformat(), "open": w.open, "close": w.close, "net": w.net, "result": w.result,
         "status": w.status, "volume": w.volume, "error": w.error}
        for w in windows
    ]


def cmd_btc15(client, args):
    windows = load_history(client, datetime.now(timezone.utc), hours=args.hours, cache_path=HISTORY_CACHE,
                           with_volume=args.volume)
    if args.json:
        return windows_to_json(windows)
    print_table(windows)


AUTH_COMMANDS = {"account", "balances", "positions", "orders"}  # the only commands that need API keys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pm", description="Live Polymarket US data (read-only)")
    parser.add_argument("--json", action="store_true", help="print the raw API response")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("account", help="balances, positions and open orders").set_defaults(func=cmd_account)
    sub.add_parser("balances").set_defaults(func=cmd_balances)
    sub.add_parser("positions").set_defaults(func=cmd_positions)
    sub.add_parser("orders", help="open orders").set_defaults(func=cmd_orders)

    p = sub.add_parser("search", help="search events and their markets")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--status", choices=["active", "closed", "upcoming"], default="active")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("widget", help="live terminal widget for the BTC 15-minute markets")
    p.add_argument("--snapshot", action="store_true", help="print one plain-text frame and exit")
    p.add_argument("--keyless", action="store_true", help="ignore any API keys and use public data only")

    p = sub.add_parser("btc15", help="recent BTC 15-minute Up/Down windows (no API keys needed)")
    p.add_argument("--hours", type=float, default=6)
    p.add_argument("--volume", action="store_true", help="also fetch each window's volume (slower)")
    p.set_defaults(func=cmd_btc15)

    for name, func, help_text in [
        ("price", cmd_price, "best bid/ask and last trade"),
        ("book", cmd_book, "order book"),
        ("market", cmd_market, "market details"),
        ("event", cmd_event, "event details (raw JSON)"),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.add_argument("slug")
        if name == "book":
            p.add_argument("--depth", type=int, default=10)
        p.set_defaults(func=func)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "widget":  # needs no API client up front: the widget reports credential problems itself
        from btc15_widget import app

        app.main((["--snapshot"] if args.snapshot else []) + (["--keyless"] if args.keyless else []))
        return
    client = None
    try:
        client = get_client() if args.command in AUTH_COMMANDS else get_public_client()
        result = args.func(client, args)
    except Exception as e:
        msg = str(e)
        if "Error 1015" in msg or "rate limited" in msg:
            msg = "rate limited by Polymarket (Cloudflare 1015) — wait a minute and retry"
        elif msg.lstrip().startswith("<"):
            msg = "the API returned an HTML error page (blocked or unavailable)"
        sys.exit(f"Error: {msg[:500]}")
    finally:
        if client is not None:
            client.close()
    if result is not None:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
