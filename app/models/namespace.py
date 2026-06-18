"""Pydantic models for namespace object counts."""

from __future__ import annotations

from pydantic import BaseModel, Field

TRACKED_OBJECT_TYPES: list[str] = [
    "HTTP Load Balancer",
    "Origin Pool",
    "Application Firewall",
    "API Definition",
    "Virtual Host",
    "Service Policy",
    "Route",
    "CSD - Client Side Defense",
]

# Maps display label → API kind (path segment used in /api/config/namespaces/{ns}/{kind})
OBJECT_TYPE_TO_KIND: dict[str, str] = {
    "HTTP Load Balancer": "http_loadbalancers",
    "Origin Pool": "origin_pools",
    "Application Firewall": "app_firewalls",
    "API Definition": "api_definitions",
    "Virtual Host": "virtual_hosts",
    "Service Policy": "service_policys",
    "Route": "routes",
    # CSD lives under a different service prefix (/api/shape/csd) - handled
    # specially by the top-consumers service.
    "CSD - Client Side Defense": "protected_domains",
}



class ObjectCount(BaseModel):
    """Count of a single object type in a namespace."""

    label: str = Field(description="Human-readable object type label")
    kind: str = Field(description="API resource kind")
    count: int = Field(default=0, description="Number of objects in the namespace")


class NamespaceObjectCounts(BaseModel):
    """Aggregated object counts for a single namespace."""

    namespace: str = Field(description="Namespace name")
    objects: list[ObjectCount] = Field(default_factory=list)
