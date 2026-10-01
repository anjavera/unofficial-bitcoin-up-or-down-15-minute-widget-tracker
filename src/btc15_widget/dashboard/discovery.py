"""REST market discovery across categories (crypto, sports, politics, ...)."""

from btc15_widget.dashboard.model import MarketSummary

DEFAULT_CATEGORIES = ("crypto", "sports", "politics")
DEFAULT_PER_CATEGORY = 8
EVENTS_PAGE_SIZE = 25


def _market_summaries(event: dict, category: str) -> list[MarketSummary]:
    out = []
    for m in event.get("markets") or []:
        slug = m.get("slug")
        if not slug or m.get("closed"):
            continue
        out.append(
            MarketSummary(
                slug=slug,
                title=m.get("title") or event.get("title") or slug,
                category=category,
                event_slug=event.get("slug", ""),
                volume=float(m.get("volume") or event.get("volume") or 0.0),
                active=m.get("active", True),
            )
        )
    return out


def discover_markets(
    client, categories: tuple[str, ...] = DEFAULT_CATEGORIES, per_category: int = DEFAULT_PER_CATEGORY
) -> list[MarketSummary]:
    """The `per_category` highest-volume active markets for each requested category.

    One REST call per category (the API filters by a single `categories` list, but querying
    separately keeps each category's top-N independent of how much liquidity the others have).
    """
    found: list[MarketSummary] = []
    for category in categories:
        data = client.events.list({"categories": [category], "active": True, "closed": False, "limit": EVENTS_PAGE_SIZE})
        summaries = [s for event in data.get("events", []) for s in _market_summaries(event, category)]
        summaries.sort(key=lambda s: s.volume, reverse=True)
        found.extend(summaries[:per_category])
    return found
