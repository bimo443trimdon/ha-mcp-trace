"""REST client for the Home Assistant HTTP API."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
from urllib.parse import quote

from ha_mcp.ha_client.models import (
    HAAuthError,
    HAConnectionError,
    HANotFoundError,
    HAValidationError,
)

logger = logging.getLogger(__name__)


def _seg(value: str) -> str:
    """Quote one URL path segment; refuse values that would escape it."""
    value = str(value)
    if not value or value in (".", "..") or "/" in value or "\\" in value:
        raise HAValidationError(f"Invalid identifier: {value!r}")
    return quote(value, safe=":+")


class HARestClient:
    """Async REST client wrapping the Home Assistant HTTP API.

    Provides methods for state queries, history/logbook retrieval, template
    rendering, automation/script/scene CRUD, and service calls.
    """

    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._session: aiohttp.ClientSession | None = None
        self._semaphore = asyncio.Semaphore(5)

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Create the HTTP session with auth headers."""
        self._session = aiohttp.ClientSession(
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            }
        )

    async def disconnect(self) -> None:
        """Close the HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Make an authenticated request with error handling.

        Acquires the concurrency semaphore, issues the request via *aiohttp*,
        and translates HTTP error codes into the appropriate HA exceptions.

        Returns parsed JSON for JSON responses and plain text otherwise.
        """
        if self._session is None:
            raise HAConnectionError("REST client is not connected – call connect() first")

        url = f"{self.base_url}{path}"
        logger.debug("%s %s", method.upper(), url)

        async with self._semaphore:
            try:
                async with self._session.request(method, url, **kwargs) as resp:
                    if resp.status == 401:
                        text = await resp.text()
                        raise HAAuthError(f"Authentication failed (401): {text}")
                    if resp.status == 404:
                        text = await resp.text()
                        raise HANotFoundError(f"Resource not found (404): {path} – {text}")
                    if resp.status == 400:
                        text = await resp.text()
                        raise HAValidationError(f"Validation error (400): {text}")

                    resp.raise_for_status()

                    content_type = resp.content_type or ""
                    if "json" in content_type:
                        return await resp.json()
                    return await resp.text()

            except aiohttp.ClientConnectionError as exc:
                raise HAConnectionError(f"Connection error: {exc}") from exc
            except aiohttp.ClientResponseError as exc:
                # Catch any remaining non-2xx that raise_for_status() triggers
                raise HAConnectionError(
                    f"HTTP {exc.status} from {method.upper()} {path}: {exc.message}"
                ) from exc

    # ------------------------------------------------------------------
    # State endpoints
    # ------------------------------------------------------------------

    async def get_states(self) -> list[dict]:
        """GET /api/states – return all entity states."""
        return await self._request("GET", "/api/states")

    async def get_state(self, entity_id: str) -> dict:
        """GET /api/states/{entity_id} – return a single entity state."""
        return await self._request("GET", f"/api/states/{_seg(entity_id)}")

    # ------------------------------------------------------------------
    # History / logging
    # ------------------------------------------------------------------

    async def get_history(
        self,
        entity_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list:
        """GET /api/history/period/{timestamp} with optional query params."""
        path = "/api/history/period"
        if start_time:
            path = f"{path}/{_seg(start_time)}"

        params: dict[str, str] = {}
        if entity_id:
            params["filter_entity_id"] = entity_id
        if end_time:
            params["end_time"] = end_time

        return await self._request("GET", path, params=params)

    async def get_logbook(
        self,
        entity_id: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list:
        """GET /api/logbook/{timestamp} with optional query params."""
        path = "/api/logbook"
        if start_time:
            path = f"{path}/{_seg(start_time)}"

        params: dict[str, str] = {}
        if entity_id:
            params["entity"] = entity_id
        if end_time:
            params["end_time"] = end_time

        return await self._request("GET", path, params=params)

    async def get_error_log(self) -> str:
        """GET /api/error_log – return the plain-text error log."""
        return await self._request("GET", "/api/error_log")

    # ------------------------------------------------------------------
    # Template rendering
    # ------------------------------------------------------------------

    async def render_template(self, template: str) -> str:
        """POST /api/template – render a Jinja2 template on HA."""
        return await self._request("POST", "/api/template", json={"template": template})

    # ------------------------------------------------------------------
    # Config check
    # ------------------------------------------------------------------

    async def check_config(self) -> dict:
        """POST /api/config/core/check_config – validate HA configuration."""
        return await self._request("POST", "/api/config/core/check_config")

    async def get_config(self) -> dict:
        """GET /api/config – return core configuration (version, components, units)."""
        return await self._request("GET", "/api/config")

    async def get_services(self) -> list[dict]:
        """GET /api/services – return all available service domains and services."""
        return await self._request("GET", "/api/services")

    # ------------------------------------------------------------------
    # Config entries (integrations)
    # ------------------------------------------------------------------

    async def reload_config_entry(self, entry_id: str) -> dict:
        """POST /api/config/config_entries/entry/{entry_id}/reload."""
        return await self._request(
            "POST", f"/api/config/config_entries/entry/{_seg(entry_id)}/reload"
        )

    async def set_config_entry_disabled(
        self, entry_id: str, disabled_by: str | None
    ) -> dict:
        """POST /api/config/config_entries/entry/{entry_id}/disable.

        Pass ``disabled_by="user"`` to disable, or ``None`` to (re-)enable.
        """
        return await self._request(
            "POST",
            f"/api/config/config_entries/entry/{_seg(entry_id)}/disable",
            json={"disabled_by": disabled_by},
        )

    async def delete_config_entry(self, entry_id: str) -> dict:
        """DELETE /api/config/config_entries/entry/{entry_id}."""
        return await self._request(
            "DELETE", f"/api/config/config_entries/entry/{_seg(entry_id)}"
        )

    # ------------------------------------------------------------------
    # Data entry flows (config, options, subentry)
    # ------------------------------------------------------------------

    _FLOW_BASES = {
        "config": "/api/config/config_entries/flow",
        "options": "/api/config/config_entries/options/flow",
        "subentry": "/api/config/config_entries/subentries/flow",
    }

    async def get_flow_handlers(self, handler_type: str | None = None) -> list:
        """GET /api/config/config_entries/flow_handlers[?type=integration|helper]."""
        params = {"type": handler_type} if handler_type else None
        return await self._request(
            "GET", "/api/config/config_entries/flow_handlers", params=params
        )

    async def start_flow(self, kind: str, payload: dict) -> dict:
        """POST to the flow index view of *kind* (config/options/subentry)."""
        return await self._request("POST", self._FLOW_BASES[kind], json=payload)

    async def get_flow(self, kind: str, flow_id: str) -> dict:
        """GET the current step of a flow."""
        return await self._request("GET", f"{self._FLOW_BASES[kind]}/{_seg(flow_id)}")

    async def continue_flow(self, kind: str, flow_id: str, user_input: dict) -> dict:
        """POST user input to the current step of a flow."""
        return await self._request(
            "POST", f"{self._FLOW_BASES[kind]}/{_seg(flow_id)}", json=user_input
        )

    async def abort_flow(self, kind: str, flow_id: str) -> dict:
        """DELETE a flow in progress."""
        return await self._request(
            "DELETE", f"{self._FLOW_BASES[kind]}/{_seg(flow_id)}"
        )

    # ------------------------------------------------------------------
    # Automation CRUD
    # ------------------------------------------------------------------

    async def get_automation_config(self, automation_id: str) -> dict:
        """GET /api/config/automation/config/{id}."""
        return await self._request(
            "GET", f"/api/config/automation/config/{_seg(automation_id)}"
        )

    async def save_automation_config(self, automation_id: str, config: dict) -> None:
        """POST /api/config/automation/config/{id}."""
        await self._request(
            "POST", f"/api/config/automation/config/{_seg(automation_id)}", json=config
        )

    async def delete_automation_config(self, automation_id: str) -> None:
        """DELETE /api/config/automation/config/{id}."""
        await self._request(
            "DELETE", f"/api/config/automation/config/{_seg(automation_id)}"
        )

    # ------------------------------------------------------------------
    # Script CRUD
    # ------------------------------------------------------------------

    async def get_script_config(self, script_id: str) -> dict:
        """GET /api/config/script/config/{id}."""
        return await self._request(
            "GET", f"/api/config/script/config/{_seg(script_id)}"
        )

    async def save_script_config(self, script_id: str, config: dict) -> None:
        """POST /api/config/script/config/{id}."""
        await self._request(
            "POST", f"/api/config/script/config/{_seg(script_id)}", json=config
        )

    async def delete_script_config(self, script_id: str) -> None:
        """DELETE /api/config/script/config/{id}."""
        await self._request(
            "DELETE", f"/api/config/script/config/{_seg(script_id)}"
        )

    # ------------------------------------------------------------------
    # Scene CRUD
    # ------------------------------------------------------------------

    async def get_scene_config(self, scene_id: str) -> dict:
        """GET /api/config/scene/config/{id}."""
        return await self._request(
            "GET", f"/api/config/scene/config/{_seg(scene_id)}"
        )

    async def save_scene_config(self, scene_id: str, config: dict) -> None:
        """POST /api/config/scene/config/{id}."""
        await self._request(
            "POST", f"/api/config/scene/config/{_seg(scene_id)}", json=config
        )

    async def delete_scene_config(self, scene_id: str) -> None:
        """DELETE /api/config/scene/config/{id}."""
        await self._request(
            "DELETE", f"/api/config/scene/config/{_seg(scene_id)}"
        )

    # ------------------------------------------------------------------
    # Services
    # ------------------------------------------------------------------

    async def call_service(
        self, domain: str, service: str, data: dict | None = None
    ) -> list[dict]:
        """POST /api/services/{domain}/{service} – call a HA service."""
        return await self._request(
            "POST",
            f"/api/services/{_seg(domain)}/{_seg(service)}",
            json=data or {},
        )
