#!/usr/bin/env bash
set -euo pipefail

# s6-overlay stores the container environment as files instead of shell env vars.
if [ -f /run/s6/container_environment/SUPERVISOR_TOKEN ]; then
    SUPERVISOR_TOKEN="$(cat /run/s6/container_environment/SUPERVISOR_TOKEN)"
fi

if [ -z "${SUPERVISOR_TOKEN:-}" ]; then
    echo "[FATAL] SUPERVISOR_TOKEN not available. Ensure homeassistant_api is enabled in config.yaml."
    exit 1
fi

option() {
    python3 - "$1" "$2" <<'PY'
import json, sys
value = json.load(open("/data/options.json")).get(sys.argv[1], sys.argv[2])
print(str(value).lower() if isinstance(value, bool) else value)
PY
}

KEY_FILE=/data/api_key
API_KEY="$(option api_key '')"
if [ -z "${API_KEY}" ]; then
    if [ ! -s "${KEY_FILE}" ]; then
        (umask 077 && python3 -c "import secrets; print(secrets.token_urlsafe(32))" > "${KEY_FILE}")
        echo "[INFO] Generated a new API key. Open the MCP Server panel to copy it."
    fi
    API_KEY="$(cat "${KEY_FILE}")"
fi

export HA_MCP_HA_URL="http://supervisor/core"
export HA_MCP_HA_TOKEN="${SUPERVISOR_TOKEN}"
export HA_MCP_TRANSPORT="http"
export HA_MCP_HOST="0.0.0.0"
export HA_MCP_PORT=8099
export HA_MCP_API_KEY="${API_KEY}"
export HA_MCP_LOG_LEVEL="$(option log_level INFO)"
export HA_MCP_CONFIRM_MODE="$(option confirm_mode client)"
export HA_MCP_READ_ONLY="$(option read_only false)"
export HA_MCP_ENABLE_DEVICE_CONTROL="$(option enable_device_control false)"

echo "[INFO] Starting Home Assistant MCP Server (confirm_mode=${HA_MCP_CONFIRM_MODE}, read_only=${HA_MCP_READ_ONLY}, device_control=${HA_MCP_ENABLE_DEVICE_CONTROL})"

python3 /guide_server.py &

exec python3 -m ha_mcp
