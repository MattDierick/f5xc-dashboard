"""Unit tests for the F5 XC HTTP client.

Tests cover URL building and auth header generation without making real HTTP
requests.  Error-path tests use respx to mock httpx responses.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.clients.f5_xc_client import (
    AuthError,
    F5XCClient,
    NotFoundError,
    RateLimitError,
    UpstreamError,
)
from app.config import Settings

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_client(tenant: str = "acme", token: str = "test-token") -> F5XCClient:
    settings = Settings(tenant=tenant, api_token=token)
    return F5XCClient(settings)


# ---------------------------------------------------------------------------
# URL builder
# ---------------------------------------------------------------------------


class TestBuildUrl:
    def test_basic_url(self) -> None:
        client = _make_client()
        url = client.build_url("/api/config", "my-ns", "http_loadbalancers")
        assert url == (
            "https://acme.console.ves.volterra.io"
            "/api/config/namespaces/my-ns/http_loadbalancers"
        )

    def test_url_with_name(self) -> None:
        client = _make_client()
        url = client.build_url("/api/config", "my-ns", "http_loadbalancers", name="my-lb")
        assert url.endswith("/http_loadbalancers/my-lb")

    def test_base_url_uses_tenant(self) -> None:
        client = _make_client(tenant="bigcorp")
        assert client.base_url == "https://bigcorp.console.ves.volterra.io"

    def test_trailing_slash_stripped(self) -> None:
        client = _make_client()
        url = client.build_url("/api/config/", "ns", "kind")
        # Should not produce double-slash
        assert "//" not in url.replace("https://", "")


# ---------------------------------------------------------------------------
# Auth headers
# ---------------------------------------------------------------------------


class TestAuthHeaders:
    def test_header_format(self) -> None:
        client = _make_client(token="secret123")
        headers = client._auth_headers()
        assert headers["Authorization"] == "APIToken secret123"

    def test_header_key_exact(self) -> None:
        client = _make_client()
        assert "Authorization" in client._auth_headers()


# ---------------------------------------------------------------------------
# HTTP error handling (mocked)
# ---------------------------------------------------------------------------


class TestGetErrorHandling:
    @pytest.mark.asyncio
    async def test_401_raises_auth_error(self) -> None:
        client = _make_client()
        with respx.mock:
            respx.get(f"{client.base_url}/api/test").mock(
                return_value=httpx.Response(401)
            )
            with pytest.raises(AuthError):
                await client.get("/api/test")

    @pytest.mark.asyncio
    async def test_403_raises_auth_error(self) -> None:
        client = _make_client()
        with respx.mock:
            respx.get(f"{client.base_url}/api/test").mock(
                return_value=httpx.Response(403)
            )
            with pytest.raises(AuthError):
                await client.get("/api/test")

    @pytest.mark.asyncio
    async def test_404_raises_not_found(self) -> None:
        client = _make_client()
        with respx.mock:
            respx.get(f"{client.base_url}/api/test").mock(
                return_value=httpx.Response(404)
            )
            with pytest.raises(NotFoundError):
                await client.get("/api/test")

    @pytest.mark.asyncio
    async def test_429_raises_rate_limit(self) -> None:
        client = _make_client()
        with respx.mock:
            respx.get(f"{client.base_url}/api/test").mock(
                return_value=httpx.Response(429)
            )
            with pytest.raises(RateLimitError):
                await client.get("/api/test")

    @pytest.mark.asyncio
    async def test_500_raises_upstream_error(self) -> None:
        client = _make_client()
        with respx.mock:
            respx.get(f"{client.base_url}/api/test").mock(
                return_value=httpx.Response(500, text="Internal Server Error")
            )
            with pytest.raises(UpstreamError):
                await client.get("/api/test")

    @pytest.mark.asyncio
    async def test_200_returns_json(self) -> None:
        client = _make_client()
        with respx.mock:
            respx.get(f"{client.base_url}/api/test").mock(
                return_value=httpx.Response(200, json={"hello": "world"})
            )
            result = await client.get("/api/test")
        assert result == {"hello": "world"}

    @pytest.mark.asyncio
    async def test_timeout_raises_upstream_error(self) -> None:
        client = _make_client()
        with respx.mock:
            respx.get(f"{client.base_url}/api/test").mock(
                side_effect=httpx.TimeoutException("timed out")
            )
            with pytest.raises(UpstreamError, match="timed out"):
                await client.get("/api/test")
