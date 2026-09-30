"""Per-window, per-minute summary of recorder output. Usage: btc15-summarize data/live.jsonl"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone


def px(d):
    return float(d["value"]) if d else None


def load(path: str) -> dict:
    wins = defaultdict(lambda: {"ticks": [], "trades": []})
    for line in open(path):
        r = json.loads(line)
        m = r["msg"]
        if r["kind"] == "marketDataLite":
            d = m["marketDataLite"]
            wins[d["marketSlug"]]["ticks"].append(
                (r["t"], px(d.get("currentPx")), px(d.get("bestBid")), px(d.get("bestAsk")))
            )
        elif r["kind"] == "trade":
            d = m["trade"]
            wins[d["marketSlug"]]["trades"].append((r["t"], px(d["price"]), float(d["quantity"]["value"])))
    return wins


def main(argv: list[str] | None = None) -> None:
    wins = load((argv or sys.argv[1:])[0])
    for slug in sorted(wins):
        w = wins[slug]
        if not w["ticks"]:
            continue
        print(f"== {slug}  ticks={len(w['ticks'])} trades={len(w['trades'])}")
        by_min = defaultdict(list)
        for t, cur, bid, ask in w["ticks"]:
            by_min[int(t // 60)].append((cur, bid, ask))
        for mn in sorted(by_min):
            v = by_min[mn]
            c = [x[0] for x in v if x[0] is not None]
            if not c:
                continue
            sp = [x[2] - x[1] for x in v if x[1] is not None and x[2] is not None]
            tr = [x for x in w["trades"] if int(x[0] // 60) == mn]
            print(
                f"  {datetime.fromtimestamp(mn * 60, timezone.utc):%H:%M}Z upPx open {c[0]:.2f} hi {max(c):.2f} "
                f"lo {min(c):.2f} close {c[-1]:.2f} spread {sum(sp) / len(sp) if sp else float('nan'):.3f} "
                f"trades {len(tr)} qty {sum(x[2] for x in tr):.0f}"
            )


if __name__ == "__main__":
    main()
