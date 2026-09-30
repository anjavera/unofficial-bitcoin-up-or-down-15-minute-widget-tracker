"""Polymarket US credentials and client construction (read-only use)."""

import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from polymarket_us import PolymarketUS


def load_credentials() -> tuple[str, str]:
    load_dotenv(find_dotenv(usecwd=True))
    load_dotenv(Path.home() / "polymarket-bot" / ".env")
    key_id, secret = os.environ.get("POLYMARKET_KEY_ID"), os.environ.get("POLYMARKET_SECRET_KEY")
    if not key_id or not secret:
        raise RuntimeError(
            "Missing POLYMARKET_KEY_ID / POLYMARKET_SECRET_KEY: set them in the environment or a .env file"
        )
    return key_id, secret


def get_client() -> PolymarketUS:
    key_id, secret = load_credentials()
    return PolymarketUS(key_id=key_id, secret_key=secret)
