# Architecture

This document describes the internal structure of Home Assistant
MCP Server, how its components fit together, and how to extend
it with new tools.

## Project layout

```
src/ha_mcp/
├── __init__.py
├── __main__.py          # Entry point (ha-mcp CLI), refuses unauthenticated HTTP
├── auth.py              # Static API-key bearer verifier
├── config.py            # Settings via pydantic-settings
├── server.py            # FastMCP server, lifespan, auth, registration
├── ha_client/
│   ├── models.py        # Pydantic models and exceptions
│   ├── websocket.py     # Persistent WebSocket client
│   └── rest.py          # REST API client (path segments escaped via _seg)
├── tools/
│   ├── __init__.py      # register_all_tools + annotation/read-only policy
│   ├── registry.py      # Device, entity, area, floor, label queries
│   ├── registry_edit.py # Area, floor, label, entity, device edits
│   ├── registry_remove.py  # Remove entities and devices
│   ├── categories.py    # Category registry + assignment
│   ├── config_flow.py   # Config, options and subentry flows
│   ├── integration.py   # Config entry list/reload/enable
│   ├── state.py         # State, history, logbook, templates, error log
│   ├── automation.py    # Automation CRUD
│   ├── script.py        # Script CRUD
│   ├── scene.py         # Scene CRUD
│   ├── helper.py        # input_*, counter, timer, schedule helpers
│   ├── dashboard.py     # Lovelace dashboard management
│   ├── blueprint.py     # Blueprint management
│   ├── config_validation.py  # Config and YAML validation
│   ├── diagnostics.py   # Repairs, system log, traces, target discovery
│   ├── backup.py        # Backups and backup configuration
│   ├── system.py        # Reload, restart, health, services
│   ├── control.py       # call_service (opt-in, denylisted)
│   ├── events.py        # Bounded event listening
│   └── suggestions.py   # Proactive analysis and suggestions
├── prompts/
│   └── prompts.py       # MCP prompt templates
├── resources/
│   └── resources.py     # MCP resource templates
└── util/
    ├── context.py       # Clients from ctx.lifespan_context
    ├── dry_run.py       # confirm_change(): policy, validation gate, elicit
    ├── validation.py    # validate_config wrapper (plural + singular keys)
    ├── redact.py        # Secret redaction and truncation for logs
    ├── yaml_util.py     # YAML parse, format, diff utilities
    └── entity_analysis.py  # Rule-based suggestion engine
```

## Core components

### Server and lifespan (`server.py`)

The `server.py` module creates the `FastMCP` instance and manages
the server lifecycle. It uses an async context manager as the
lifespan handler to:

1. Create WebSocket and REST clients at startup.
2. Connect and authenticate both clients.
3. Yield the clients as a lifespan context dictionary
   (`{"ws": ws_client, "rest": rest_client}`).
4. Disconnect both clients on shutdown.

After creating the server, it calls `register_all_tools`,
`register_resources`, and `register_prompts` to wire up all
capabilities.

### Configuration (`config.py`)

Settings are loaded from environment variables using
`pydantic-settings` with the `HA_MCP_` prefix. The `Settings`
class validates the transport type and warns if the access token
is empty. It also provides computed properties for the base URL
(with trailing slash removed) and the WebSocket URL (protocol
auto-conversion from `http`/`https` to `ws`/`wss`).

A singleton `settings` instance is created at module load time.

### Entry point (`__main__.py`)

The `main()` function configures logging, verifies the token is
set, and starts the MCP server with the configured transport.
The `ha-mcp` console script (defined in `pyproject.toml`) calls
this function.

## Home Assistant clients

The server communicates with Home Assistant through two parallel
clients.

### WebSocket client (`ha_client/websocket.py`)

`HAWebSocketClient` maintains a persistent WebSocket connection
for real-time command execution. Key design decisions:

- **Authentication handshake** -- on connect, the client waits
  for the `auth_required` message, sends the token, and verifies
  `auth_ok`.
- **Message routing** -- each outgoing command gets a unique
  auto-incrementing ID. A background listener task dispatches
  incoming messages to per-ID `asyncio.Future` objects.
- **Concurrency** -- a semaphore limits concurrent in-flight
  commands to 10.
- **Reconnection** -- on connection loss, the client retries with
  exponential backoff (1 second to 60 seconds).

### REST client (`ha_client/rest.py`)

`HARestClient` wraps the Home Assistant HTTP API using `aiohttp`.
It provides typed methods for common endpoints:

- State queries (`/api/states`)
- History and logbook (`/api/history`, `/api/logbook`)
- Template rendering (`/api/template`)
- Configuration management (automation, script, scene CRUD)
- Service calls (`/api/services/{domain}/{service}`)

