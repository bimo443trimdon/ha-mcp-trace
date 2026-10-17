"""Diagnostics tools: repairs, system log, automation/script traces, target discovery."""

import json
import logging

from fastmcp import Context

from ha_mcp.util.context import get_clients
from ha_mcp.util.dry_run import confirm_change
from ha_mcp.util.redact import redact

logger = logging.getLogger(__name__)

TRACE_DOMAINS = ("automation", "script")
TARGET_KEYS = ("entity_id", "device_id", "area_id", "floor_id", "label_id")
MAX_OUTPUT_CHARS = 30_000
MAX_LOG_ENTRIES = 50
MAX_TRACE_STEPS = 60


def _dump(payload) -> str:
    text = json.dumps(payload, indent=2, default=str)
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return json.dumps(
        {"truncated": True, "note": "Output exceeded size cap; narrow the query.", "preview": text[:MAX_OUTPUT_CHARS]},
        indent=2,
    )


def _error(message: str) -> str:
    return json.dumps({"error": message})


def _parse_target(target: str) -> dict | str:
    try:
        parsed = json.loads(target)
    except json.JSONDecodeError as exc:
        return f"Invalid JSON in target: {exc}"
    if not isinstance(parsed, dict) or not parsed:
        return "target must be a non-empty JSON object."
    unknown = set(parsed) - set(TARGET_KEYS)
    if unknown:
        return f"Unknown target keys {sorted(unknown)}; allowed: {list(TARGET_KEYS)}."
    return {k: v if isinstance(v, list) else [v] for k, v in parsed.items()}


def _summarize_log_entry(entry: dict) -> dict:
    messages = [redact(str(m)) for m in entry.get("message", [])]
    summary = {
        "level": entry.get("level"),
        "logger": entry.get("name"),
        "message": messages[0] if len(messages) == 1 else messages,
        "source": entry.get("source"),
        "count": entry.get("count"),
        "first_occurred": entry.get("first_occurred"),
        "last_occurred": entry.get("timestamp"),
    }
    exception = entry.get("exception")
    if exception:
        summary["exception"] = redact(exception)[-2_000:]
    return summary


def summarize_trace(trace: dict) -> dict:
    steps = []
    failed_step = None
    for path, elements in (trace.get("trace") or {}).items():
        for element in elements:
            step = {"path": path}
            for key in ("error", "result", "child_id"):
                if key in element:
                    step[key] = element[key]
            if element.get("template_errors"):
                step["template_errors"] = element["template_errors"]
            if "error" in element and failed_step is None:
                failed_step = path
            steps.append(step)

    conditions = [
        {"path": s["path"], "result": s.get("result", {}).get("result")}
        for s in steps
        if s["path"].startswith("condition") or "/conditions/" in s["path"]
    ]

    trigger = trace.get("trigger")
    if trigger is None:
        trigger_step = (trace.get("trace") or {}).get("trigger/0") or []
        if trigger_step:
            trigger = trigger_step[0].get("changed_variables", {}).get("trigger", {}).get("description")

    return {
        "domain": trace.get("domain"),
        "item_id": trace.get("item_id"),
        "run_id": trace.get("run_id"),
        "state": trace.get("state"),
        "script_execution": trace.get("script_execution"),
        "timestamp": trace.get("timestamp"),
        "trigger": trigger,
        "error": trace.get("error"),
        "failed_step": failed_step,
        "last_step": trace.get("last_step"),
        "condition_results": conditions,
        "steps": steps[:MAX_TRACE_STEPS],
        "steps_truncated": len(steps) > MAX_TRACE_STEPS,
    }


