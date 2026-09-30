import pytest

from btc15_widget.proxy import QUOTE_URLS, apply_bias, composite, fetch_quotes, parse_quote


def test_quote_urls_cover_the_four_exchanges():
    assert set(QUOTE_URLS) == {"coinbase", "kraken", "bitstamp", "gemini"}


@pytest.mark.parametrize(
    "exchange, payload",
    [
        ("coinbase", {"price": "84000.10"}),
        ("kraken", {"result": {"XXBTZUSD": {"c": ["84000.10", "0.01"]}}}),
        ("bitstamp", {"last": "84000.10"}),
        ("gemini", {"last": "84000.10"}),
    ],
)
def test_parse_quote(exchange, payload):
    assert parse_quote(exchange, payload) == 84000.10


def test_composite_is_the_mean():
    assert composite({"a": 100.0, "b": 102.0}) == 101.0


def test_composite_drops_none_zero_negative():
    assert composite({"a": None, "b": 0, "c": -5, "d": 84000.0}) == 84000.0


def test_composite_drops_outlier():
    quotes = {"a": 84000.0, "b": 84010.0, "c": 84020.0, "d": 10.0}
    assert composite(quotes) == pytest.approx(84010.0)


def test_composite_all_bad_is_none():
    assert composite({"a": None, "b": 0}) is None
    assert composite({}) is None


def test_fetch_quotes_isolates_failures():
    def get_json(url):
        if "kraken" in url:
            raise OSError("down")
        if "coinbase" in url:
            return {"price": "84000"}
        return {"last": "84010"}

    quotes = fetch_quotes(get_json)
    assert quotes["kraken"] is None
    assert quotes["coinbase"] == 84000.0 and quotes["bitstamp"] == 84010.0 and quotes["gemini"] == 84010.0


def test_fetch_quotes_bad_payload_is_none():
    quotes = fetch_quotes(lambda url: {"unexpected": True})
    assert all(v is None for v in quotes.values())


def test_apply_bias():
    assert apply_bias(None) is None
    assert apply_bias(100.0, 4.0) == 104.0
    assert apply_bias(100.0) == 100.0
