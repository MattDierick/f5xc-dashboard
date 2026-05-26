"""Pydantic models for F5 XC quota data."""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field


class QuotaItem(BaseModel):
    """A single quota entry from GET /api/web/namespaces/{ns}/quota/usage.

    The ``objects`` map in the response is keyed by object kind (e.g.
    ``http_loadbalancer``).  Each value provides a ``display_name``, a
    ``limit.maximum`` integer, and a ``usage.current`` integer.
    """

    kind: str = Field(description="Object kind key (e.g. 'http_loadbalancer')")
    display_name: str = Field(default="", description="Human-readable object type label")
    limit: int = Field(description="Maximum number of objects allowed")
    current_usage: int = Field(default=0, description="Number of objects currently in use")

    @computed_field  # type: ignore[misc]
    @property
    def available(self) -> int:
        """Remaining quota (limit minus current usage, floored at 0).

        Returns -1 when the limit is -1 (unlimited).
        """
        if self.limit == -1:
            return -1
        return max(0, self.limit - self.current_usage)

    @computed_field  # type: ignore[misc]
    @property
    def usage_pct(self) -> float:
        """Usage percentage (0-100), rounded to one decimal place.

        Returns 0.0 when the limit is 0 or -1 (unlimited / not set).
        """
        if self.limit <= 0:
            return 0.0
        return round(self.current_usage / self.limit * 100, 1)