A semaphore limits concurrent HTTP requests to 5.

### Data models (`ha_client/models.py`)

Pydantic models define the shape of Home Assistant data:
`HADevice`, `HAEntity`, `HAState`, `HAArea`, `HAFloor`, `HALabel`,
`HAAutomation`, `HAScript`, `HAScene`, `HAService`, and
`HAValidationResult`.

Custom exceptions inherit from `HAError`:

- `HAConnectionError` -- connection failure
- `HAAuthError` -- authentication failure
- `HANotFoundError` -- resource not found (404)
- `HAValidationError` -- validation error (400)
- `HAConnectionLost` -- WebSocket connection dropped

## Tool registration pattern

Each tool module exports a `register_*_tools(mcp_server)` function
that defines tools as inner functions decorated with
`@mcp_server.tool()`. This pattern keeps tool definitions
self-contained while avoiding circular imports.

```python
# Example: tools/example.py
from ha_mcp.util.context import get_clients

def register_example_tools(mcp_server):

    @mcp_server.tool()
    async def my_tool(ctx: Context, param: str) -> str:
        """Tool description."""
        ws, rest = get_clients(ctx)
        result = await ws.send_command("some/command")
        return json.dumps(result, indent=2)
```

The `tools/__init__.py` module aggregates all registration
functions into `register_all_tools(mcp)`, which `server.py` calls
at import time.

### Accessing clients

Tools access the WebSocket and REST clients through the
`get_clients(ctx)` helper in `util/context.py`. This function
extracts the clients from the FastMCP lifespan context.

> **Warning:** Never import clients directly from `server.py`.
> That causes a circular import because `server.py` imports the
> tool modules.

## Authentication

For `http`/`sse`, `server.py` installs `ApiKeyVerifier` (a FastMCP
`TokenVerifier` using a constant-time compare) when `HA_MCP_API_KEY` is
set. `__main__.py` exits if it isn't, unless
`HA_MCP_ALLOW_UNAUTHENTICATED=true`. The add-on generates the key into
`/data/api_key`, and `ha_mcp_addon/guide_server.py` serves it only to
the ingress proxy (`172.30.32.2`).

## Tool registration policy

`register_all_tools()` passes each module a registrar instead of the
FastMCP server. The registrar derives MCP annotations from the tool
name (`list_`/`get_`/`find_`... are read-only; `delete_`/`remove_`/
`restart_` and `call_service` are destructive), skips write tools in
read-only mode, and skips `call_service` unless device control is on.
Name new tools with these prefixes.

## Confirmation flow

All mutating tools call `confirm_change(ctx, action, entity_type,
identifier, config, validation_result=None)` from `util/dry_run.py`:

1. Raises `ToolError` in read-only mode.
2. Raises `ToolError` if `validation_result` is invalid, so the model
   sees why.
3. With `confirm_mode=client`, returns `True`; the client's own tool
   approval is the human gate.
4. With `confirm_mode=elicit`, shows a YAML preview via `ctx.elicit()`
   and returns whether the user confirmed. If the client can't answer
   (including on 2026-07-28 protocol connections), it raises
   `ToolError` instead of applying the change.

There is deliberately no per-call bypass argument.

## Suggestion engine (`util/entity_analysis.py`)

The entity analysis module provides a rule-based pattern matching
engine used by the suggestion tools. It includes four main
functions:

- **`analyze_coverage`** -- calculates which entities are covered
  by automations and identifies gaps per area.
- **`generate_suggestions`** -- applies eight built-in rules to
  suggest automations based on entity types and relationships (for
  example, motion sensor + light in the same area suggests
  motion-activated lighting).
- **`detect_conflicts`** -- finds three types of conflicts between
  automations: shared trigger entities, opposing actions, and
  time-based overlaps.
- **`suggest_dashboard_layout`** -- generates a Lovelace dashboard
  config organized by area, using domain-appropriate card types.

## Adding a new tool module

To add a new category of tools:

1. Create a new file in `src/ha_mcp/tools/` (for example,
   `notification.py`).
2. Define a `register_notification_tools(mcp_server)` function
   with your tools as inner functions.
3. Import and call it from `tools/__init__.py` inside
   `register_all_tools`.
4. Use `get_clients(ctx)` from `util/context.py` to access the
   Home Assistant clients.
5. For mutating operations, use `confirm_change()` from
   `util/dry_run.py`.
6. Return JSON strings from all tools.

## Dependencies

| Package | Purpose |
|---|---|
| `fastmcp` >= 2.0.0 | MCP server framework |
| `aiohttp` >= 3.9.0 | WebSocket and HTTP client |
| `pydantic-settings` >= 2.0.0 | Environment-based configuration |
| `pyyaml` >= 6.0 | YAML parsing and formatting |
