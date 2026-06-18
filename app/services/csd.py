"""Client-Side Defense (CSD) helpers.

CSD *protected domains* live under a dedicated service prefix
(``/api/shape/csd``) rather than the usual ``/api/config`` prefix, so they
need their own per-namespace counter.  The Top Consumers and Namespaces
pages treat "CSD - Client Side Defense" as a regular object type and route
it through :func:`_count_protected_domains`.

API endpoint used:
    GET /api/shape/csd/namespaces/{ns}/protected_domains      - list protected domains

Docs:
    https://docs.cloud.f5.com/docs-v2/api/shape-client-side-defense-protected-domain

Authentication:
    API Token (``Authorization: APIToken <token>``)
"""

from __future__ import annotations

import logging

from app.clients.f5_xc_client import F5XCClient, NotFoundError
from app.services.namespace_objects import _extract_count

logger = logging.getLogger(__name__)

CSD_SERVICE_PREFIX = "/api/shape/csd"
CSD_KIND = "protected_domains"
CSD_LABEL = "CSD - Client Side Defense"


async def _count_protected_domains(client: F5XCClient, namespace: str) -> int:
    """Return the number of CSD protected domains owned by *namespace*.

    Returns 0 on 404 (namespace exists but CSD is not enabled / no domains).
    """
    url = client.build_url(CSD_SERVICE_PREFIX, namespace, CSD_KIND)
    try:
        data = await client.get(url)
    except NotFoundError:
        return 0
    count = _extract_count(data)
    logger.debug("Counted %d CSD protected domains for %s", count, namespace)
    return count
