# Configuration

## Home Assistant add-on

The add-on authenticates to Home Assistant automatically through the
Supervisor token. MCP clients authenticate to the add-on with an API key.

| Option | Default | Description |
|---|---|---|
| `api_key` | *(empty)* | Bearer token clients must send. Leave empty to use an auto-generated key, stored in `/data/api_key` and shown in the **MCP Server** panel. Set a value to override it or to rotate the key. |
| `confirm_mode` | `client` | How changes are confirmed. See [Confirmation](#confirmation). |
| `read_only` | `false` | Only expose tools that read configuration. |
| `enable_device_control` | `false` | Expose the generic `call_service` tool. |
| `log_level` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR`. |

The `transport` option from 0.1.x has been removed; the add-on always
uses streamable HTTP.

The MCP endpoint is `http://<ha-host>:8099/mcp` (no trailing slash). You
can change the host port in the add-on's **Network** panel. Open the
**MCP Server** panel in the sidebar for copy-paste snippets that already
contain your host and API key. That panel is only reachable through
Home Assistant ingress, so only HA admins can see the key.

## pip install (environment variables)

All settings use the `HA_MCP_` prefix.

| Variable | Default | Description |
|---|---|---|
| `HA_MCP_HA_URL` | `http://homeassistant.local:8123` | Home Assistant base URL. The WebSocket URL is derived from it (`ws://` or `wss://` + `/api/websocket`). |
| `HA_MCP_HA_TOKEN` | *(required)* | Long-lived access token (HA profile > Security). |
| `HA_MCP_TRANSPORT` | `stdio` | `stdio`, `http` or `sse`. |
| `HA_MCP_HOST` | `127.0.0.1` | Bind address for `http`/`sse`. Use `0.0.0.0` only if other machines must connect. |
| `HA_MCP_PORT` | `8099` | Port for `http`/`sse`. |
| `HA_MCP_API_KEY` | *(empty)* | Required for `http`/`sse`. Clients send it as `Authorization: Bearer <key>`. |
| `HA_MCP_ALLOW_UNAUTHENTICATED` | `false` | Start `http`/`sse` without an API key. Only for a trusted loopback setup. |
| `HA_MCP_CONFIRM_MODE` | `client` | `client` or `elicit`. See below. |
| `HA_MCP_READ_ONLY` | `false` | Only register read-only tools. |
| `HA_MCP_ENABLE_DEVICE_CONTROL` | `false` | Register `call_service`. |
| `HA_MCP_LOG_LEVEL` | `INFO` | Logging level. |

The server refuses to start on `http`/`sse` without `HA_MCP_API_KEY`
unless `HA_MCP_ALLOW_UNAUTHENTICATED=true`. Anyone who can reach the
port would otherwise get admin access to Home Assistant.

Generate a key with:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Confirmation

Confirmation is a server setting. Tools have no `skip_confirm` argument,
so the model cannot bypass it.

- **`client`** (default) -- the server applies changes directly and
  relies on your AI client's own tool-approval prompt. Clients see MCP
  annotations (`readOnlyHint`, `destructiveHint`), so you can
  auto-approve read-only tools and keep prompts for the rest.
- **`elicit`** -- the server shows a YAML preview and asks for
  confirmation itself via MCP elicitation. Clients that can't answer
  elicitation get an error instead of a silent change. Elicitation is
  not available on connections using the 2026-07-28 MCP protocol
  revision, so most current clients need `client` mode.

In both modes, read-only mode blocks every change, and a failed
automation/script validation blocks the save.

## Device control

`call_service` is off by default because this server is for setting
Home Assistant up, not operating it. Even when enabled, these are always
blocked: the `shell_command`, `python_script`, `pyscript`, `hassio` and
`command_line` domains, plus `homeassistant.stop`/`restart`,
`recorder.purge`/`purge_entities`/`disable` and `backup.create`/
`create_automatic`. Use `restart_home_assistant` and `create_backup`
instead.

## Client setup

Replace the host and `<API_KEY>`. The add-on's **MCP Server** panel
generates these for you.

### Claude Code

Available in every project:

```bash
claude mcp add --transport http --scope user home-assistant http://homeassistant.local:8099/mcp \
  --header "Authorization: Bearer <API_KEY>"
```

Or for one project, in `.mcp.json` at the project root. Export
`HA_MCP_API_KEY` in your shell to keep the key out of git:

```json
{
  "mcpServers": {
    "home-assistant": {
      "type": "http",
      "url": "http://homeassistant.local:8099/mcp",
      "headers": {
        "Authorization": "Bearer ${HA_MCP_API_KEY}"
      }
    }
  }
}
```

Check with `claude mcp list`.

### Claude Desktop

Requires Node.js. In Settings > Developer > Edit Config, merge this into
`claude_desktop_config.json`, then fully restart Claude Desktop:

```json
{
  "mcpServers": {
    "home-assistant": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "http://homeassistant.local:8099/mcp",
        "--allow-http",
        "--header",
        "Authorization:${AUTH_HEADER}"
      ],
      "env": {
        "AUTH_HEADER": "Bearer <API_KEY>"
      }
    }
  }
}
```

The header is passed through an env var because a space inside `args`
gets split on some platforms. Custom connectors (Settings > Connectors)
won't work: they connect from Anthropic's cloud and can't reach a server
on your home network.

### Cursor

`~/.cursor/mcp.json` (global) or `.cursor/mcp.json` (project):

```json
{
  "mcpServers": {
    "home-assistant": {
      "url": "http://homeassistant.local:8099/mcp",
      "headers": { "Authorization": "Bearer <API_KEY>" }
    }
  }
}
```

### VS Code

`.vscode/mcp.json`:

```json
{
  "servers": {
    "home-assistant": {
      "type": "http",
      "url": "http://homeassistant.local:8099/mcp",
      "headers": { "Authorization": "Bearer <API_KEY>" }
    }
  }
}
```

### Other clients

Any client with Streamable HTTP support: connect to
`http://<host>:8099/mcp` and send `Authorization: Bearer <API_KEY>`.

### pip install, stdio

With stdio the client launches the server itself, so no API key is
needed:

```json
{
  "mcpServers": {
    "home-assistant": {
      "command": "ha-mcp",
      "env": {
        "HA_MCP_HA_URL": "http://homeassistant.local:8123",
        "HA_MCP_HA_TOKEN": "<long-lived-access-token>"
      }
    }
  }
}
```

## Network security

The connection is plain HTTP. Use it only on a network you trust, or put
it behind a VPN or a reverse proxy with HTTPS. Never forward port 8099
directly to the internet.
