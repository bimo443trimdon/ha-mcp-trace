"""System tools: core config, system health, services, reload/restart, target resolution."""

import json
import logging

from fastmcp import Context

from ha_mcp.ha_client.models import HAConnectionError, HAConnectionLost
from ha_mcp.util.context import get_clients
from ha_mcp.util.dry_run import confirm_change

logger = logging.getLogger(__name__)


def register_system_tools(mcp_server):
    """Register system-level tools on the MCP server."""

    @mcp_server.tool()
    async def get_config(ctx: Context) -> str:
        """Get Home Assistant core configuration.

        Returns version, location, unit system, time zone, loaded components,
        and other core settings. Useful for troubleshooting and for tailoring
        suggestions to the installation.
        """
        _ws, rest = get_clients(ctx)
        return json.dumps(await rest.get_config(), indent=2)

    @mcp_server.tool()
    async def get_system_health(ctx: Context) -> str:
        """Get system health information for Home Assistant and its integrations.

        Aggregates the per-integration system health panels (e.g. version,
        cloud status, recorder/database stats, reachable endpoints).
        """
        ws, _rest = get_clients(ctx)
        try:
            result = await ws.send_command("system_health/info")
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": f"system_health/info failed: {exc}"})
        return json.dumps(result, indent=2)

    @mcp_server.tool()
    async def list_services(ctx: Context, domain: str | None = None) -> str:
        """List the services available in Home Assistant, optionally for one domain.

        Each domain maps to its services and their accepted fields. Use this to
        discover valid ``domain.service`` names and parameters before building
        automations, scripts, or calling a service.

        Args:
            domain: Optionally restrict the result to a single domain (e.g. 'light').
        """
        _ws, rest = get_clients(ctx)
        services = await rest.get_services()
        if domain:
            services = [s for s in services if s.get("domain") == domain]
        return json.dumps(services, indent=2)

    @mcp_server.tool()
    async def resolve_target(
        ctx: Context,
        entity_id: list[str] | None = None,
        device_id: list[str] | None = None,
        area_id: list[str] | None = None,
        label_id: list[str] | None = None,
        expand_group: bool = True,
    ) -> str:
        """Resolve a service target into the concrete entities/devices/areas it covers.

        Mirrors Home Assistant's target resolution: given any mix of entities,
        devices, areas, and labels, returns the full set of referenced entities
        (and devices/areas), plus any references that could not be matched.

        Args:
            entity_id: Entity IDs to include.
            device_id: Device IDs to expand to their entities.
            area_id: Area IDs to expand to their entities.
            label_id: Label IDs to expand to their entities.
            expand_group: Whether to expand group entities into members.
        """
        ws, _rest = get_clients(ctx)
        target = {
            k: v
            for k, v in {
                "entity_id": entity_id,
                "device_id": device_id,
                "area_id": area_id,
                "label_id": label_id,
            }.items()
            if v
        }
        if not target:
            return json.dumps({"error": "Provide at least one of entity_id/device_id/area_id/label_id."})

        result = await ws.send_command(
            "extract_from_target", target=target, expand_group=expand_group
        )
        return json.dumps(result, indent=2)

    @mcp_server.tool()
    async def reload_domain(
        ctx: Context, domain: str
    ) -> str:
        """Reload a configuration domain so YAML/config changes take effect.

        Calls the domain's ``reload`` service (e.g. 'automation', 'script',
        'scene', 'template', 'input_boolean', 'group'). For the whole of YAML
        configuration use domain 'homeassistant' (reloads core config + all
        reloadable domains via ``homeassistant.reload_all``).

        Args:
            domain: The domain to reload (or 'homeassistant' for reload_all).
        """
        ws, _rest = get_clients(ctx)
        service = "reload_all" if domain == "homeassistant" else "reload"

        if not await confirm_change(
            ctx=ctx, action="RELOAD", entity_type="domain",
            identifier=f"{domain}.{service}", config={"domain": domain, "service": service},
        ):
            return json.dumps({"status": "cancelled", "message": "Reload cancelled."})

        await ws.send_command("call_service", domain=domain, service=service)
        return json.dumps({"status": "reloaded", "domain": domain, "service": service})

    @mcp_server.tool()
    async def restart_home_assistant(
        ctx: Context, safe_mode: bool = False
    ) -> str:
        """Restart the Home Assistant core (validates config first).

        Runs a configuration check, refuses to restart if it fails, then calls
        ``homeassistant.restart``. This briefly takes HA offline.

        Args:
            safe_mode: Restart into safe mode (custom integrations disabled).
        """
        ws, rest = get_clients(ctx)

        try:
            check = await rest.check_config()
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": f"Config check failed to run: {exc}"})

        if check.get("result") != "valid":
            return json.dumps({
                "status": "aborted",
                "reason": "Configuration check failed; not restarting.",
                "errors": check.get("errors"),
            })

        if not await confirm_change(
            ctx=ctx, action="RESTART", entity_type="core",
            identifier="homeassistant", config={"safe_mode": safe_mode},
        ):
            return json.dumps({"status": "cancelled", "message": "Restart cancelled."})

        data = {"safe_mode": True} if safe_mode else {}
        try:
            await ws.send_command(
                "call_service", domain="homeassistant", service="restart", service_data=data
            )
        except (HAConnectionLost, HAConnectionError, TimeoutError):
            pass
        return json.dumps({"status": "restarting", "safe_mode": safe_mode})
