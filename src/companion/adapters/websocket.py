"""Optional localhost WebSocket producer, isolated from the runtime core."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from ..protocol import ProtocolError, validate_event
from ..queue import append_jsonl


async def serve(inbox: Path, *, host: str = "127.0.0.1", port: int = 8765) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("websocket adapter only permits loopback hosts")
    try:
        from websockets.asyncio.server import serve as websocket_serve
    except ImportError as exc:
        raise RuntimeError("WebSocket support requires: pip install 'open-agent-companion[websocket]'") from exc

    async def handler(connection: Any) -> None:
        async for raw in connection:
            try:
                event = validate_event(json.loads(raw))
                append_jsonl(inbox, event)
                await connection.send(json.dumps({"status": "queued", "event_id": event["id"]}))
            except (json.JSONDecodeError, ProtocolError) as exc:
                await connection.send(json.dumps({"status": "error", "error": str(exc)}))

    async with websocket_serve(handler, host, port):
        await asyncio.Future()
