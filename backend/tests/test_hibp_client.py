"""HIBP client success/failure distinction tests."""

import pytest

from app.services import hibp_client


class _Resp:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_fetch_breaches_404_is_authoritative_empty(monkeypatch):
    monkeypatch.setattr(hibp_client.settings, "hibp_api_key", "key")
    monkeypatch.setattr(hibp_client, "get_cached", lambda key: None)
    monkeypatch.setattr(hibp_client, "set_cached", lambda key, value: None)
    monkeypatch.setattr(hibp_client, "throttle", lambda *_a, **_k: _async_noop())

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            return _Resp(404, {"detail": "not found"})

    monkeypatch.setattr(hibp_client.httpx, "AsyncClient", lambda **kwargs: _Client())
    result = await hibp_client.fetch_breaches("jane@example.com")
    assert result.ok is True
    assert result.items == []


@pytest.mark.asyncio
async def test_fetch_breaches_http_error_is_not_ok(monkeypatch):
    monkeypatch.setattr(hibp_client.settings, "hibp_api_key", "key")
    monkeypatch.setattr(hibp_client, "get_cached", lambda key: None)
    monkeypatch.setattr(hibp_client, "throttle", lambda *_a, **_k: _async_noop())

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            return _Resp(429, {"detail": "rate limited"})

    monkeypatch.setattr(hibp_client.httpx, "AsyncClient", lambda **kwargs: _Client())
    result = await hibp_client.fetch_breaches("jane@example.com")
    assert result.ok is False
    assert result.items == []
    assert result.error == "http_429"


async def _async_noop(*_a, **_k):
    return None
