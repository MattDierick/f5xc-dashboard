"""Unit tests for the quota service layer."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.clients.f5_xc_client import F5XCClient
from app.config import Settings
from app.services.quota import _parse_quota_response, fetch_quota_usages


def _make_client() -> F5XCClient:
    return F5XCClient(Settings(tenant="acme", api_token="tok"))


# ---------------------------------------------------------------------------
# Parser unit tests (pure function, no HTTP)
# Response shape: GET /api/web/namespaces/{ns}/quota/usage
# {
#   "objects": {
#     "http_loadbalancer": {
#       "display_name": "HTTP Load Balancer",
#       "limit": {"maximum": 100},
#       "usage": {"current": 3}
#     }
#   }
# }
# ---------------------------------------------------------------------------


class TestParseQuotaResponse:
    def test_standard_fields(self) -> None:
        data = {
            "objects": {
                "http_loadbalancer": {
                    "display_name": "HTTP Load Balancer",
                    "limit": {"maximum": 50},
                    "usage": {"current": 10},
                },
                "origin_pool": {
                    "display_name": "Origin Pool",
                    "limit": {"maximum": 200},
                    "usage": {"current": 5},
                },
            }
        }
        items = _parse_quota_response(data)
        assert len(items) == 2
        lb = next(i for i in items if i.kind == "http_loadbalancer")
        assert lb.display_name == "HTTP Load Balancer"
        assert lb.limit == 50
        assert lb.current_usage == 10
        assert lb.available == 40
        assert lb.usage_pct == 20.0

    def test_empty_objects(self) -> None:
        assert _parse_quota_response({"objects": {}}) == []

    def test_missing_objects_key(self) -> None:
        assert _parse_quota_response({"other": "data"}) == []

    def test_non_dict_input(self) -> None:
        assert _parse_quota_response([]) == []

    def test_zero_limit_usage_pct(self) -> None:
        items = _parse_quota_response(
            {"objects": {"foo": {"limit": {"maximum": 0}, "usage": {"current": 0}}}}
        )
        assert items[0].usage_pct == 0.0

    def test_available_floored_at_zero(self) -> None:
        items = _parse_quota_response(
            {"objects": {"bar": {"limit": {"maximum": 5}, "usage": {"current": 10}}}}
        )
        assert items[0].available == 0

    def test_results_sorted_by_display_name(self) -> None:
        data = {
            "objects": {
                "z_type": {"display_name": "Z Type", "limit": {"maximum": 1}, "usage": {"current": 0}},  # noqa: E501
                "a_type": {"display_name": "A Type", "limit": {"maximum": 1}, "usage": {"current": 0}},  # noqa: E501
            }
        }
        items = _parse_quota_response(data)
        assert items[0].display_name == "A Type"
        assert items[1].display_name == "Z Type"

    def test_kind_used_as_display_name_fallback(self) -> None:
        data = {"objects": {"my_kind": {"limit": {"maximum": 10}, "usage": {"current": 1}}}}
        items = _parse_quota_response(data)
        assert items[0].display_name == "my_kind"


# ---------------------------------------------------------------------------
# Integration with mocked HTTP
# ---------------------------------------------------------------------------


class TestFetchQuotaUsages:
    @pytest.mark.asyncio
    async def test_successful_fetch(self) -> None:
        client = _make_client()
        payload = {
            "objects": {
                "http_loadbalancer": {
                    "display_name": "HTTP Load Balancer",
                    "limit": {"maximum": 100},
                    "usage": {"current": 3},
                },
            }
        }
        with respx.mock:
            respx.get(
                f"{client.base_url}/api/web/namespaces/system/quota/usage"
            ).mock(return_value=httpx.Response(200, json=payload))
            items = await fetch_quota_usages(client)

        assert len(items) == 1
        assert items[0].kind == "http_loadbalancer"
        assert items[0].display_name == "HTTP Load Balancer"
        assert items[0].current_usage == 3

    @pytest.mark.asyncio
    async def test_custom_namespace(self) -> None:
        client = _make_client()
        payload = {"objects": {}}
        with respx.mock:
            respx.get(
                f"{client.base_url}/api/web/namespaces/my-ns/quota/usage"
            ).mock(return_value=httpx.Response(200, json=payload))
            items = await fetch_quota_usages(client, namespace="my-ns")
        assert items == []
