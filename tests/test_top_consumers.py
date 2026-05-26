"""Tests for the top consumers service and route."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.clients.f5_xc_client import F5XCClient
from app.config import Settings
from app.services.top_consumers import TOP_N, fetch_top_consumers


def _make_client() -> F5XCClient:
    return F5XCClient(Settings(tenant="acme", api_token="tok"))


def _ns_items(*namespaces: str) -> list[dict]:
    return [{"metadata": {"namespace": ns}} for ns in namespaces]


class TestFetchTopConsumers:
    @pytest.mark.asyncio
    async def test_returns_top_n_sorted_descending(self) -> None:
        client = _make_client()
        base = client.base_url
        namespaces = ["ns-a", "ns-b", "ns-c"]
        ns_payload = {"items": [{"name": ns} for ns in namespaces]}

        with respx.mock:
            respx.get(f"{base}/api/web/namespaces").mock(
                return_value=httpx.Response(200, json=ns_payload)
            )
            # ns-a: 5, ns-b: 1, ns-c: 3
            respx.get(f"{base}/api/config/namespaces/ns-a/http_loadbalancers").mock(
                return_value=httpx.Response(200, json={"items": [{}] * 5})
            )
            respx.get(f"{base}/api/config/namespaces/ns-b/http_loadbalancers").mock(
                return_value=httpx.Response(200, json={"items": [{}] * 1})
            )
            respx.get(f"{base}/api/config/namespaces/ns-c/http_loadbalancers").mock(
                return_value=httpx.Response(200, json={"items": [{}] * 3})
            )
            result = await fetch_top_consumers(client, "http_loadbalancers", "HTTP Load Balancer")

        assert result.kind == "http_loadbalancers"
        assert result.label == "HTTP Load Balancer"
        assert result.total_namespaces_scanned == 3
        # Should be sorted descending
        assert result.top[0].namespace == "ns-a"
        assert result.top[0].count == 5
        assert result.top[1].namespace == "ns-c"
        assert result.top[1].count == 3
        assert result.top[2].namespace == "ns-b"
        assert result.top[2].count == 1

    @pytest.mark.asyncio
    async def test_caps_at_top_n(self) -> None:
        client = _make_client()
        base = client.base_url
        # Create more namespaces than TOP_N
        namespaces = [f"ns-{i}" for i in range(TOP_N + 5)]
        ns_payload = {"items": [{"name": ns} for ns in namespaces]}

        with respx.mock:
            respx.get(f"{base}/api/web/namespaces").mock(
                return_value=httpx.Response(200, json=ns_payload)
            )
            for i, ns in enumerate(namespaces):
                respx.get(f"{base}/api/config/namespaces/{ns}/origin_pools").mock(
                    return_value=httpx.Response(200, json={"items": [{}] * i})
                )
            result = await fetch_top_consumers(client, "origin_pools", "Origin Pool")

        assert len(result.top) == TOP_N

    @pytest.mark.asyncio
    async def test_404_counts_as_zero(self) -> None:
        client = _make_client()
        base = client.base_url
        ns_payload = {"items": [{"name": "ns-x"}]}

        with respx.mock:
            respx.get(f"{base}/api/web/namespaces").mock(
                return_value=httpx.Response(200, json=ns_payload)
            )
            respx.get(f"{base}/api/config/namespaces/ns-x/app_firewalls").mock(
                return_value=httpx.Response(404)
            )
            result = await fetch_top_consumers(client, "app_firewalls", "Application Firewall")

        assert result.top[0].count == 0
