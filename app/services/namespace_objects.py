"""Namespace object counts service.

Fetches:
  - List of namespaces:  GET /api/web/namespaces
  - Per-namespace object counts for the four tracked resource types:
      HTTP Load Balancers  → GET /api/config/namespaces/{ns}/http_loadbalancers
      Origin Pools         → GET /api/config/namespaces/{ns}/origin_pools
      Application Firewalls→ GET /api/config/namespaces/{ns}/app_firewalls
      API Definitions      → GET /api/config/namespaces/{ns}/api_definitions

Authentication:
    API Token (``Authorization: APIToken <token>``)

All four object-count requests are fired concurrently to minimise latency.
"""

from __future__ import annotations

import asyncio
import logging

from app.clients.f5_xc_client import F5XCClient, NotFoundError
from app.models.namespace import (
    OBJECT_TYPE_TO_KIND,
    TRACKED_OBJECT_TYPES,
    NamespaceObjectCounts,
    ObjectCount,
)

logger = logging.getLogger(__name__)

_NAMESPACES_PATH = "/api/web/namespaces"


async def fetch_namespaces(client: F5XCClient) -> list[str]:
    """Return a sorted list of namespace names visible to the configured credentials.

    Args:
        client: An authenticated :class:`~app.clients.f5_xc_client.F5XCClient`.

    Returns:
        Sorted list of namespace name strings.

    Raises:
        :class:`~app.clients.f5_xc_client.F5XCClientError` subclasses on failure.
    """
    data = await client.get(_NAMESPACES_PATH)
    return _parse_namespaces(data)


def _parse_namespaces(data: object) -> list[str]:
    if not isinstance(data, dict):
        return []
    items = data.get("items") or []
    names: list[str] = []
    for item in items:
        if isinstance(item, dict):
            name = item.get("name") or item.get("namespace") or ""
            if name:
                names.append(name)
    return sorted(set(names))


async def fetch_object_counts(
    client: F5XCClient,
    namespace: str,
) -> NamespaceObjectCounts:
    """Fetch counts for all tracked object types in *namespace* concurrently.

    Args:
        client: An authenticated :class:`~app.clients.f5_xc_client.F5XCClient`.
        namespace: The namespace to query.

    Returns:
        A :class:`~app.models.namespace.NamespaceObjectCounts` instance with
        one :class:`~app.models.namespace.ObjectCount` per tracked type.
    """
    tasks = {
        label: _count_objects(client, namespace, kind)
        for label, kind in OBJECT_TYPE_TO_KIND.items()
    }

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    object_counts: list[ObjectCount] = []
    for label, result in zip(tasks.keys(), results, strict=False):
        kind = OBJECT_TYPE_TO_KIND[label]
        if isinstance(result, BaseException):
            logger.warning("Failed to fetch %s in namespace %s: %s", kind, namespace, result)
            count = 0
        else:
            count = result
        object_counts.append(ObjectCount(label=label, kind=kind, count=count))

    # Preserve the canonical display order
    ordered = sorted(object_counts, key=lambda o: TRACKED_OBJECT_TYPES.index(o.label))
    return NamespaceObjectCounts(namespace=namespace, objects=ordered)


async def _count_objects(client: F5XCClient, namespace: str, kind: str) -> int:
    """Return the number of objects of *kind* owned by *namespace*.

    Objects explicitly tagged as belonging to the ``shared`` namespace are
    excluded.  Items with no namespace tag are assumed to belong to the
    requested namespace and are always counted.

    Returns 0 on 404 (namespace exists but resource type is empty / not supported).
    """
    url = client.build_url("/api/config", namespace, kind)
    try:
        data = await client.get(url)
    except NotFoundError:
        return 0
    count = _extract_count(data)
    logger.debug("Counted %d objects for %s/%s", count, namespace, kind)
    return count


def _extract_count(data: object) -> int:
    if not isinstance(data, dict):
        return 0
    if "items" in data:
        items = data["items"]
        if not isinstance(items, list):
            return 0
        # Exclude items explicitly tagged as belonging to the shared namespace.
        # Check every location F5 XC may put the namespace field:
        #   item.namespace
        #   item.metadata.namespace
        #   item.system_metadata.namespace
        excluded = 0
        for item in items:
            if isinstance(item, dict) and _item_namespace(item) == "shared":
                excluded += 1
                logger.debug("Excluding shared-namespace item: %s", item.get("name", "?"))
        return len(items) - excluded
    total = data.get("total_count") or data.get("totalCount")
    if total is not None:
        return int(total)
    return 0


def _item_namespace(item: dict) -> str:
    """Extract the namespace from an item, checking all known field locations."""
    # Top-level namespace field (present in some list response items)
    ns = item.get("namespace")
    if ns:
        return str(ns)
    # metadata.namespace
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        ns = metadata.get("namespace")
        if ns:
            return str(ns)
    # system_metadata.namespace
    sys_meta = item.get("system_metadata")
    if isinstance(sys_meta, dict):
        ns = sys_meta.get("namespace")
        if ns:
            return str(ns)
    return ""
