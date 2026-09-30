"""Measure how far the exchange composite sits from settled BRTI (Polymarket's window opens)."""

from dataclasses import dataclass
from datetime import datetime

from btc15_widget.model import Window
from btc15_widget.proxy import composite, http_get_json


@dataclass(frozen=True)
class Calibration:
    n: int
    bias: float  # mean(proxy - BRTI); negative means the proxy reads low
    mean_abs_error: float
    max_abs_error: float


def measure(windows: list[Window], candles: dict[str, dict[int, float]]) -> Calibration | None:
    """Compare each window's BRTI open with the composite of the candles for the minute before it."""
    errors = []
    for w in windows:
        if w.open is None:
            continue
        minute = int(w.start.timestamp()) - 60
        proxy = composite({ex: series.get(minute) for ex, series in candles.items()})
        if proxy is not None:
            errors.append(proxy - w.open)
    if not errors:
        return None
    return Calibration(
        n=len(errors),
        bias=sum(errors) / len(errors),
        mean_abs_error=sum(abs(e) for e in errors) / len(errors),
        max_abs_error=max(abs(e) for e in errors),
    )


def _typical(o: float, h: float, l: float, c: float) -> float:
    return (o + h + l + c) / 4


def _coinbase(data) -> dict[int, float]:
    return {int(t): _typical(o, h, lo, c) for t, lo, h, o, c, _v in data}


def _kraken(data) -> dict[int, float]:
    rows = next(v for k, v in data["result"].items() if k != "last")
    return {int(r[0]): _typical(*map(float, r[1:5])) for r in rows}


def _bitstamp(data) -> dict[int, float]:
    return {int(r["timestamp"]): _typical(*(float(r[k]) for k in ("open", "high", "low", "close")))
            for r in data["data"]["ohlc"]}


def _gemini(data) -> dict[int, float]:
    return {int(r[0] // 1000): _typical(*r[1:5]) for r in data}


def fetch_candles(start: datetime, end: datetime, get_json=http_get_json) -> dict[str, dict[int, float]]:
    """1-minute typical prices keyed by epoch-minute; an exchange that fails is left out."""
    urls = {
        "coinbase": (f"https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=60"
                     f"&start={start.isoformat()}&end={end.isoformat()}", _coinbase),
        "kraken": (f"https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=1&since={int(start.timestamp())}", _kraken),
        "bitstamp": (f"https://www.bitstamp.net/api/v2/ohlc/btcusd/?step=60&limit=1000&start={int(start.timestamp())}", _bitstamp),
        "gemini": ("https://api.gemini.com/v2/candles/btcusd/1m", _gemini),
    }
    out = {}
    for name, (url, parse) in urls.items():
        try:
            out[name] = parse(get_json(url))
        except Exception:
            continue
    return out
