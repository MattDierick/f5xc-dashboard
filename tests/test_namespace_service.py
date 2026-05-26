"""Unit tests for the namespace objects service."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.clients.f5_xc_client import F5XCClient
from app.config import Settings
from app.services.namespace_objects import (
    _extract_count,
    _item_namespace,
    _parse_namespaces,
    fetch_namespaces,
    fetch_object_counts,
)


def _make_client() -> F5XCClient:
    return F5XCClient(Settings(tenant="acme", api_token="tok"))


# ---------------------------------------------------------------------------
# Parser helpers
# ---------------------------------------------------------------------------


class TestParseNamespaces:
    def test_standard_response(self) -> None:
        data = {"items": [{"name": "default"}, {"name": "production"}]}
        assert _parse_namespaces(data) == ["default", "production"]

    def test_deduplication(self) -> None:
        data = {"items": [{"name": "ns1"}, {"name": "ns1"}]}
        assert _parse_namespaces(data) == ["ns1"]

    def test_sorted(self) -> None:
        data = {"items": [{"name": "z-ns"}, {"name": "a-ns"}]}
        assert _parse_namespaces(data) == ["a-ns", "z-ns"]

    def test_empty_items(self) -> None:
        assert _parse_namespaces({"items": []}) == []

    def test_non_dict(self) -> None:
        assert _parse_namespaces([]) == []


class TestExtractCount:
    def test_items_list(self) -> None:
        # Items with no metadata are counted normally
        assert _extract_count({"items": [{}, {}, {}]}) == 3

    def test_total_count_field(self) -> None:
        assert _extract_count({"total_count": 42}) == 42

    def test_empty_items(self) -> None:
        assert _extract_count({"items": []}) == 0

    def test_non_dict(self) -> None:
        assert _extract_count("nope") == 0

    def test_filters_out_shared_via_metadata(self) -> None:
        items = [
            {"metadata": {"namespace": "my-ns"}},
            {"metadata": {"namespace": "shared"}},   # must be excluded
            {"metadata": {"namespace": "my-ns"}},
        ]
        assert _extract_count({"items": items}) == 2

    def test_filters_out_shared_via_top_level(self) -> None:
        items = [
            {"namespace": "my-ns"},
            {"namespace": "shared"},   # must be excluded
            {"namespace": "my-ns"},
        ]
        assert _extract_count({"items": items}) == 2

    def test_filters_out_shared_via_system_metadata(self) -> None:
        items = [
            {"system_metadata": {"namespace": "my-ns"}},
            {"system_metadata": {"namespace": "shared"}},   # must be excluded
        ]
        assert _extract_count({"items": items}) == 1

    def test_items_without_metadata_are_counted(self) -> None:
        # Items with no namespace tag are always counted
        items = [{}, {"metadata": {"namespace": "shared"}}, {}]
        assert _extract_count({"items": items}) == 2

    def test_shared_only_returns_zero(self) -> None:
        items = [
            {"metadata": {"namespace": "shared"}},
            {"namespace": "shared"},
        ]
        assert _extract_count({"items": items}) == 0


class TestItemNamespace:
    def test_reads_metadata_namespace(self) -> None:
        assert _item_namespace({"metadata": {"namespace": "my-ns"}}) == "my-ns"

    def test_falls_back_to_system_metadata(self) -> None:
        assert _item_namespace({"system_metadata": {"namespace": "sys-ns"}}) == "sys-ns"

    def test_missing_metadata_returns_empty(self) -> None:
        assert _item_namespace({}) == ""

    def test_missing_namespace_key_returns_empty(self) -> None:
        assert _item_namespace({"metadata": {}}) == ""


# ---------------------------------------------------------------------------
# Integration with mocked HTTP
# ---------------------------------------------------------------------------


class TestFetchNamespaces:
    @pytest.mark.asyncio
    async def test_successful_fetch(self) -> None:
        client = _make_client()
        payload = {"items": [{"name": "default"}, {"name": "staging"}]}
        with respx.mock:
            respx.get(f"{client.base_url}/api/web/namespaces").mock(
                return_value=httpx.Response(200, json=payload)
            )
            ns_list = await fetch_namespaces(client)
        assert "default" in ns_list
        assert "staging" in ns_list


class TestFetchObjectCounts:
    @pytest.mark.asyncio
    async def test_all_objects_counted(self) -> None:
        client = _make_client()
        base = f"{client.base_url}/api/config/namespaces/my-ns"
        with respx.mock:
            respx.get(f"{base}/http_loadbalancers").mock(
                return_value=httpx.Response(200, json={"items": [{}, {}]})
            )
            respx.get(f"{base}/origin_pools").mock(
                return_value=httpx.Response(200, json={"items": [{}]})
            )
            respx.get(f"{base}/app_firewalls").mock(
                return_value=httpx.Response(200, json={"items": []})
            )
            respx.get(f"{base}/api_definitions").mock(
                return_value=httpx.Response(200, json={"items": [{}, {}, {}]})
            )
            counts = await fetch_object_counts(client, "my-ns")

        assert counts.namespace == "my-ns"
        count_map = {o.label: o.count for o in counts.objects}
        assert count_map["HTTP Load Balancer"] == 2
        assert count_map["Origin Pool"] == 1
        assert count_map["Application Firewall"] == 0
        assert count_map["API Definition"] == 3

    @pytest.mark.asyncio
    async def test_shared_objects_excluded(self) -> None:
        client = _make_client()
        base = f"{client.base_url}/api/config/namespaces/my-ns"
        # Mix of owned items and shared items — shared ones must not be counted
        items = [
            {"metadata": {"namespace": "my-ns"}},
            {"metadata": {"namespace": "shared"}},
            {"metadata": {"namespace": "my-ns"}},
        ]
        with respx.mock:
            for kind in (
                "http_loadbalancers", "origin_pools", "app_firewalls",
                "api_definitions", "virtual_hosts", "service_policys", "routes",
            ):
                respx.get(f"{base}/{kind}").mock(
                    return_value=httpx.Response(200, json={"items": items})
                )
            counts = await fetch_object_counts(client, "my-ns")

        for obj in counts.objects:
            assert obj.count == 2, f"{obj.label} should be 2, got {obj.count}"

    @pytest.mark.asyncio
    async def test_404_treated_as_zero(self) -> None:
        client = _make_client()
        base = f"{client.base_url}/api/config/namespaces/empty-ns"
        with respx.mock:
            for kind in ("http_loadbalancers", "origin_pools", "app_firewalls", "api_definitions"):
                respx.get(f"{base}/{kind}").mock(return_value=httpx.Response(404))
            counts = await fetch_object_counts(client, "empty-ns")

        for obj in counts.objects:
            assert obj.count == 0
