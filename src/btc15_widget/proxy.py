"""Live BTC price proxy: composite of public exchange quotes (an approximation of BRTI)."""

import json
import statistics
import urllib.request
from concurrent.futures import ThreadPoolExecutor

QUOTE_URLS = {
    "coinbase": "https://api.exchange.coinbase.com/products/BTC-USD/ticker",
    "kraken": "https://api.kraken.com/0/public/Ticker?pair=XBTUSD",
    "bitstamp": "https://www.bitstamp.net/api/v2/ticker/btcusd/",
    "gemini": "https://api.gemini.com/v1/pubticker/btcusd",
}


def _http_get_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "btc15-widget"})
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def parse_quote(exchange: str, payload: dict) -> float:
    if exchange == "coinbase":
        return float(payload["price"])
    if exchange == "kraken":
        return float(next(iter(payload["result"].values()))["c"][0])
    return float(payload["last"])  # bitstamp, gemini


def composite(quotes: dict[str, float | None], max_dev: float = 0.05) -> float | None:
    """Mean of valid quotes, ignoring any more than `max_dev` from the median; None if none remain."""
    valid = [v for v in quotes.values() if v is not None and v > 0]
    if not valid:
        return None
    median = statistics.median(valid)
    kept = [v for v in valid if abs(v - median) <= max_dev * median]
    return statistics.fmean(kept)


def fetch_quotes(get_json=_http_get_json) -> dict[str, float | None]:
    def one(item):
        exchange, url = item
        try:
            return exchange, parse_quote(exchange, get_json(url))
        except Exception:
            return exchange, None

    with ThreadPoolExecutor(max_workers=len(QUOTE_URLS)) as pool:
        return dict(pool.map(one, QUOTE_URLS.items()))


def apply_bias(value: float | None, bias: float = 0.0) -> float | None:
    return None if value is None else value + bias
