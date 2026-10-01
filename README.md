# Unofficial Bitcoin Up or Down 15 Minute Widget Tracker

A live widget for Polymarket US's **"BTC Up or Down: 15 min"** markets: the last 24 hours of
15-minute windows, colour-coded by result and net change, plus the live window with odds,
a live BTC price and a countdown.

> **Unofficial.** Not affiliated with, endorsed by, or connected to Polymarket or CF Benchmarks.
> Read-only market data. Nothing here places orders, and nothing here is financial advice.

**Status:** core library, `pm` CLI and the terminal widget implemented; desktop window and shortcut not started. See
[`docs/superpowers/specs/2026-09-30-btc15-widget-design.md`](docs/superpowers/specs/2026-09-30-btc15-widget-design.md).

## No API keys needed

The live widget and `pm btc15` read only **public** Polymarket US data and public exchange prices, so there is
nothing to sign up for or configure. API keys are needed only for the optional account commands
(`pm account`, `balances`, `positions`, `orders`) and the recorder: put them in a local `.env`
(`POLYMARKET_KEY_ID`, `POLYMARKET_SECRET_KEY`). `.env` is git-ignored. Never commit it.

## Usage

```
uv sync
uv run pm btc15 --hours 6     # one-shot styled table, last 6 hours (add --volume for volumes; slower)
uv run btc15-widget           # live widget: ticker + styled 24h table + colour key;
                              #   on terminals >=116 columns x 28 rows an ASCII coin appears whose ring is the analog countdown
                              #   (orange = time left, green/red = time used, by the current lean)
                              #   q quit · v table/strip view · r refresh · arrows/PgUp/PgDn scroll
uv run btc15-widget --snapshot  # print one plain-text frame and exit
uv run pytest                 # tests
```

Commands: see `CLAUDE.md`. Plans: `docs/superpowers/plans/`.

History for the last 24 hours loads in about a second with one request, and settled windows are cached locally.
The live price is an exchange-composite estimate (≈), not CF Benchmarks BRTI. Windows are coloured from real
settled BRTI; the live window is provisional.
