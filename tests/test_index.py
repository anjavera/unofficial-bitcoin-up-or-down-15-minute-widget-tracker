import pytest

from btc15_widget.index import INDEX_URL, fetch_index, parse_index


def payload(*closes, tick_counts=None, start=1000):
    counts = tick_counts or [1] * len(closes)
    return {"series": [{"asset": {"assetClass": "ASSET_CLASS_CRYPTO", "symbol": "btc"}, "currency": "USD",
                        "candles": [{"timestamp": start + i, "close": c, "tickCount": n}
                                    for i, (c, n) in enumerate(zip(closes, counts))]}]}


def test_url_is_the_public_btc_one_second_series():
    assert "gateway.polymarket.us/v1/asset-prices/history" in INDEX_URL
    assert "assets=crypto:btc" in INDEX_URL and "ASSET_PRICE_BUCKET_1S" in INDEX_URL


def test_parse_takes_the_latest_real_candle():
    assert parse_index(payload("83585.57", "83590.26")) == (83590.26, 1001)


def test_parse_skips_gap_filled_candles():  # tickCount 0 = carried-forward, not a real publication
    assert parse_index(payload("83585.57", "83585.57", tick_counts=[1, 0])) == (83585.57, 1000)


@pytest.mark.parametrize("bad", [{}, {"series": []}, {"series": [{"candles": []}]},
                                 payload("0"), payload("nan"), payload("abc"), payload("-5"), None])
def test_parse_rejects_missing_or_bad_data(bad):
    assert parse_index(bad) is None


def test_parse_matches_the_btc_series_by_asset_not_position():
    eth = {"asset": {"assetClass": "ASSET_CLASS_CRYPTO", "symbol": "eth"}, "candles": [{"timestamp": 5, "close": "3000", "tickCount": 1}]}
    data = payload("83000.0")
    data["series"].insert(0, eth)
    assert parse_index(data) == (83000.0, 1000)


def test_fetch_uses_a_window_ending_now_and_returns_price_and_time():
    seen = []
    result = fetch_index(lambda url: seen.append(url) or payload("83000.5"))
    assert result == (83000.5, 1000) and len(seen) == 1


def test_fetch_failure_is_none_not_an_exception():
    def boom(url):
        raise OSError("down")

    assert fetch_index(boom) is None
