"""F5 Distributed Cloud HTTP client.

All communication with the F5 XC API is centralised here.  Route handlers and
service functions must *not* make raw HTTP calls; they must go through this
client so that authentication, timeouts, redaction, and error handling are
applied consistently.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Typed exceptions
# ---------------------------------------------------------------------------


class F5XCClientError(Exception):
    """Base class for all F5 XC client errors."""


class AuthError(F5XCClientError):
    """Raised on 401 / 403 responses - invalid or missing credentials."""


class NotFoundError(F5XCClientError):
    """Raised on 404 responses."""


class RateLimitError(F5XCClientError):
    """Raised on 429 responses."""


class UpstreamError(F5XCClientError):
    """Raised on 5xx responses or unexpected transport failures."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class F5XCClient:
    """Thin async wrapper around the F5 XC REST API.

    Args:
        settings: The application :class:`~app.config.Settings` instance.
            The client reads ``tenant``, ``api_token``, and ``timeout_seconds``
            from this object on every request so that in-memory updates (from
            the Settings page) are picked up without restarting the client.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @property
    def base_url(self) -> str:
        """Return the base hostname for the configured tenant."""
        return f"https://{self._settings.tenant}.console.ves.volterra.io"

    def _auth_headers(self) -> dict[str, str]:
        """Return authentication headers.  The token is *never* logged."""
        return {"Authorization": f"APIToken {self._settings.api_token}"}

    def build_url(
        self,
        service_prefix: str,
        namespace: str,
        kind: str,
        name: str | None = None,
    ) -> str:
        """Build a fully-qualified URL for a namespaced resource.

        Args:
            service_prefix: e.g. ``/api/config`` or ``/api/web``
            namespace: F5 XC namespace name
            kind: resource kind, e.g. ``http_loadbalancers``
            name: optional object name for single-object operations

        Returns:
            A full URL string.

        Example::

            client.build_url("/api/config", "my-ns", "http_loadbalancers")
            # → "https://tenant.console.ves.volterra.io/api/config/namespaces/my-ns/http_loadbalancers"
        """
        prefix = service_prefix.strip("/")
        parts = [self.base_url.rstrip("/"), prefix, "namespaces", namespace, kind]
        if name:
            parts.append(name)
        return "/".join(parts)

    # ------------------------------------------------------------------
    # HTTP verbs
    # ------------------------------------------------------------------

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Perform a GET request and return the parsed JSON body.

        Args:
            path: Absolute path (e.g. ``/api/web/namespaces/system/quota_usages``)
                  or a full URL returned by :meth:`build_url`.
            params: Optional query parameters.

        Returns:
            Parsed JSON (dict or list).

        Raises:
            AuthError: 401 or 403 response.
            NotFoundError: 404 response.
            RateLimitError: 429 response.
            UpstreamError: 5xx response or transport error.
        """
        url = path if path.startswith("https://") else f"{self.base_url}{path}"
        timeout = httpx.Timeout(self._settings.timeout_seconds)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                # Log URL but NEVER log auth headers
                logger.debug("GET %s params=%s", url, params)
                response = await client.get(url, headers=self._auth_headers(), params=params)
        except httpx.TimeoutException as exc:
            raise UpstreamError(f"Request timed out: {url}") from exc
        except httpx.RequestError as exc:
            raise UpstreamError(f"Transport error for {url}: {exc}") from exc

        return self._handle_response(response, url)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _handle_response(self, response: httpx.Response, url: str) -> Any:
        status = response.status_code
        if status == 200:
            return response.json()
        if status in (401, 403):
            raise AuthError(
                f"Authentication / authorisation error ({status}) for {url}. "
                "Check your API token and tenant name."
            )
        if status == 404:
            raise NotFoundError(f"Resource not found ({status}): {url}")
        if status == 429:
            raise RateLimitError(f"Rate limited ({status}): {url}")
        if status >= 500:
            raise UpstreamError(
                f"F5 XC upstream error ({status}): {url} - {response.text[:200]}"
            )
        raise UpstreamError(f"Unexpected status {status} for {url}: {response.text[:200]}")
