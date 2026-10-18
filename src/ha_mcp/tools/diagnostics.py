"""Diagnostics tools: repairs, system log, automation/script traces, target discovery."""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

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
MAX_DIAGNOSIS_TRACES = 5
MAX_DIAGNOSIS_ENTITIES = 10
MAX_HISTORY_CHANGES_PER_ENTITY = 10


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


def _parse_datetime(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _trace_started(trace: dict) -> datetime | None:
    timestamp = trace.get("timestamp") or {}
    return _parse_datetime(timestamp.get("start")) if isinstance(timestamp, dict) else None


def _run_failed(run: dict) -> bool:
    return bool(
        run.get("error")
        or run.get("failed_step")
        or run.get("script_execution") in ("error", "failed")
    )


def _run_blocked_by_condition(run: dict) -> bool:
    return run.get("script_execution") == "failed_conditions" or any(
        item.get("result") is False for item in run.get("condition_results", [])
    )


def _automation_entity_references(value) -> list[str]:
    references = set()

    def visit(node):
        if isinstance(node, dict):
            for key, child in node.items():
                if key == "entity_id":
                    values = child if isinstance(child, list) else [child]
                    references.update(
                        item
                        for item in values
                        if isinstance(item, str) and "." in item
                    )
                else:
                    visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(value)
    return sorted(references)


def _history_records(history) -> list[dict]:
    if not isinstance(history, list):
        raise RuntimeError("Home Assistant returned an unexpected entity history")
    records = []
    for group in history:
        items = group if isinstance(group, list) else [group]
        if any(not isinstance(record, dict) for record in items):
            raise RuntimeError("Home Assistant returned a malformed entity history")
        records.extend(items)
    return records


def _diagnosis_logbook_entry(entry: dict) -> dict:
    summary = {"source": "Home Assistant logbook"}
    summary.update(
        {
            key: entry.get(key)
            for key in ("when", "timestamp", "name", "entity_id", "domain", "message")
            if entry.get(key) is not None
        }
    )
    return summary


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

    @mcp_server.tool()
    async def get_automation_diagnosis(
        ctx: Context,
        automation_id: str,
        lookback_minutes: int = 60,
        trace_limit: int = 3,
    ) -> str:
        """Build an evidence-based diagnosis for a Home Assistant automation.

        Accepts either the automation entity ID (automation.example) or its
        config ID. Checks current enabled state, recent stored traces, trigger
        and condition entity history, and matching logbook entries.

        Missing traces do not prove that an automation never ran: Home
        Assistant only retains a limited number of traces, and some trigger
        types cannot be checked through entity history.
        """
        if not automation_id or "/" in automation_id or "\\" in automation_id:
            raise ValueError("automation_id must be a non-empty automation ID")
        if not 1 <= lookback_minutes <= 1440:
            raise ValueError("lookback_minutes must be between 1 and 1440")
        if not 1 <= trace_limit <= MAX_DIAGNOSIS_TRACES:
            raise ValueError(
                f"trace_limit must be between 1 and {MAX_DIAGNOSIS_TRACES}"
            )

        ws, rest = get_clients(ctx)
        states = await rest.get_states()
        automation_states = [
            state
            for state in states
            if str(state.get("entity_id", "")).startswith("automation.")
        ]
        entity_state = None
        if automation_id.startswith("automation."):
            entity_state = next(
                (
                    state
                    for state in automation_states
                    if state.get("entity_id") == automation_id
                ),
                None,
            )
            if entity_state is None:
                raise ValueError(f"Automation entity not found: {automation_id}")
            config_id = (entity_state.get("attributes") or {}).get("id")
            if not isinstance(config_id, str) or not config_id:
                raise RuntimeError(
                    f"Home Assistant did not provide the config ID for {automation_id}"
                )
        else:
            config_id = automation_id
            entity_state = next(
                (
                    state
                    for state in automation_states
                    if (state.get("attributes") or {}).get("id") == config_id
                ),
                None,
            )

        config = await rest.get_automation_config(config_id)
        if not isinstance(config, dict):
            raise RuntimeError("Home Assistant returned an unexpected automation config")

        now = datetime.now(timezone.utc)
        start = now - timedelta(minutes=lookback_minutes)
        start_time = start.isoformat(timespec="seconds")
        end_time = now.isoformat(timespec="seconds")

        trigger_config = config.get("triggers", config.get("trigger", []))
        condition_config = config.get("conditions", config.get("condition", []))
        trigger_entities = _automation_entity_references(trigger_config)
        condition_entities = _automation_entity_references(condition_config)
        history_entities = sorted(set(trigger_entities + condition_entities))
        included_history_entities = history_entities[:MAX_DIAGNOSIS_ENTITIES]

        current_states = {
            state.get("entity_id"): state
            for state in states
            if isinstance(state, dict) and state.get("entity_id")
        }
        history_results = await asyncio.gather(
            *(
                rest.get_history(entity_id, start_time, end_time)
                for entity_id in included_history_entities
            )
        )
        entity_history = []
        for entity_id, history in zip(included_history_entities, history_results):
            records = _history_records(history)
            records.sort(
                key=lambda record: _parse_datetime(
                    record.get("last_changed") or record.get("last_updated")
                )
                or datetime.min.replace(tzinfo=timezone.utc)
            )
            state = current_states.get(entity_id) or {}
            entity_history.append(
                {
                    "source": "Home Assistant entity history",
                    "entity_id": entity_id,
                    "current_state": state.get("state"),
                    "current_last_changed": state.get("last_changed"),
                    "window_start": start_time,
                    "window_end": end_time,
                    "change_count": len(records),
                    "recent_changes": [
                        {
                            key: record.get(key)
                            for key in ("state", "last_changed", "last_updated")
                            if record.get(key) is not None
                        }
                        for record in records[-MAX_HISTORY_CHANGES_PER_ENTITY:]
                    ],
                }
            )

        entity_id = entity_state.get("entity_id") if entity_state else None
        logbook_entries = []
        if entity_id:
            entries = await rest.get_logbook(entity_id, start_time, end_time)
            if not isinstance(entries, list) or any(
                not isinstance(entry, dict) for entry in entries
            ):
                raise RuntimeError("Home Assistant returned an unexpected logbook result")
            logbook_entries = [
                _diagnosis_logbook_entry(entry)
                for entry in entries[-MAX_LOG_ENTRIES:]
            ]

        summaries = await ws.send_command(
            "trace/list", domain="automation", item_id=config_id
        )
        if not isinstance(summaries, list) or any(
            not isinstance(summary, dict) for summary in summaries
        ):
            raise RuntimeError("Home Assistant returned an unexpected trace list")
        ordered_summaries = sorted(
            summaries,
            key=lambda trace: _trace_started(trace).timestamp()
            if _trace_started(trace)
            else 0,
            reverse=True,
        )
        in_window = [
            summary
            for summary in ordered_summaries
            if (
                _trace_started(summary) is None
                or _trace_started(summary) >= start
            )
        ]

        runs = []
        for summary in in_window[:trace_limit]:
            run_id = summary.get("run_id")
            if not isinstance(run_id, str) or not run_id:
                raise RuntimeError("Home Assistant returned a trace without a run_id")
            trace = await ws.send_command(
                "trace/get",
                domain="automation",
                item_id=config_id,
                run_id=run_id,
            )
            if not isinstance(trace, dict):
                raise RuntimeError(f"Home Assistant returned an invalid trace: {run_id}")
            runs.append(summarize_trace(trace))

        observations = []
        if entity_state:
            observations.append(
                {
                    "fact": (
                        "The automation is currently enabled."
                        if entity_state.get("state") == "on"
                        else f"The automation is currently {entity_state.get('state')}."
                    ),
                    "source": "automation entity state",
                    "timestamp": entity_state.get("last_changed"),
                }
            )
        for entry in logbook_entries:
            entry_message = (
                entry.get("message") or entry.get("name") or "activity recorded"
            )
            observations.append(
                {
                    "fact": f"Logbook entry: {entry_message}",
                    "source": entry["source"],
                    "timestamp": entry.get("when") or entry.get("timestamp"),
                }
            )
        for run in runs:
            observations.append(
                {
                    "fact": (
                        f"Stored trace run {run.get('run_id')} reports "
                        f"script_execution={run.get('script_execution')}."
                    ),
                    "source": "automation trace",
                    "timestamp": (run.get("timestamp") or {}).get("start"),
                }
            )
            if _run_failed(run):
                failed_step = run.get("failed_step") or run.get("last_step") or "unknown step"
                failure_detail = run.get("error") or (
                    f"script_execution={run.get('script_execution')}"
                )
                observations.append(
                    {
                        "fact": (
                            f"Run {run.get('run_id')} reported an execution error "
                            f"at {failed_step}: {failure_detail}"
                        ),
                        "source": "automation trace",
                        "timestamp": (run.get("timestamp") or {}).get("start"),
                    }
                )
            if run.get("script_execution") == "failed_conditions" and not any(
                item.get("result") is False
                for item in run.get("condition_results", [])
            ):
                observations.append(
                    {
                        "fact": (
                            f"Home Assistant reports that conditions blocked run "
                            f"{run.get('run_id')}."
                        ),
                        "source": "automation trace",
                        "timestamp": (run.get("timestamp") or {}).get("start"),
                    }
                )
            for condition in run.get("condition_results", []):
                if condition.get("result") is False:
                    observations.append(
                        {
                            "fact": (
                                f"Condition {condition.get('path')} evaluated false "
                                f"in run {run.get('run_id')}."
                            ),
                            "source": "automation trace",
                            "timestamp": (run.get("timestamp") or {}).get("start"),
                        }
                    )

        failed_runs = [run for run in runs if _run_failed(run)]
        blocked_runs = [run for run in runs if _run_blocked_by_condition(run)]
        if failed_runs:
            status = "execution_error_observed"
            summary = (
                f"{len(failed_runs)} of {len(runs)} retrieved stored run(s) "
                "reported an execution error."
            )
        elif blocked_runs:
            status = "condition_blocked"
            summary = (
                "At least one retrieved run was blocked by automation conditions."
            )
        elif entity_state and entity_state.get("state") == "off":
            status = "automation_disabled"
            summary = "The automation is currently disabled."
        elif entity_state and entity_state.get("state") != "on":
            status = "automation_state_unknown"
            summary = (
                f"The automation state is {entity_state.get('state')!r}; "
                "its enabled status cannot be confirmed."
            )
        elif not runs and logbook_entries:
            status = "logbook_activity_without_trace"
            entry_word = "entry" if len(logbook_entries) == 1 else "entries"
            summary = (
                f"No stored trace was retrieved, but {len(logbook_entries)} matching "
                f"logbook {entry_word} were found in the selected window."
            )
        elif not runs:
            status = "no_trace_in_window"
            summary = (
                "No stored automation trace with a known run time in the selected "
                "window was found."
            )
        else:
            status = "no_failure_observed"
            summary = (
                "The retrieved stored runs show no explicit failed step or false "
                "condition; this does not confirm that the expected trigger occurred."
            )

        hypotheses = []
        limitations = []
        if not runs:
            if logbook_entries:
                hypotheses.append(
                    "The logbook activity may correspond to an automation run whose "
                    "trace is no longer retained; inspect the entries before "
                    "concluding whether the expected action occurred."
                )
            else:
                hypotheses.append(
                    "The automation may not have triggered in this interval, or Home "
                    "Assistant may no longer retain a trace for that run."
                )
            limitations.append(
                "An empty trace result cannot establish that the automation never "
                "ran; Home Assistant retains only a limited number of traces."
            )
            if not trigger_entities:
                limitations.append(
                    "No direct entity IDs were found in the configured triggers. "
                    "Time, event, device, template, and other trigger types cannot "
                    "be verified from entity history alone."
                )
            elif not any(item["change_count"] for item in entity_history):
                observations.append(
                    {
                        "fact": (
                            "No state changes were returned for the referenced "
                            "trigger/condition entities during the selected interval."
                        ),
                        "source": "entity history",
                        "timestamp": start_time,
                    }
                )
                limitations.append(
                    "No matching entity changes is not proof that a trigger could "
                    "not occur; history may be incomplete or the trigger may use "
                    "other conditions."
                )
        if len(history_entities) > len(included_history_entities):
            limitations.append(
                f"Entity history was capped at {MAX_DIAGNOSIS_ENTITIES} referenced "
                "entities."
            )
        if any(_trace_started(trace) is None for trace in ordered_summaries):
            limitations.append(
                "Some stored traces had no parseable start timestamp and could not "
                "be reliably assigned to the requested time window."
            )

        result = {
            "automation": {
                "entity_id": entity_id,
                "config_id": config_id,
                "alias": config.get("alias"),
                "state": entity_state.get("state") if entity_state else None,
                "config": {
                    key: config[key]
                    for key in ("triggers", "trigger", "conditions", "condition", "actions", "action")
                    if key in config
                },
            },
            "time_window": {
                "start": start_time,
                "end": end_time,
                "lookback_minutes": lookback_minutes,
            },
            "assessment": {
                "status": status,
                "summary": summary,
                "hypotheses": hypotheses,
            },
            "observations": observations,
            "evidence": {
                "stored_trace_count_in_window": sum(
                    _trace_started(trace) is not None for trace in in_window
                ),
                "stored_trace_count_with_unknown_timestamp": sum(
                    _trace_started(trace) is None for trace in in_window
                ),
                "traces_returned": runs,
                "trigger_entity_ids": trigger_entities,
                "condition_entity_ids": condition_entities,
                "entity_history": entity_history,
                "logbook_entries": logbook_entries,
            },
            "limitations": limitations,
        }
        return redact(_dump(result))

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
