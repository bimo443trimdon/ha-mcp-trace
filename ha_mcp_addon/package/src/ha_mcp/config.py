"""Configuration module for the Home Assistant MCP Server."""

import logging
from typing import Literal
from urllib.parse import urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables with HA_MCP_ prefix."""

    ha_url: str = "http://homeassistant.local:8123"
    ha_token: str = ""
    transport: str = "stdio"
    host: str = "127.0.0.1"
    port: int = 8099
    api_key: str = ""
    allow_unauthenticated: bool = False
    confirm_mode: Literal["client", "elicit"] = "client"
    read_only: bool = False
    enable_device_control: bool = False
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_prefix="HA_MCP_")

    @field_validator("ha_token")
    @classmethod
    def warn_if_empty_token(cls, v: str) -> str:
        if not v:
            logger.warning(
                "ha_token is empty. Set HA_MCP_HA_TOKEN to a long-lived access token."
            )
        return v

    @field_validator("transport")
    @classmethod
    def validate_transport(cls, v: str) -> str:
        allowed = {"stdio", "http", "sse"}
        if v not in allowed:
            raise ValueError(
                f"Invalid transport '{v}'. Must be one of: {', '.join(sorted(allowed))}"
            )
        return v

    @property
    def ha_base_url(self) -> str:
        """Return ha_url with any trailing slash removed."""
        return self.ha_url.rstrip("/")

    @property
    def ha_websocket_url(self) -> str:
        """Convert ha_url to a WebSocket URL and append /api/websocket."""
        parsed = urlparse(self.ha_base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        return f"{scheme}://{parsed.netloc}{parsed.path}/api/websocket"


settings = Settings()
