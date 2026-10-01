"""Polymarket US credentials and client construction (read-only use)."""

import os

from dotenv import find_dotenv, load_dotenv
from polymarket_us import PolymarketUS

from btc15_widget.paths import env_file


def _read_env() -> tuple[str | None, str | None]:
    load_dotenv(find_dotenv(usecwd=True))
    load_dotenv(env_file())
    return os.environ.get("POLYMARKET_KEY_ID"), os.environ.get("POLYMARKET_SECRET_KEY")


def has_credentials() -> bool:
    """True when both API key values are set (environment or .env). Never returns or prints them."""
    key_id, secret = _read_env()
    return bool(key_id and secret)


def load_credentials() -> tuple[str, str]:
    key_id, secret = _read_env()
    if not key_id or not secret:
        raise RuntimeError(
            "Missing POLYMARKET_KEY_ID / POLYMARKET_SECRET_KEY (needed only for account commands and the "
            "recorder; the widget and `pm btc15` need no keys): set them in the environment or a .env file"
        )
    return key_id, secret


def get_public_client() -> PolymarketUS:
    """Client for public market data (history, prices, search): no credentials needed."""
    return PolymarketUS()


def get_client() -> PolymarketUS:
    """Authenticated client, only needed for account commands and the recorder."""
    key_id, secret = load_credentials()
    return PolymarketUS(key_id=key_id, secret_key=secret)
