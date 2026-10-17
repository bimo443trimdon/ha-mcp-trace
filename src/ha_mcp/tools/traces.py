"""Read recent Home Assistant automation traces."""

import json

from fastmcp import Context

from ha_mcp.util.context import get_clients

_MAX_TRACES = 10


def register_trace_tools(mcp_server):
    """Register automation trace tools."""

    @mcp_server.tool()
    async def get_automation_traces(
        ctx: Context,
        automation_id: str,
        limit: int = 3,
    ) -> str:
        """Fetch recent traces for a Home Assistant automation.

        Args:
            automation_id: Automation entity ID, e.g. "automation.garage_door".
            limit: Number of recent traces to return (1–10; default 3).

        Returns the full trace data as JSON. Trace data may contain entity
        state and service details, so request only the traces needed.
        """
        domain, separator, item_id = automation_id.partition(".")
        if domain != "automation" or not separator or not item_id or "." in item_id:
            raise ValueError(
                "automation_id must be an automation entity ID, "
                'e.g. "automation.garage_door"'
            )
        if not 1 <= limit <= _MAX_TRACES:
            raise ValueError(f"limit must be between 1 and {_MAX_TRACES}")

        ws, _rest = get_clients(ctx)
        summaries = await ws.send_command(
            "trace/list",
            domain=domain,
            item_id=item_id,
        )
        if not isinstance(summaries, list):
            raise RuntimeError("Home Assistant returned an unexpected trace list")

        traces = []
        for summary in summaries[:limit]:
            run_id = summary.get("run_id") if isinstance(summary, dict) else None
            if not isinstance(run_id, str) or not run_id:
                raise RuntimeError("Home Assistant returned a trace without a run_id")

            trace = await ws.send_command(
                "trace/get",
                domain=domain,
                item_id=item_id,
                run_id=run_id,
            )
            traces.append(trace)

        return json.dumps(
            {
                "automation_id": automation_id,
                "count": len(traces),
                "traces": traces,
            },
            indent=2,
        )
