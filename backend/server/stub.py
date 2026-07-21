"""Phase 0 stub echo server.

The fake brain. It accepts a `query`, emits a `state: thinking`, waits a beat to
simulate work, echoes the text back as a `reply`, then returns to `state: idle`.
No LLM, no tools — this exists purely to prove the websocket loop end to end.

In Phase 1 this file gets replaced by a real handler that calls Ollama, but the
message shapes it sends stay identical, so the avatar never has to change.

Run:  python -m server.stub      (from the backend/ directory)
"""

from __future__ import annotations

import asyncio
import json

import websockets
from websockets.asyncio.server import ServerConnection, serve

from core import config
from core.protocol import AgentState, Query, reply, state


async def handle(ws: ServerConnection) -> None:
    """One connection. Reads messages forever until the client disconnects."""
    print(f"[stub] client connected: {ws.remote_address}")
    try:
        async for raw in ws:
            await _handle_message(ws, raw)
    except websockets.ConnectionClosed:
        print("[stub] client disconnected")


async def _handle_message(ws: ServerConnection, raw: str) -> None:
    # Parse defensively — a malformed message shouldn't kill the connection.
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print(f"[stub] ignoring non-JSON: {raw!r}")
        return

    if data.get("type") != "query":
        print(f"[stub] ignoring non-query: {data.get('type')!r}")
        return

    query = Query.from_dict(data)
    print(f"[stub] query from '{query.agent}': {query.text!r}")

    # 1) tell the avatar we're working
    await ws.send(json.dumps(state(AgentState.THINKING)))

    # 2) simulate a moment of thought
    await asyncio.sleep(0.8)

    # 3) the canned "reply" — just echoes, tagged with the agent
    echo = f"[{query.agent}] you said: {query.text}"
    await ws.send(json.dumps(reply(echo)))

    # 4) back to resting
    await ws.send(json.dumps(state(AgentState.IDLE)))


async def main() -> None:
    print(f"[stub] listening on ws://{config.WS_HOST}:{config.WS_PORT}")
    async with serve(handle, config.WS_HOST, config.WS_PORT):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[stub] shutting down")