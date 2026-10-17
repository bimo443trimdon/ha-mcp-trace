"""Connection-guide web UI, reachable only through Home Assistant ingress."""

import json
import os
from pathlib import Path

from aiohttp import web

INGRESS_PROXY_IP = "172.30.32.2"
WWW = Path("/www")


@web.middleware
async def ingress_only(request: web.Request, handler):
    if request.remote != INGRESS_PROXY_IP:
        raise web.HTTPForbidden(text="Open this page from the Home Assistant sidebar.")
    response = await handler(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


async def index(_request: web.Request) -> web.Response:
    return web.FileResponse(WWW / "index.html")


async def connection(_request: web.Request) -> web.Response:
    return web.Response(
        text=json.dumps({
            "api_key": os.environ["HA_MCP_API_KEY"],
            "port": int(os.environ.get("HA_MCP_PORT", "8099")),
            "read_only": os.environ.get("HA_MCP_READ_ONLY") == "true",
            "confirm_mode": os.environ.get("HA_MCP_CONFIRM_MODE", "client"),
            "device_control": os.environ.get("HA_MCP_ENABLE_DEVICE_CONTROL") == "true",
        }),
        content_type="application/json",
    )


app = web.Application(middlewares=[ingress_only])
app.router.add_get("/", index)
app.router.add_get("/connection.json", connection)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=8100, print=None, access_log=None)
