"""Application settings - in-memory singleton pre-seeded from environment variables.

Settings can be updated at runtime via the web UI (Settings page) without restarting
the application. No secrets are written to disk through this module.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the F5 XC dashboard.

    Values are loaded from environment variables on startup and can be
    overridden in-memory via :func:`update_settings`.
    """

    model_config = SettingsConfigDict(
        env_prefix="F5_XC_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    tenant: str = Field(default="", description="F5 XC tenant subdomain")
    api_token: str = Field(default="", description="F5 XC API token")
    default_namespace: str = Field(default="default", description="Default namespace")
    timeout_seconds: int = Field(default=30, description="HTTP timeout in seconds")

    @property
    def is_configured(self) -> bool:
        """Return True when the minimum required settings are present."""
        return bool(self.tenant and self.api_token)


# Module-level singleton - the rest of the application imports this instance.
_settings = Settings()


def get_settings() -> Settings:
    """Return the current in-memory settings instance."""
    return _settings


def update_settings(*, tenant: str, api_token: str) -> None:
    """Update mutable settings in-place (called by the Settings web route).

    Only tenant and api_token are user-editable via the UI; other values
    come from environment variables and are not exposed in the form.
    """
    global _settings
    _settings = _settings.model_copy(
        update={
            "tenant": tenant.strip(),
            "api_token": api_token.strip(),
        }
    )
