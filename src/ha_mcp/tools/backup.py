"""Backup tools built on the core backup WebSocket API (HA 2025.1+)."""

import json
import logging

from fastmcp import Context

from ha_mcp.util.context import get_clients
from ha_mcp.util.dry_run import confirm_change

logger = logging.getLogger(__name__)

_HINT = "Requires the 'backup' integration (Settings > System > Backups)."
_LOCAL_AGENT = "backup.local"


def _redact_config(config: dict) -> dict:
    create = config.get("create_backup")
    if isinstance(create, dict) and create.get("password"):
        config = {**config, "create_backup": {**create, "password": "***"}}
    return config


def _summarize_backup(backup: dict) -> dict:
    keys = (
        "backup_id", "name", "date", "with_automatic_settings",
        "database_included", "homeassistant_included", "addons", "folders",
        "failed_agent_ids",
    )
    summary = {k: backup[k] for k in keys if k in backup}
    agents = backup.get("agents") or {}
    summary["agents"] = {
        agent_id: {"size": info.get("size"), "protected": info.get("protected")}
        for agent_id, info in agents.items()
    }
    return summary


def register_backup_tools(mcp_server):
    """Register backup tools on the MCP server."""

    @mcp_server.tool()
    async def list_backups(ctx: Context) -> str:
        """List Home Assistant backups and the automatic-backup status.

        Returns each backup's id, name, date, contents and the agents
        (storage locations) holding it, plus the backup manager state and the
        last/next automatic backup times.
        """
        ws, _rest = get_clients(ctx)
        try:
            result = await ws.send_command("backup/info")
        except Exception as exc:
            return json.dumps({"error": f"Could not list backups: {exc}", "hint": _HINT})

        result = result or {}
        return json.dumps({
            "state": result.get("state"),
            "backups": [_summarize_backup(b) for b in result.get("backups", [])],
            "agent_errors": result.get("agent_errors", {}),
            "last_completed_automatic_backup": result.get("last_completed_automatic_backup"),
            "last_attempted_automatic_backup": result.get("last_attempted_automatic_backup"),
            "next_automatic_backup": result.get("next_automatic_backup"),
        }, indent=2)

    @mcp_server.tool()
    async def list_backup_agents(ctx: Context) -> str:
        """List backup agents (storage locations) such as 'backup.local',
        'hassio.local', cloud or network storage. Use their agent_id values in
        create_backup and update_backup_config.
        """
        ws, _rest = get_clients(ctx)
        try:
            result = await ws.send_command("backup/agents/info")
        except Exception as exc:
            return json.dumps({"error": f"Could not list backup agents: {exc}", "hint": _HINT})
        return json.dumps(result, indent=2)

    @mcp_server.tool()
    async def get_backup_config(ctx: Context) -> str:
        """Get the automatic backup configuration: schedule, retention, which
        agents to back up to, what to include, and per-agent settings. The
        backup encryption password is redacted.
        """
        ws, _rest = get_clients(ctx)
        try:
            result = await ws.send_command("backup/config/info")
        except Exception as exc:
            return json.dumps({"error": f"Could not read backup config: {exc}", "hint": _HINT})
        config = (result or {}).get("config", {})
        return json.dumps({"config": _redact_config(config)}, indent=2)

    @mcp_server.tool()
    async def update_backup_config(ctx: Context, config: str) -> str:
        """Update the automatic backup configuration.

        Args:
            config: JSON object with any of these keys (all optional):
                - create_backup: {agent_ids: [str], include_database: bool,
                  include_all_addons: bool, include_addons: [str] | null,
                  include_folders: [str] | null, name: str | null,
                  password: str | null}
                - retention: {copies: int >= 1 | null, days: int >= 1 | null}
                - schedule: {recurrence: "never" | "daily" | "custom_days",
                  days: ["mon", ...], time: "HH:MM" | null}
                - agents: {agent_id: {protected: bool, retention: {...} | null}}
                - automatic_backups_configured: bool

        Example: '{"schedule": {"recurrence": "daily", "time": "03:30"},
        "retention": {"copies": 7}, "create_backup": {"agent_ids": ["backup.local"]}}'
        """
        try:
            changes = json.loads(config)
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"Invalid JSON in config: {exc}"})
        if not isinstance(changes, dict):
            return json.dumps({"error": "config must be a JSON object"})
        changes = {k: v for k, v in changes.items() if k not in ("id", "type")}

        if not await confirm_change(
            ctx, action="UPDATE", entity_type="backup config",
            identifier="automatic backups", config=_redact_config(changes),
        ):
            return json.dumps({"status": "cancelled", "message": "Update cancelled."})

        ws, _rest = get_clients(ctx)
        try:
            await ws.send_command("backup/config/update", **changes)
        except Exception as exc:
            return json.dumps({"error": f"Could not update backup config: {exc}"})
        return json.dumps({"status": "updated", "changes": _redact_config(changes)}, indent=2)

    @mcp_server.tool()
    async def create_backup(
        ctx: Context,
        name: str | None = None,
        agent_ids: list[str] | None = None,
        include_database: bool = True,
    ) -> str:
        """Create a Home Assistant backup, e.g. before risky configuration changes.

        Args:
            name: Optional backup name.
            agent_ids: Agents to store the backup on (see list_backup_agents).
                When omitted, the stored automatic-backup settings are used if
                they name any agents; otherwise the local agent is used.
            include_database: Include the recorder database (ignored when the
                automatic-backup settings are used; set false or pass a name
                or agent_ids to force an explicit backup).

        The backup runs in the background; check list_backups for progress.
        """
        ws, _rest = get_clients(ctx)

        use_automatic = False
        if not agent_ids and name is None and include_database:
            try:
                info = await ws.send_command("backup/config/info")
                use_automatic = bool(
                    ((info or {}).get("config", {}).get("create_backup") or {}).get("agent_ids")
                )
            except Exception as exc:
                logger.warning("Could not read backup config: %s", exc)

        if not use_automatic and not agent_ids:
            try:
                agents = (await ws.send_command("backup/agents/info") or {}).get("agents", [])
            except Exception as exc:
                return json.dumps({"error": f"Could not list backup agents: {exc}", "hint": _HINT})
            ids = [a.get("agent_id") for a in agents]
            local = [i for i in ids if i in (_LOCAL_AGENT, "hassio.local")]
            agent_ids = local[:1] or ids[:1]
            if not agent_ids:
                return json.dumps({"error": "No backup agents available.", "hint": _HINT})

        preview = (
            {"mode": "automatic backup settings"}
            if use_automatic
            else {"name": name, "agent_ids": agent_ids, "include_database": include_database}
        )
        if not await confirm_change(
            ctx, action="CREATE", entity_type="backup",
            identifier=name or "backup", config=preview,
        ):
            return json.dumps({"status": "cancelled", "message": "Backup cancelled."})

        try:
            if use_automatic:
                result = await ws.send_command("backup/generate_with_automatic_settings")
            else:
                params = {"agent_ids": agent_ids, "include_database": include_database}
                if name:
                    params["name"] = name
                result = await ws.send_command("backup/generate", **params)
        except Exception as exc:
            return json.dumps({"error": f"Could not create backup: {exc}", "hint": _HINT})
        return json.dumps({"status": "started", "result": result}, indent=2)

    @mcp_server.tool()
    async def delete_backup(ctx: Context, backup_id: str) -> str:
        """Permanently delete a backup from all agents that hold it.

        Args:
            backup_id: The backup_id from list_backups.
        """
        ws, _rest = get_clients(ctx)
        try:
            details = await ws.send_command("backup/details", backup_id=backup_id)
        except Exception as exc:
            return json.dumps({"error": f"Could not read backup {backup_id}: {exc}"})
        backup = (details or {}).get("backup")
        if not backup:
            return json.dumps({"error": f"Backup {backup_id} not found."})

        if not await confirm_change(
            ctx, action="DELETE", entity_type="backup",
            identifier=backup_id, config=_summarize_backup(backup),
        ):
            return json.dumps({"status": "cancelled", "message": "Delete cancelled."})

        try:
            result = await ws.send_command("backup/delete", backup_id=backup_id)
        except Exception as exc:
            return json.dumps({"error": f"Could not delete backup: {exc}"})
        return json.dumps({
            "status": "deleted",
            "backup_id": backup_id,
            "agent_errors": (result or {}).get("agent_errors", {}),
        }, indent=2)
