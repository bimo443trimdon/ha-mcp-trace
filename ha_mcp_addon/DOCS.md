# Home Assistant MCP Server

This add-on runs an MCP (Model Context Protocol) server that lets AI
assistants such as Claude Code and Claude Desktop set up and maintain
your Home Assistant: add integrations, organise devices and entities,
and build automations, scripts, scenes, helpers and dashboards. It can
also fix repairs, debug automation traces and manage backups.

## Getting started

1. Start the add-on.
2. Open the **MCP Server** panel in the sidebar (or **OPEN WEB UI** on
   the add-on page).
3. Pick your client and copy the snippet. It already contains your
   host, port and API key.

The MCP endpoint is `http://<your-ha-host>:8099/mcp`. Every request must
carry `Authorization: Bearer <API_KEY>`.

## Configuration

| Option | Default | Description |
|---|---|---|
| `api_key` | *(empty)* | Leave empty to use the auto-generated key shown in the panel. Enter your own value to override or rotate it, then restart. |
| `confirm_mode` | `client` | `client`: rely on your AI client's tool-approval prompt. `elicit`: the server asks for confirmation itself (only for clients that support MCP elicitation). |
| `read_only` | `false` | Only expose tools that read configuration. |
| `enable_device_control` | `false` | Expose the generic `call_service` tool for turning devices on/off. |
| `log_level` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR`. |

The 0.1.x `transport` option is gone; the add-on always uses streamable
HTTP. You can change the host port in the **Network** panel.

## Connecting clients

### Claude Code

```bash
claude mcp add --transport http --scope user home-assistant http://homeassistant.local:8099/mcp \
  --header "Authorization: Bearer <API_KEY>"
```

For a single project, add this to `.mcp.json` and export
`HA_MCP_API_KEY` in your shell:

```json
{
  "mcpServers": {
    "home-assistant": {
      "type": "http",
      "url": "http://homeassistant.local:8099/mcp",
      "headers": { "Authorization": "Bearer ${HA_MCP_API_KEY}" }
    }
  }
}
```

### Claude Desktop

Requires Node.js. Merge this into `claude_desktop_config.json`
(Settings > Developer > Edit Config), then fully restart Claude Desktop:

```json
{
  "mcpServers": {
    "home-assistant": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://homeassistant.local:8099/mcp",
               "--allow-http", "--header", "Authorization:${AUTH_HEADER}"],
      "env": { "AUTH_HEADER": "Bearer <API_KEY>" }
    }
  }
}
```

Custom connectors (Settings > Connectors) can't be used: they connect
from Anthropic's cloud and can't reach your home network.

### Cursor, VS Code and others

The **MCP Server** panel has snippets for these too. Any client with
Streamable HTTP support works with the endpoint and header above.

## Security

- Anyone with the API key and network access to port 8099 has full
  admin access to Home Assistant. Treat the key like a password.
- The connection is plain HTTP. Use it on a trusted network, or put it
  behind a VPN or an HTTPS reverse proxy. Don't forward port 8099 to
  the internet.
- The panel showing the key is only reachable through Home Assistant
  ingress, which requires an admin login.
- Shell/Python execution, Supervisor services, stop/restart and recorder
  purge are always blocked in `call_service`.

## Troubleshooting

- **401 Unauthorized** -- the client isn't sending the header, or the
  key changed. Copy a fresh snippet from the panel.
- **Can't connect** -- check the add-on is running and port 8099 is
  mapped in **Network**. Try the IP address instead of
  `homeassistant.local`. Use `/mcp`, not `/mcp/`.
- **"requires an in-client confirmation"** -- `confirm_mode` is `elicit`
  but your client can't show the prompt. Switch to `client`.
- **A tool isn't listed** -- `read_only` hides all write tools, and
  `call_service` needs `enable_device_control`.

## Status

Tools added in 0.2.0 (config flows, registry removal, categories,
diagnostics, backup configuration, `counter`/`timer`/`schedule` helpers)
are not yet verified against a live Home Assistant. Please report
issues on GitHub.
