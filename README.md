# Unofficial Bitcoin Up or Down 15 Minute Widget Tracker

Unofficial terminal tooling for Polymarket US: a live widget for the **"BTC Up or Down: 15 min"** market
(the last 24 hours of 15-minute windows, colour-coded by result and net change, plus the live window with
odds, a live BTC price and a countdown), and a **multi-market dashboard** that lists crypto, sports and
politics markets side by side with live order-book depth and a pinnable watchlist.

> **Unofficial.** Not affiliated with, endorsed by, or connected to Polymarket or CF Benchmarks.
> Read-only market data. Nothing here places orders, and nothing here is financial advice.

**Status:** core library, `pm` CLI, the BTC-15 terminal widget and the multi-market dashboard implemented;
desktop window and shortcut not started. See
[`docs/superpowers/specs/2026-09-30-btc15-widget-design.md`](docs/superpowers/specs/2026-09-30-btc15-widget-design.md).

**Why the dashboard lives in this repo instead of a new one:** it is a direct sequel to the BTC-15 widget —
same read-only client, same reconnecting-websocket feed pattern, same Textual/rich rendering approach — built
to compound the credibility of the first widget for a reviewer rather than starting cold. See
`src/btc15_widget/dashboard/` for the extension (discovery, watchlist, multi-market feed, dashboard app).

## Credentials

Polymarket US API keys are read from a local `.env` (`POLYMARKET_KEY_ID`, `POLYMARKET_SECRET_KEY`).
`.env` is git-ignored. Never commit it.

## Usage

```
uv sync
uv run pm btc15 --hours 6     # one-shot styled table, last 6 hours
uv run btc15-widget           # live widget: ticker + styled 24h table + colour key;
                              #   on terminals >=116 columns x 28 rows an ASCII coin appears whose ring is the analog countdown
                              #   (orange = time left, green/red = time used, by the current lean)
                              #   q quit · v table/strip view · r refresh · arrows/PgUp/PgDn scroll
uv run btc15-widget --snapshot  # print one plain-text frame and exit
uv run market-dashboard       # live multi-market dashboard: crypto/sports/politics, order-book depth, watchlist
                              #   q quit · w pin/unpin highlighted market · r refresh markets
uv run pm watchlist add <market-slug>   # pin a market so it always sorts first in the dashboard
uv run pytest                 # tests
```

Commands: see `CLAUDE.md`. Plans: `docs/superpowers/plans/`.

First run fetches 24 hours of history (a few minutes); later runs reuse a local cache and start in seconds.
The live price is an exchange-composite estimate (≈), not CF Benchmarks BRTI. Windows are coloured from real
settled BRTI; the live window is provisional.
