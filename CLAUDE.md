# Unofficial Bitcoin Up or Down 15 Minute Widget Tracker

Polymarket US (https://docs.polymarket.us) read-only tooling using the `polymarket-us` Python SDK, managed with uv.
Design: `docs/superpowers/specs/`, plans: `docs/superpowers/plans/`.

- The widget and `pm btc15` need **no keys** (public data): use `btc15_widget.client.get_public_client()`. If the user has set up keys, the widget uses the faster authenticated WebSocket feed automatically (`feed: live (keyed)`); `--keyless` ignores them.
- Keys (`POLYMARKET_KEY_ID` / `POLYMARKET_SECRET_KEY`, from the environment, a `.env`, or `~/polymarket-bot/.env`) are only for account commands and the recorder: `get_client()`. Never print or cat them; the secret is base64 and ends in `=`.

## Live data (read-only)

Run from this directory. Add `--json` before the command for machine-readable output.

    uv run pm account              # balances + positions (with live bid/ask) + open orders
    uv run pm balances | positions | orders
    uv run pm search "yankees"     # find events and market slugs
    uv run pm price <market-slug>  # best bid/ask, last trade
    uv run pm book <market-slug> --depth 10
    uv run pm market <market-slug>
    uv run pm --json event <event-slug>
    uv run pm btc15 [--hours 6] [--volume]   # one-shot styled table (Chg $/% blue-orange gradient, Result green/red, volume)
    uv run btc15-widget [--snapshot] [--keyless]   # live widget: ticker, styled table, colour key, ASCII coin = analog countdown on wide terminals (also: uv run pm widget)
                                   # keys: q quit, v table/strip view, r refresh, arrows/PgUp/PgDn scroll
    uv run btc15-record --hours 4 --out data/live.jsonl   # record live ticks + trades
    uv run btc15-summarize data/live.jsonl

Rapid-fire calls can trip a Cloudflare 1015 rate limit; wait a minute.

The CLI is read-only. Placing, modifying or cancelling orders spends real money; nothing in this project does that.
