# Unofficial Bitcoin Up or Down 15 Minute Widget Tracker

A live widget for Polymarket US's **"BTC Up or Down: 15 min"** markets: the last 24 hours of
15-minute windows, colour-coded by result and net change, plus the live window with odds,
a live BTC price and a countdown.

> **Unofficial.** Not affiliated with, endorsed by, or connected to Polymarket or CF Benchmarks.
> Read-only market data. Nothing here places orders, and nothing here is financial advice.

**Status:** core library and `pm` CLI implemented (history, live feed, price proxy, colour bands, themes); widgets not started. See
[`docs/superpowers/specs/2026-09-30-btc15-widget-design.md`](docs/superpowers/specs/2026-09-30-btc15-widget-design.md).

## Credentials

Polymarket US API keys are read from a local `.env` (`POLYMARKET_KEY_ID`, `POLYMARKET_SECRET_KEY`).
`.env` is git-ignored. Never commit it.

## Usage

```
uv sync
uv run pm btc15 --hours 6     # last 6 hours of windows
uv run pytest                 # tests
```

Commands: see `CLAUDE.md`. Plans: `docs/superpowers/plans/`.
