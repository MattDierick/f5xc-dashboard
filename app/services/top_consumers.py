"""Top consumers service.

For a given object kind, queries every namespace concurrently and returns
the top 10 namespaces ranked by object count (highest first).

API endpoints used:
    GET /api/web/namespaces                              - list all namespaces
    GET /api/config/namespaces/{ns}/{kind}               - count objects per ns

Authentication:
    API Token (``Authorization: APIToken <token>``)
"""

from __future__ import annotations

import asyncio
import logging

from app.clients.f5_xc_client import F5XCClient
from app.models.top_consumers import NamespaceCount, TopConsumersResult
from app.services.csd import CSD_KIND, _count_protected_domains
from app.services.namespace_objects import (
    _count_objects,
    fetch_namespaces,
)

logger = logging.getLogger(__name__)

TOP_N = 10



async def fetch_top_consumers(
    client: F5XCClient,
    kind: str,
    label: str,
) -> TopConsumersResult:
    """Return the top namespaces ranked by object count for *kind*.

    Args:
        client: Authenticated F5 XC client.
        kind: API resource kind, e.g. ``http_loadbalancers``.
        label: Human-readable label shown in the UI.

    Returns:
        A :class:`~app.models.top_consumers.TopConsumersResult` with the top
        10 namespaces sorted descending by count.
    """
    namespaces = await fetch_namespaces(client)

    # CSD protected domains live under a different service prefix
    # (/api/shape/csd) so they need a dedicated counter.
    if kind == CSD_KIND:
        counter = _count_protected_domains
    else:
        def counter(c: F5XCClient, ns: str) -> object:  # type: ignore[misc]
            return _count_objects(c, ns, kind)

    # Query all namespaces concurrently
    tasks = [counter(client, ns) for ns in namespaces]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    counts: list[NamespaceCount] = []
    for ns, result in zip(namespaces, results, strict=False):
        if isinstance(result, BaseException):
            logger.warning("Failed to count %s in namespace %s: %s", kind, ns, result)
            count = 0
        else:
            count = result
        counts.append(NamespaceCount(namespace=ns, count=count))

    # Sort descending, take top N
    counts.sort(key=lambda c: c.count, reverse=True)
    top = counts[:TOP_N]

    return TopConsumersResult(
        kind=kind,
        label=label,
        top=top,
        total_namespaces_scanned=len(namespaces),
    )
