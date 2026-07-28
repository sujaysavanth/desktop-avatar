"""Phase 0 stub echo server.

The fake brain. Two halves:

  * Reactive — accepts a `query`, emits `state: thinking`, waits a beat to
    simulate work, echoes the text back as a `reply`, then returns to
    `state: idle`.
  * Proactive — a per-connection nudger that every so often pushes an `intent`
    so the roaming avatar has something to be autonomous *about*. It picks the
    intent from whatever app currently has focus (sent by the avatar as
    `context`). Canned lines, no LLM — this exists purely to prove that the
    unsolicited-push direction of the wire works before Ollama is involved.

In Phase 1 this file gets replaced by a real handler that calls Ollama, but the
message shapes it sends stay identical, so the avatar never has to change.

Run:  python -m server.stub      (from the backend/ directory)
"""

from __future__ import annotations

import asyncio
import json
import random

import websockets
from websockets.asyncio.server import ServerConnection, serve

from core import config
from core.protocol import AgentState, Context, IntentAction, Query, intent, reply, state

# How long between proactive nudges. Wide and random on purpose: a pet on a
# fixed timer reads as a cron job.
NUDGE_MIN_S = 35
NUDGE_MAX_S = 90

# Canned reactions per focused app. `None` key is the fallback.
NUDGES: dict[str | None, list[tuple[IntentAction, str | None]]] = {
    "code": [
        (IntentAction.APPROACH, "still on that file? want me to look at it?"),
        (IntentAction.IDLE, None),
        (IntentAction.PEEK, "i'll stay out of the way."),
    ],
    "chrome": [
        (IntentAction.WANDER, None),
        (IntentAction.APPROACH, "job hunting? point me at a posting."),
    ],
    None: [
        (IntentAction.WANDER, None),
        (IntentAction.WANDER, None),
        (IntentAction.PEEK, None),
        (IntentAction.SLEEP, "nothing going on. napping."),
        (IntentAction.APPROACH, "hey — need anything?"),
    ],
}


def _pick_nudge(app: str) -> tuple[IntentAction, str | None]:
    key = next((k for k in NUDGES if k and k in app.lower()), None)
    return random.choice(NUDGES[key])


async def handle(ws: ServerConnection) -> None:
    """One connection. Reads messages forever until the client disconnects."""
    print(f"[stub] client connected: {ws.remote_address}")

    # Per-connection mutable context the nudger reads from.
    ctx = Context(app="", title="")
    nudger = asyncio.create_task(_nudge_loop(ws, ctx))

    try:
        async for raw in ws:
            await _handle_message(ws, raw, ctx)
    except websockets.ConnectionClosed:
        print("[stub] client disconnected")
    finally:
        nudger.cancel()


async def _nudge_loop(ws: ServerConnection, ctx: Context) -> None:
    """Push an unsolicited `intent` now and then. Cancelled on disconnect."""
    try:
        while True:
            await asyncio.sleep(random.uniform(NUDGE_MIN_S, NUDGE_MAX_S))
            action, text = _pick_nudge(ctx.app)
            print(f"[stub] nudge -> {action.value} (focus: {ctx.app or 'unknown'})")
            await ws.send(json.dumps(intent(action, text)))
    except (asyncio.CancelledError, websockets.ConnectionClosed):
        pass


async def _handle_message(ws: ServerConnection, raw: str, ctx: Context) -> None:
    # Parse defensively — a malformed message shouldn't kill the connection.
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        print(f"[stub] ignoring non-JSON: {raw!r}")
        return

    kind = data.get("type")

    if kind == "context":
        incoming = Context.from_dict(data)
        ctx.app, ctx.title = incoming.app, incoming.title
        # Titles are truncated on purpose: they routinely contain email subject
        # lines and document names, and this print lands in terminal scrollback.
        # ASCII-only separator — a Windows console in cp1252 mangles an em-dash.
        shown = ctx.title if len(ctx.title) <= 40 else ctx.title[:37] + "..."
        print(f"[stub] focus: {ctx.app} | {shown!r}")
        return

    if kind != "query":
        print(f"[stub] ignoring unknown type: {kind!r}")
        return

    query = Query.from_dict(data)
    print(f"[stub] query from '{query.agent}': {query.text!r}")

    # 1) tell the avatar we're working
    await ws.send(json.dumps(state(AgentState.THINKING)))

    # 2) simulate a moment of thought
    await asyncio.sleep(0.8)

    # 3) the canned "reply" — echoes, tagged with the agent, and mentions the
    #    focused app when we know it, to prove context actually arrived
    echo = f"[{query.agent}] you said: {query.text}"
    if ctx.app:
        echo += f"  (you're in {ctx.app})"
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
