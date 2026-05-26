"""Pydantic models for the Top Consumers page."""

from __future__ import annotations

from pydantic import BaseModel, Field


class NamespaceCount(BaseModel):
    """Count of a single object kind in one namespace."""

    namespace: str = Field(description="Namespace name")
    count: int = Field(description="Number of objects in this namespace")


class TopConsumersResult(BaseModel):
    """Top namespaces ranked by object count for a given kind."""

    kind: str = Field(description="API resource kind queried")
    label: str = Field(description="Human-readable label for the kind")
    top: list[NamespaceCount] = Field(
        default_factory=list,
        description="Top namespaces sorted by count descending (max 10)",
    )
    total_namespaces_scanned: int = Field(
        default=0, description="Total number of namespaces scanned"
    )
