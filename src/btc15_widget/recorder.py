"""Record live Polymarket US BTC 15m market data (prices + trades) to JSONL.

Usage: btc15-record --hours 4 --out data/live.jsonl
Reads POLYMARKET_KEY_ID / POLYMARKET_SECRET_KEY from the environment or a .env. Read-only.
"""

import argparse
import asyncio
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from polymarket_us.websocket import MarketsWebSocket

from btc15_widget.windows import window_slugs

SESSION_SECONDS = 3600  # reconnect hourly so the subscribed window list stays current
WINDOWS_AHEAD = 6


def load_credentials() -> tuple[str, str]:
    load_dotenv(find_dotenv(usecwd=True))
    load_dotenv(Path.home() / "polymarket-bot" / ".env")
    return os.environ["POLYMARKET_KEY_ID"], os.environ["POLYMARKET_SECRET_KEY"]


def classify(message: dict) -> str:
    for kind in ("marketDataLite", "marketData", "trade", "heartbeat", "error"):
        if kind in message:
            return kind
    return "other"


async def run_session(creds, out, seconds: float, counts: Counter) -> None:
    ws = MarketsWebSocket(key_id=creds[0], secret_key=creds[1])

    def on_message(message: dict) -> None:
        kind = classify(message)
        counts[kind] += 1
        out.write(json.dumps({"t": time.time(), "kind": kind, "msg": message}) + "\n")

    ws.on("message", on_message)
    ws.on("error", lambda e: print(f"{datetime.now(timezone.utc):%H:%M:%SZ} ws error: {str(e)[:120]}", flush=True))
    closed = asyncio.Event()
    ws.on("close", closed.set)

    slugs = window_slugs(datetime.now(timezone.utc), WINDOWS_AHEAD)
    await ws.connect()
    await ws.subscribe_market_data_lite("lite", slugs)
    await ws.subscribe_trades("trades", slugs)
    try:
        await asyncio.wait_for(closed.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass
    finally:
        await ws.close()


async def record(creds, path: Path, hours: float) -> Counter:
    counts: Counter = Counter()
    deadline = time.monotonic() + hours * 3600
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", buffering=1) as out:
        failures = 0
        while (remaining := deadline - time.monotonic()) > 1:
            try:
                await run_session(creds, out, min(SESSION_SECONDS, remaining), counts)
                failures = 0
            except Exception as e:  # connection dropped or refused: back off and reconnect
                failures += 1
                print(f"{datetime.now(timezone.utc):%H:%M:%SZ} session failed ({failures}): {str(e)[:120]}", flush=True)
                await asyncio.sleep(min(5 * failures, 60))
    return counts


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hours", type=float, default=4)
    parser.add_argument("--out", type=Path, default=Path("data/live.jsonl"))
    args = parser.parse_args(argv)
    print(f"recording {args.hours}h to {args.out}", flush=True)
    counts = asyncio.run(record(load_credentials(), args.out, args.hours))
    print("done:", dict(counts), flush=True)


if __name__ == "__main__":
    main()
