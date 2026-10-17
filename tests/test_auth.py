import asyncio
import socket

import httpx
import pytest
import uvicorn
from fastmcp import Client, FastMCP
from fastmcp.client.transports import StreamableHttpTransport

from ha_mcp.auth import ApiKeyVerifier

KEY = "test-key-123"
INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
}
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


async def test_verifier_rejects_wrong_and_empty_tokens():
    verifier = ApiKeyVerifier(KEY)
    assert await verifier.verify_token("") is None
    assert await verifier.verify_token("nope") is None
    assert (await verifier.verify_token(KEY)).client_id == "api-key"


@pytest.fixture
async def server_url():
    mcp = FastMCP("t", auth=ApiKeyVerifier(KEY))

    @mcp.tool()
    def ping() -> str:
        return "pong"

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(mcp.http_app(), host="127.0.0.1", port=port, log_level="error"))
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.02)
    yield f"http://127.0.0.1:{port}/mcp"
    server.should_exit = True
    await task


async def test_http_requires_api_key(server_url):
    async with httpx.AsyncClient() as client:
        assert (await client.post(server_url, json=INIT, headers=HEADERS)).status_code == 401
        wrong = {**HEADERS, "Authorization": "Bearer nope"}
        assert (await client.post(server_url, json=INIT, headers=wrong)).status_code == 401

    transport = StreamableHttpTransport(server_url, headers={"Authorization": f"Bearer {KEY}"})
    async with Client(transport) as client:
        assert [t.name for t in await client.list_tools()] == ["ping"]
