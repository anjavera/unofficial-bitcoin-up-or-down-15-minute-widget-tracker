# BTC 15-Minute Up/Down Widget: Design

Date: 2026-09-30 · Status: approved by the project owner, pending spec review

## Purpose
Show the last 24 hours (96 windows) of Polymarket US "BTC Up or Down: 15 min" markets plus the
live window, aligned as closely as possible with the price source Polymarket settles against.

## Price source
Polymarket settles each window on **CF Benchmarks' Bitcoin Real-Time Index (BRTI)**: the average of
60 BRTI prices in the last minute before each boundary, rounded to 2 decimals. Up if close >= open
("Yes" = Up). Polymarket's API exposes the open (`assetPriceTerms.priceToBeat`) and, after settling,
the close (`settlementPrice`), but no live BRTI. CF Benchmarks' live feed is licensed data; an
official feed can replace the proxy below later. CF Benchmarks publishes no pricing or free tier; real-time
access is by licence enquiry. **Decision (owner): no paid data sources for now, so the proxy below is used.**

## Data
- **No API keys** are needed for the widget or `pm btc15`; keys only serve account commands and the recorder.
- **History (exact):** settled windows from Polymarket, addressed by slug
  `btc-updown-15m-YYYY-MM-DD-HHMMz` (market slug prefixed `cpc-`). Cached locally; only new windows fetched.
- **Live Polymarket (keyless, updated 2026-10-01):** poll the public order book (`markets.book`) every 2 s for the
  live window: Up price = midpoint of best bid/ask (last trade if one side is empty), spread, last trade. The keyed
  WebSocket and `markets.bbo` are not used (`bbo` returns 404 for a live market for minutes after it opens).
- **History bulk request:** one `events.list({"slug": [...], "limit": 100})` returns up to 100 windows (0.5 s for 97);
  per-window requests remain only as a fallback. Volume needs one extra request per window, so it is opt-in.
- **Live BTC (proxy):** composite (mean) of Coinbase, Kraken, Bitstamp, Gemini public data, shown as
  "≈". Calibration on 17 settled windows (minute-before-boundary candles vs BRTI open):
  composite mean |error| $4.65, max $9.12, bias about -$4; per exchange mean |error| $4.1 to $9.7.
  Show the measured error in the UI and re-measure periodically; optionally apply the bias offset.
- **Rule:** proxy values never enter history. A window's colour comes from real BRTI once settled;
  the live window is marked provisional. The smallest colour band ($10) is about 2x proxy error.
- Rate limits: Polymarket REST can trip Cloudflare 1015; use backoff and cache (see `btc15.py` retry).

## Display
- Header: live proxy price, price to beat, gap, countdown to window end.
- Odds: Up/Down price, spread.
- 96-window strip. Result mark: **green = UP, red = DOWN**. Fill = net-change gradient:
  **positive = blue, negative = orange**, 9 steps of increasing intensity by |net change|:
  0-10, 10-25, 25-50, 50-100, 100-200, 200-300, 300-400, 400-500, 500-1000 (capped at 1000+).
  Smallest step is a pale tint so it reads on dark backgrounds.
- Signals row (see below).

## Theme
**Dark only.** Light mode (and the dark/light/system switch, `--theme` flag and config file) was dropped on
2026-09-30 after review. Palettes stay behind a `theme` argument, so another theme could be added later.

## Architecture
1. `core` (no UI): history cache, Polymarket WebSocket client, proxy price aggregator, colour banding.
2. Terminal widget (Textual), `pm widget`.
3. Desktop window: same core, small native window (pywebview or similar). Always-on-top optional.

## Signals
Display-only, disabled by default. Enabled only for patterns that survive across many complete windows
(candidates come from the recorded per-minute data analysis). No order placement anywhere in the widget.

## Testing
Unit tests: colour-band boundaries (both signs, cap), slug/window generation across hour and day
boundaries, proxy composite maths, UP/DOWN rule (>=). Live parts verified against real data.

## Decisions
- Theme: dark only (light mode dropped 2026-09-30).
- No paid data sources for now; revisit official BRTI access only if it proves to be free.
- This repo will absorb the existing `pm` CLI code (`client`, `cli`, `btc15`) so there is one project.

## Later
- Desktop shortcut: a Linux `.desktop` launcher (and install script) that opens the desktop window.
  Not part of the first milestones.

## Open items
- None blocking; signal definitions wait on the recorded-data analysis (recording must be restarted, see notes).
