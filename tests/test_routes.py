"""Route smoke tests using FastAPI TestClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.namespace import NamespaceObjectCounts, ObjectCount
from app.models.quota import QuotaItem

# Use synchronous TestClient (wraps async handlers automatically)
client = TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Settings routes
# ---------------------------------------------------------------------------


class TestSettingsRoutes:
    def test_settings_page_loads(self) -> None:
        resp = client.get("/settings")
        assert resp.status_code == 200
        assert "Settings" in resp.text
        assert "Tenant Name" in resp.text

    def test_settings_save_redirects(self) -> None:
        resp = client.post(
            "/settings",
            data={"tenant": "test-tenant", "api_token": "test-token"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/settings?saved=1"

    def test_settings_save_shows_confirmation(self) -> None:
        resp = client.post(
            "/settings",
            data={"tenant": "test-tenant", "api_token": "test-token"},
            follow_redirects=True,
        )
        assert resp.status_code == 200
        assert "saved successfully" in resp.text.lower()


# ---------------------------------------------------------------------------
# Quota dashboard routes
# ---------------------------------------------------------------------------


class TestQuotaRoutes:
    def test_quota_page_unconfigured(self) -> None:
        """When no credentials are set the page should show a config prompt."""
        with patch("app.web.routes.get_settings") as mock_settings:
            mock_settings.return_value.is_configured = False
            resp = client.get("/")
        assert resp.status_code == 200
        # Should contain a link to settings
        assert "/settings" in resp.text

    def test_quota_page_with_data(self) -> None:
        items = [
            QuotaItem(kind="http_loadbalancer", display_name="HTTP Load Balancer", limit=100, current_usage=10),  # noqa: E501
            QuotaItem(kind="origin_pool", display_name="Origin Pool", limit=200, current_usage=5),
        ]
        with (
            patch("app.web.routes.get_settings") as mock_settings,
            patch("app.web.routes.fetch_quota_usages", new_callable=AsyncMock) as mock_fetch,
        ):
            mock_settings.return_value.is_configured = True
            mock_settings.return_value.tenant = "demo"
            mock_settings.return_value.api_token = "tok"
            mock_settings.return_value.timeout_seconds = 30
            mock_fetch.return_value = items
            resp = client.get("/")

        assert resp.status_code == 200
        assert "http_loadbalancer" in resp.text
        assert "origin_pool" in resp.text


# ---------------------------------------------------------------------------
# Namespace routes
# ---------------------------------------------------------------------------


class TestNamespaceRoutes:
    def test_namespace_page_unconfigured(self) -> None:
        with patch("app.web.routes.get_settings") as mock_settings:
            mock_settings.return_value.is_configured = False
            resp = client.get("/namespaces")
        assert resp.status_code == 200
        assert "/settings" in resp.text

    def test_namespace_page_with_namespaces(self) -> None:
        with (
            patch("app.web.routes.get_settings") as mock_settings,
            patch("app.web.routes.fetch_namespaces", new_callable=AsyncMock) as mock_ns,
        ):
            mock_settings.return_value.is_configured = True
            mock_settings.return_value.tenant = "demo"
            mock_settings.return_value.api_token = "tok"
            mock_settings.return_value.timeout_seconds = 30
            mock_ns.return_value = ["default", "production"]
            resp = client.get("/namespaces")

        assert resp.status_code == 200
        assert "default" in resp.text
        assert "production" in resp.text

    def test_namespace_post_returns_counts(self) -> None:
        counts = NamespaceObjectCounts(
            namespace="default",
            objects=[
                ObjectCount(label="HTTP Load Balancer", kind="http_loadbalancers", count=3),
                ObjectCount(label="Origin Pool", kind="origin_pools", count=1),
                ObjectCount(label="Application Firewall", kind="app_firewalls", count=0),
                ObjectCount(label="API Definition", kind="api_definitions", count=2),
            ],
        )
        with (
            patch("app.web.routes.get_settings") as mock_settings,
            patch("app.web.routes.fetch_namespaces", new_callable=AsyncMock) as mock_ns,
            patch(
                "app.web.routes.fetch_object_counts", new_callable=AsyncMock
            ) as mock_counts,
        ):
            mock_settings.return_value.is_configured = True
            mock_settings.return_value.tenant = "demo"
            mock_settings.return_value.api_token = "tok"
            mock_settings.return_value.timeout_seconds = 30
            mock_ns.return_value = ["default"]
            mock_counts.return_value = counts
            resp = client.post("/namespaces", data={"namespace": "default"})

        assert resp.status_code == 200
        assert "HTTP Load Balancer" in resp.text
        assert "3" in resp.text