def register_diagnostics_tools(mcp_server):
    """Register repairs, system-log, trace and target-discovery tools."""

    @mcp_server.tool()
    async def list_repairs(ctx: Context, include_ignored: bool = False) -> str:
        """List open Repairs issues (Settings > System > Repairs).

        Repairs are Home Assistant's to-do list of setup problems: deprecated
        YAML, broken integrations, required migrations, and so on. Start here
        when auditing or cleaning up an installation.

        Args:
            include_ignored: Also return issues the user dismissed.

        Returns issues with domain, issue_id, severity, is_fixable,
        translation_key/placeholders, learn_more_url and breaks_in_ha_version.
        """
        ws, _rest = get_clients(ctx)
        result = await ws.send_command("repairs/list_issues")
        issues = result.get("issues", []) if isinstance(result, dict) else result or []
        if not include_ignored:
            issues = [i for i in issues if not i.get("ignored") and not i.get("dismissed_version")]
        return _dump({"count": len(issues), "issues": issues})

    @mcp_server.tool()
    async def ignore_repair(ctx: Context, domain: str, issue_id: str, ignore: bool = True) -> str:
        """Ignore (or un-ignore) a Repairs issue.

        Args:
            domain: The integration domain that raised the issue.
            issue_id: The issue_id from list_repairs.
            ignore: True to dismiss, False to restore it.
        """
        if not await confirm_change(
            ctx,
            "IGNORE" if ignore else "UNIGNORE",
            "repair",
            f"{domain}.{issue_id}",
            {"domain": domain, "issue_id": issue_id, "ignore": ignore},
        ):
            return json.dumps({"status": "cancelled"})
        ws, _rest = get_clients(ctx)
        await ws.send_command("repairs/ignore_issue", domain=domain, issue_id=issue_id, ignore=ignore)
        return json.dumps({"status": "ignored" if ignore else "restored", "domain": domain, "issue_id": issue_id})

    @mcp_server.tool()
    async def get_system_log(ctx: Context, level: str | None = None, logger_filter: str | None = None) -> str:
        """Get the structured, deduplicated system log (Settings > System > Logs).

        Each entry is one unique error/warning with an occurrence count, so this
        is far more compact than get_error_log. Secrets are redacted.

        Args:
            level: Only return this level (ERROR, WARNING, CRITICAL, INFO).
            logger_filter: Only return entries whose logger name contains this
                text (e.g. 'zha' or 'homeassistant.components.mqtt').
        """
        ws, _rest = get_clients(ctx)
        entries = await ws.send_command("system_log/list") or []
        if level:
            entries = [e for e in entries if str(e.get("level", "")).upper() == level.upper()]
        if logger_filter:
            entries = [e for e in entries if logger_filter.lower() in str(e.get("name", "")).lower()]
        entries = sorted(entries, key=lambda e: e.get("timestamp") or 0, reverse=True)
        return _dump({
            "count": len(entries),
            "entries": [_summarize_log_entry(e) for e in entries[:MAX_LOG_ENTRIES]],
        })

    @mcp_server.tool()
    async def list_traces(ctx: Context, domain: str = "automation", item_id: str | None = None) -> str:
        """List stored execution traces for automations or scripts.

        Args:
            domain: 'automation' or 'script'.
            item_id: Optional automation config id (the 'id' attribute of the
                automation entity) or script object id (e.g. 'bedtime' for
                script.bedtime). Omit to list traces for every item.

        Returns short summaries (run_id, state, script_execution, last_step,
        error, trigger, timestamps). Pass a run_id to get_trace for details.
        """
        if domain not in TRACE_DOMAINS:
            return _error(f"domain must be one of {list(TRACE_DOMAINS)}")
        ws, _rest = get_clients(ctx)
        payload = {"domain": domain}
        if item_id:
            payload["item_id"] = item_id
        traces = await ws.send_command("trace/list", **payload) or []
        traces = sorted(traces, key=lambda t: (t.get("timestamp") or {}).get("start") or "", reverse=True)
        return _dump({"count": len(traces), "traces": traces[:50]})

    @mcp_server.tool()
    async def get_trace(ctx: Context, domain: str, item_id: str, run_id: str) -> str:
        """Explain one automation/script run: what triggered it, which
        conditions passed, which step failed and why.

        Args:
            domain: 'automation' or 'script'.
            item_id: Automation config id or script object id.
            run_id: From list_traces.
        """
        if domain not in TRACE_DOMAINS:
            return _error(f"domain must be one of {list(TRACE_DOMAINS)}")
        ws, _rest = get_clients(ctx)
        trace = await ws.send_command("trace/get", domain=domain, item_id=item_id, run_id=run_id)
        return _dump(summarize_trace(trace or {}))

    async def _for_target(ctx: Context, command: str, target: str, expand_group: bool) -> str:
        parsed = _parse_target(target)
        if isinstance(parsed, str):
            return _error(parsed)
        ws, _rest = get_clients(ctx)
        result = await ws.send_command(command, target=parsed, expand_group=expand_group)
        return _dump(result)

    @mcp_server.tool()
    async def find_triggers_for_target(ctx: Context, target: str, expand_group: bool = True) -> str:
        """List the purpose-specific triggers usable for a target (HA 2025.12+).

        Use this before writing an automation to discover modern triggers such
        as 'light.turned_on' or 'battery.became_low' instead of guessing raw
        state triggers.

        Args:
            target: JSON object with any of entity_id, device_id, area_id,
                floor_id, label_id (string or list), e.g.
                '{"area_id": ["kitchen"]}'.
            expand_group: Expand group entities to their members.
        """
        return await _for_target(ctx, "get_triggers_for_target", target, expand_group)

    @mcp_server.tool()
    async def find_conditions_for_target(ctx: Context, target: str, expand_group: bool = True) -> str:
        """List the purpose-specific conditions usable for a target (HA 2025.12+).

        Args:
            target: JSON object with any of entity_id, device_id, area_id,
                floor_id, label_id (string or list).
            expand_group: Expand group entities to their members.
        """
        return await _for_target(ctx, "get_conditions_for_target", target, expand_group)

    @mcp_server.tool()
    async def find_services_for_target(ctx: Context, target: str, expand_group: bool = True) -> str:
        """List the actions (services) usable for a target (HA 2025.12+).

        Args:
            target: JSON object with any of entity_id, device_id, area_id,
                floor_id, label_id (string or list).
            expand_group: Expand group entities to their members.
        """
        return await _for_target(ctx, "get_services_for_target", target, expand_group)
