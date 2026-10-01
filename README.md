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
nothing to sign up for or configure. Just run it.

## Optional: use your own Polymarket US API keys

Keys are optional. With keys the widget switches automatically to Polymarket's faster live feed (updates are
pushed to you instead of polled every 2 seconds), and you can use the account commands (`pm account`,
`balances`, `positions`, `orders`) and the recorder. **Everyone needs their own keys: never share or reuse
anyone else's.**

How to get your own keys (from Polymarket US's official docs,
<https://docs.polymarket.us/api-reference/authentication>):

1. Download the **Polymarket US app** and create an account.
2. Complete **identity verification** in the app.
3. Go to <https://polymarket.us/developer> and sign in **the same way you sign in to the app** (Apple, Google or
   email). Switching sign-in methods can break your key.
4. Create a new key. You get a **Key ID** and a **Secret Key**. The secret key is shown **only once**: copy it
   somewhere safe before closing the dialog.
5. Put them in a file named `.env` in this project's folder (or set them as environment variables):

   ```
   POLYMARKET_KEY_ID=your-key-id
   POLYMARKET_SECRET_KEY=your-secret-key
   ```

The widget finds the keys by itself; the status line then shows `feed: live (keyed)`. To ignore your keys and use
public data only, run `btc15-widget --keyless` (the status line shows `feed: live (keyless)`).

**Keep your keys safe.** Polymarket's docs do not say whether a key can be limited to read-only, so assume a key
could be used to place orders. `.env` is git-ignored here; never commit it or paste it anywhere. If a key is ever
exposed, revoke it at <https://polymarket.us/developer>. This project only reads data and never places orders.

## Usage

```
uv sync
uv run pm btc15 --hours 6     # one-shot styled table, last 6 hours (add --volume for volumes; slower)
uv run btc15-widget           # (add --keyless to ignore any API keys)  live widget: ticker + styled 24h table + colour key;
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
