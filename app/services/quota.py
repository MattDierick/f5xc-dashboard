"""Quota service - fetches and parses F5 XC quota usage data.

API endpoint used:
    GET /api/web/namespaces/{namespace}/quota/usage

Authentication:
    API Token (``Authorization: APIToken <token>``)

Response shape (``quotaGetResponseType`` from the OpenAPI spec):
    {
        "objects": {
            "http_loadbalancer": {
                "display_name": "HTTP Load Balancer",
                "description": "...",
                "limit": {"maximum": 100},
                "usage": {"current": 3}
            },
            ...
        }
    }

The ``objects`` field is a map keyed by object kind.  Each value contains:
  - ``display_name``  - human-readable label
  - ``limit.maximum`` - integer quota limit
  - ``usage.current`` - integer current usage
"""

from __future__ import annotations

import logging

from app.clients.f5_xc_client import F5XCClient
from app.models.quota import QuotaItem

logger = logging.getLogger(__name__)

_QUOTA_PATH_TMPL = "/api/web/namespaces/{namespace}/quota/usage"


async def fetch_quota_usages(client: F5XCClient, namespace: str = "system") -> list[QuotaItem]:
    """Retrieve all quota usage entries from F5 XC and return typed models.

    Args:
        client: An authenticated :class:`~app.clients.f5_xc_client.F5XCClient`.
        namespace: The namespace to query (defaults to ``system`` for
            tenant-wide quotas).

    Returns:
        A sorted list of :class:`~app.models.quota.QuotaItem` objects.

    Raises:
        :class:`~app.clients.f5_xc_client.F5XCClientError` subclasses on API
        failures (caller decides how to surface these to the user).
    """
    path = _QUOTA_PATH_TMPL.format(namespace=namespace)
    data = await client.get(path)
    return _parse_quota_response(data)


def _parse_quota_response(data: object) -> list[QuotaItem]:
    """Parse the ``GET .../quota/usage`` response into QuotaItem models.

    The ``objects`` field is a dict mapping object kind -> QuotaUsage entry.
    Each entry has ``limit.maximum`` (int) and ``usage.current`` (int).
    """
    if not isinstance(data, dict):
        logger.warning("Unexpected quota response type: %s", type(data))
        return []

    objects: dict = data.get("objects") or {}
    if not objects:
        logger.warning("No 'objects' key in quota/usage response: %s", list(data.keys()))
        return []

    result: list[QuotaItem] = []
    for kind, entry in objects.items():
        if not isinstance(entry, dict):
            continue
        display_name: str = entry.get("display_name") or kind
        limit_obj = entry.get("limit") or {}
        usage_obj = entry.get("usage") or {}
        limit = int(limit_obj.get("maximum") or 0) if isinstance(limit_obj, dict) else 0
        usage = int(usage_obj.get("current") or 0) if isinstance(usage_obj, dict) else 0
        result.append(
            QuotaItem(kind=kind, display_name=display_name, limit=limit, current_usage=usage)
        )

    return sorted(result, key=lambda q: q.display_name.lower())
