from btc15_widget.dashboard.discovery import discover_markets


class FakeEvents:
    def __init__(self, by_category):
        self.by_category, self.calls = by_category, []

    def list(self, params):
        self.calls.append(params)
        return {"events": self.by_category.get(params["categories"][0], [])}


class FakeClient:
    def __init__(self, by_category):
        self.events = FakeEvents(by_category)


def event(slug, title, markets):
    return {"slug": slug, "title": title, "volume": 0, "markets": markets}


def market(slug, title, volume, closed=False, active=True):
    return {"slug": slug, "title": title, "volume": volume, "closed": closed, "active": active}


def test_discover_queries_each_category_separately():
    client = FakeClient({"crypto": [], "sports": [], "politics": []})
    discover_markets(client, categories=("crypto", "sports", "politics"))
    assert [c["categories"] for c in client.events.calls] == [["crypto"], ["sports"], ["politics"]]
    assert all(c["active"] and not c["closed"] for c in client.events.calls)


def test_discover_flattens_event_markets_into_summaries():
    by_category = {
        "crypto": [event("ev-btc", "BTC event", [market("m1", "BTC up", 1000.0)])],
        "sports": [],
        "politics": [],
    }
    client = FakeClient(by_category)
    [summary] = discover_markets(client, categories=("crypto", "sports", "politics"))
    assert summary.slug == "m1" and summary.title == "BTC up" and summary.category == "crypto"
    assert summary.event_slug == "ev-btc" and summary.volume == 1000.0


def test_discover_skips_markets_without_a_slug_or_that_are_closed():
    markets = [market("", "no slug", 10.0), market("closed", "closed one", 10.0, closed=True), market("ok", "ok", 10.0)]
    client = FakeClient({"crypto": [event("e", "e", markets)], "sports": [], "politics": []})
    summaries = discover_markets(client, categories=("crypto", "sports", "politics"))
    assert [s.slug for s in summaries] == ["ok"]


def test_discover_sorts_by_volume_and_truncates_per_category():
    markets = [market(f"m{i}", f"m{i}", volume=i) for i in range(5)]
    client = FakeClient({"crypto": [event("e", "e", markets)], "sports": [], "politics": []})
    summaries = discover_markets(client, categories=("crypto", "sports", "politics"), per_category=2)
    assert [s.slug for s in summaries] == ["m4", "m3"]


def test_discover_falls_back_to_event_title_and_volume():
    markets = [{"slug": "m1"}]  # no title/volume/active/closed on the market itself
    client = FakeClient({"crypto": [event("ev", "Event title", markets)], "sports": [], "politics": []})
    client.events.by_category["crypto"][0]["volume"] = 42.0
    [summary] = discover_markets(client, categories=("crypto",))
    assert summary.title == "Event title" and summary.volume == 42.0 and summary.active is True
