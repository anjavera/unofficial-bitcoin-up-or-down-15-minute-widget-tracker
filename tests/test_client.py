import pytest

from btc15_widget import client


def test_missing_credentials_raise_one_clear_error(monkeypatch):
    monkeypatch.delenv("POLYMARKET_KEY_ID", raising=False)
    monkeypatch.delenv("POLYMARKET_SECRET_KEY", raising=False)
    monkeypatch.setattr(client, "load_dotenv", lambda *a, **k: False)
    with pytest.raises(RuntimeError, match="POLYMARKET_KEY_ID"):
        client.load_credentials()


def test_partial_credentials_still_raise(monkeypatch):
    monkeypatch.setenv("POLYMARKET_KEY_ID", "id")
    monkeypatch.delenv("POLYMARKET_SECRET_KEY", raising=False)
    monkeypatch.setattr(client, "load_dotenv", lambda *a, **k: False)
    with pytest.raises(RuntimeError):
        client.load_credentials()


def test_credentials_returned_from_env(monkeypatch):
    monkeypatch.setenv("POLYMARKET_KEY_ID", "id")
    monkeypatch.setenv("POLYMARKET_SECRET_KEY", "secret")
    monkeypatch.setattr(client, "load_dotenv", lambda *a, **k: False)
    assert client.load_credentials() == ("id", "secret")


def test_public_client_needs_no_credentials(monkeypatch):
    monkeypatch.delenv("POLYMARKET_KEY_ID", raising=False)
    monkeypatch.delenv("POLYMARKET_SECRET_KEY", raising=False)
    monkeypatch.setattr(client, "load_dotenv", lambda *a, **k: False)
    api = client.get_public_client()
    try:
        assert hasattr(api.events, "list") and hasattr(api.markets, "book")
    finally:
        api.close()


def test_has_credentials_needs_both_values(monkeypatch):
    monkeypatch.setattr(client, "load_dotenv", lambda *a, **k: False)
    monkeypatch.delenv("POLYMARKET_KEY_ID", raising=False)
    monkeypatch.delenv("POLYMARKET_SECRET_KEY", raising=False)
    assert client.has_credentials() is False
    monkeypatch.setenv("POLYMARKET_KEY_ID", "id")
    assert client.has_credentials() is False  # a lone key id is not enough
    monkeypatch.setenv("POLYMARKET_SECRET_KEY", "secret")
    assert client.has_credentials() is True
