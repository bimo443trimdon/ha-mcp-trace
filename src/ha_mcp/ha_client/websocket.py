"""Persistent WebSocket client for the Home Assistant WebSocket API."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from ha_mcp.ha_client.models import HAAuthError, HAConnectionError, HAConnectionLost

logger = logging.getLogger(__name__)


class HAWebSocketClient:
    """Async WebSocket client that maintains a persistent connection to Home Assistant.

    Features:
    - Automatic authentication on connect
    - Auto-incrementing message IDs with future-based response routing
    - Background listener task for incoming messages
    - Exponential-backoff reconnection on disconnect
    - Concurrency limiting via semaphore (max 10 in-flight commands)
    """

    def __init__(self, url: str, token: str) -> None:
        self.url = url
        self.token = token
        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._msg_id: int = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._subscriptions: dict[int, asyncio.Queue[dict[str, Any]]] = {}
        self._listener_task: asyncio.Task[None] | None = None
        self._connected: bool = False
        self._semaphore = asyncio.Semaphore(10)
        self._reconnect_delay: float = 1.0
        self._max_reconnect_delay: float = 60.0
        self._should_reconnect: bool = True

    # -- public API -----------------------------------------------------------

    async def connect(self) -> None:
        """Connect and authenticate to the HA WebSocket API.

        Raises:
            HAConnectionError: If the WebSocket connection cannot be established.
            HAAuthError: If authentication fails.
        """
        self._should_reconnect = True
        try:
            self._session = aiohttp.ClientSession()
            self._ws = await self._session.ws_connect(self.url)
        except Exception as exc:
            if self._session:
                await self._session.close()
                self._session = None
            raise HAConnectionError(
                f"Failed to connect to {self.url}: {exc}"
            ) from exc

        await self._authenticate()
        self._connected = True
        self._reconnect_delay = 1.0
        self._listener_task = asyncio.create_task(self._listener())
        logger.info("Connected to Home Assistant WebSocket API at %s", self.url)

    async def disconnect(self) -> None:
        """Gracefully disconnect from the WebSocket."""
        self._should_reconnect = False
        self._connected = False

        if self._listener_task is not None:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

        if self._ws is not None and not self._ws.closed:
            await self._ws.close()
            self._ws = None

        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

        # Cancel any pending futures so callers aren't stuck waiting.
        for future in self._pending.values():
            if not future.done():
                future.set_exception(
                    HAConnectionLost("WebSocket disconnected while awaiting response")
                )
        self._pending.clear()
        self._subscriptions.clear()

        logger.info("Disconnected from Home Assistant WebSocket API")

    async def send_command(
        self, msg_type: str, *, timeout: float = 30.0, **kwargs: Any
    ) -> dict[str, Any]:
        """Send a command and wait for the corresponding response.

        Args:
            msg_type: The HA WebSocket message type (e.g. ``"get_states"``).
            timeout: Maximum seconds to wait for a response (default 30).
            **kwargs: Additional key/value pairs merged into the outgoing message.

        Returns:
            The ``result`` payload from the HA response.

        Raises:
            HAConnectionError: If the client is not connected.
            HAConnectionLost: If the connection drops while waiting.
            asyncio.TimeoutError: If no response arrives within *timeout* seconds.
        """
        if not self._connected or self._ws is None or self._ws.closed:
            raise HAConnectionError("Not connected to Home Assistant")

        async with self._semaphore:
            self._msg_id += 1
            msg_id = self._msg_id

            loop = asyncio.get_running_loop()
            future: asyncio.Future[dict[str, Any]] = loop.create_future()
            self._pending[msg_id] = future

            message: dict[str, Any] = {**kwargs, "id": msg_id, "type": msg_type}

            try:
                await self._ws.send_json(message)
                logger.debug("Sent message id=%d type=%s", msg_id, msg_type)
            except Exception as exc:
                self._pending.pop(msg_id, None)
                raise HAConnectionLost(
                    f"Failed to send message: {exc}"
                ) from exc

            try:
                response = await asyncio.wait_for(future, timeout=timeout)
            except asyncio.TimeoutError:
                self._pending.pop(msg_id, None)
                raise
            except asyncio.CancelledError:
                self._pending.pop(msg_id, None)
                raise

            if not response.get("success", True):
                error = response.get("error", {})
                code = error.get("code", "unknown")
                error_message = error.get("message", "Unknown error")
                raise HAConnectionError(
                    f"Command {msg_type} failed [{code}]: {error_message}"
                )

            return response.get("result", response)

    async def subscribe(
        self, msg_type: str, *, timeout: float = 10.0, **kwargs: Any
    ) -> tuple[int, asyncio.Queue[dict[str, Any]]]:
        """Start an event subscription and return its id and an event queue.

        Sends a subscription command (e.g. ``subscribe_events`` or
        ``subscribe_trigger``), waits for the initial success acknowledgement,
        and returns ``(subscription_id, queue)``. Subsequent ``event`` messages
        carrying the same id are pushed onto *queue* by the background listener.

        The caller is responsible for calling :meth:`unsubscribe` when finished.

        Args:
            msg_type: The subscription command type.
            timeout: Maximum seconds to wait for the initial acknowledgement.
            **kwargs: Additional key/value pairs merged into the outgoing message.

        Returns:
            A ``(subscription_id, queue)`` tuple.

        Raises:
            HAConnectionError: If the client is not connected or the command fails.
            HAConnectionLost: If the connection drops while subscribing.
            asyncio.TimeoutError: If no acknowledgement arrives within *timeout*.
        """
        if not self._connected or self._ws is None or self._ws.closed:
            raise HAConnectionError("Not connected to Home Assistant")

        async with self._semaphore:
            # Increment and capture the id with no await in between so concurrent
            # callers can never collide on the same message id.
            self._msg_id += 1
            msg_id = self._msg_id

            loop = asyncio.get_running_loop()
            queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)
            future: asyncio.Future[dict[str, Any]] = loop.create_future()
            # Register the queue *before* sending so no event can be missed
            # between the ack and the first event.
            self._subscriptions[msg_id] = queue
            self._pending[msg_id] = future

            message: dict[str, Any] = {**kwargs, "id": msg_id, "type": msg_type}

            try:
                await self._ws.send_json(message)
                logger.debug("Sent subscription id=%d type=%s", msg_id, msg_type)
            except Exception as exc:
                self._pending.pop(msg_id, None)
                self._subscriptions.pop(msg_id, None)
                raise HAConnectionLost(f"Failed to send subscription: {exc}") from exc

            try:
                response = await asyncio.wait_for(future, timeout=timeout)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._pending.pop(msg_id, None)
                self._subscriptions.pop(msg_id, None)
                raise

            if not response.get("success", True):
                self._subscriptions.pop(msg_id, None)
                error = response.get("error", {})
                code = error.get("code", "unknown")
                error_message = error.get("message", "Unknown error")
                raise HAConnectionError(
                    f"Subscription {msg_type} failed [{code}]: {error_message}"
                )

            return msg_id, queue

    async def unsubscribe(self, subscription_id: int) -> None:
        """Stop an active subscription.

        Tolerant of failure: a reconnect may already have dropped the
        server-side subscription, so errors here are logged and swallowed.
        """
        self._subscriptions.pop(subscription_id, None)
        try:
            await self.send_command(
                "unsubscribe_events", subscription=subscription_id
            )
        except Exception as exc:  # noqa: BLE001 - best effort cleanup
            logger.debug("unsubscribe(%d) ignored error: %s", subscription_id, exc)

    @property
    def connected(self) -> bool:  # noqa: D401
        """Whether the client currently has an active connection."""
        return self._connected

    # -- internals ------------------------------------------------------------

    async def _authenticate(self) -> None:
        """Perform the auth handshake after connecting.

        Expects:
            1. Receive ``auth_required``
            2. Send ``{"type": "auth", "access_token": ...}``
            3. Receive ``auth_ok`` or ``auth_invalid``
        """
        assert self._ws is not None  # noqa: S101

        # Step 1: receive auth_required
        auth_required = await self._ws.receive_json()
        if auth_required.get("type") != "auth_required":
            raise HAConnectionError(
                f"Expected auth_required but got: {auth_required.get('type')}"
            )

        # Step 2: send auth
        await self._ws.send_json({"type": "auth", "access_token": self.token})

        # Step 3: receive auth result
        auth_result = await self._ws.receive_json()
        result_type = auth_result.get("type")
        if result_type == "auth_ok":
            logger.debug("Authentication successful")
            return
        if result_type == "auth_invalid":
            message = auth_result.get("message", "Invalid access token")
            raise HAAuthError(f"Authentication failed: {message}")

        raise HAConnectionError(
            f"Unexpected auth response type: {result_type}"
        )

    async def _listener(self) -> None:
        """Background task: read incoming messages and route them to pending futures."""
        assert self._ws is not None  # noqa: S101
        try:
            async for raw_msg in self._ws:
                if raw_msg.type == aiohttp.WSMsgType.TEXT:
                    msg: dict[str, Any] = raw_msg.json()
                    msg_id = msg.get("id")
                    if msg_id is not None and msg_id in self._pending:
                        future = self._pending.pop(msg_id)
                        if not future.done():
                            future.set_result(msg)
                    elif msg.get("type") == "event" and msg_id in self._subscriptions:
                        try:
                            self._subscriptions[msg_id].put_nowait(msg.get("event", {}))
                        except asyncio.QueueFull:
                            logger.debug("Dropping event for subscription id=%s (queue full)", msg_id)
                    elif msg.get("type") == "event":
                        logger.debug(
                            "Unhandled event for id=%s: %s",
                            msg_id,
                            msg.get("event", {}).get("event_type"),
                        )
                    else:
                        logger.debug("Unhandled message: %s", msg)
                elif raw_msg.type in (
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.CLOSING,
                    aiohttp.WSMsgType.CLOSE,
                ):
                    logger.warning("WebSocket closed by server")
                    break
                elif raw_msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(
                        "WebSocket error: %s",
                        self._ws.exception() if self._ws else "unknown",
                    )
                    break
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Listener encountered an unexpected error")

        # If we reach here the connection dropped.
        self._connected = False

        # Fail all pending futures so callers don't hang.
        for future in self._pending.values():
            if not future.done():
                future.set_exception(
                    HAConnectionLost("Connection lost while awaiting response")
                )
        self._pending.clear()
        self._subscriptions.clear()

        if self._should_reconnect:
            await self._reconnect()

    async def _reconnect(self) -> None:
        """Attempt to reconnect with exponential backoff."""
        while self._should_reconnect:
            logger.info(
                "Attempting reconnect in %.1f seconds...", self._reconnect_delay
            )
            await asyncio.sleep(self._reconnect_delay)

            # Clean up old session / ws
            if self._ws is not None and not self._ws.closed:
                await self._ws.close()
            if self._session is not None and not self._session.closed:
                await self._session.close()
            self._ws = None
            self._session = None

            try:
                self._session = aiohttp.ClientSession()
                self._ws = await self._session.ws_connect(self.url)
                await self._authenticate()
                self._connected = True
                self._reconnect_delay = 1.0
                logger.info("Reconnected to Home Assistant WebSocket API")
                # Restart the listener loop (we're already inside the old
                # listener task, so just call _listener recursively-ish via a
                # new task and return).
                self._listener_task = asyncio.create_task(self._listener())
                return
            except Exception:
                logger.exception("Reconnection attempt failed")
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, self._max_reconnect_delay
                )
                # Clean up the failed attempt
                if self._ws is not None and not self._ws.closed:
                    await self._ws.close()
                if self._session is not None and not self._session.closed:
                    await self._session.close()
                self._ws = None
                self._session = None

        logger.info("Reconnection stopped (should_reconnect is False)")
