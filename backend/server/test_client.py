"""Tiny CLI client — stands in for the avatar so you can test the backend alone.

Type a message, watch state transitions and the reply stream in. This is how you
verify the backend half without launching Electron, which matters more now that
replies are generated: a broken prompt or a stalled model is much easier to see
here than through a speech bubble.

Understands the full contract: `reply`, `reply_chunk`/`reply_end`, `state`, and
unsolicited `intent` pushes.

Commands:
    /focus <app> [title]   fake a focused-app change (sends `context`)
    quit                   exit

Run (in a second terminal, with a server already running):
    python -m server.test_client
"""

from __future__ import annotations

import asyncio
import json

import websockets

from core import config


async def pump(ws: websockets.ClientConnection, done: asyncio.Event) -> None:
    """Print everything the server sends, until it says it's idle again."""
    streaming = False
    async for raw in ws:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            print(f"\n[?] non-JSON: {raw!r}")
            continue

        kind = msg.get("type")

        if kind == "reply_chunk":
            if not streaming:
                streaming = True
                print("bot > ", end="", flush=True)
            print(msg["text"], end="", flush=True)

        elif kind == "reply_end":
            if streaming:
                print()  # close the streamed line
                streaming = False

        elif kind == "reply":
            if streaming:
                print()
                streaming = False
            print(f"bot > {msg['text']}")

        elif kind == "state":
            print(f"    [state: {msg['value']}]")
            if msg["value"] == "idle":
                done.set()

        elif kind == "intent":
            extra = f" — {msg['text']!r}" if msg.get("text") else ""
            print(f"    [intent: {msg['action']}{extra}]")

        else:
            print(f"    [? {kind}]")


async def main() -> None:
    uri = f"ws://{config.WS_HOST}:{config.WS_PORT}"
    print(f"connecting to {uri} ...")

    async with websockets.connect(uri) as ws:
        print("connected. type a message, '/focus <app>', or 'quit'.\n")
        done = asyncio.Event()
        reader = asyncio.create_task(pump(ws, done))

        try:
            while True:
                text = await asyncio.to_thread(input, "you > ")
                text = text.strip()
                if not text:
                    continue
                if text.lower() in {"quit", "exit"}:
                    break

                if text.startswith("/focus"):
                    parts = text.split(maxsplit=2)
                    app = parts[1] if len(parts) > 1 else ""
                    title = parts[2] if len(parts) > 2 else ""
                    await ws.send(json.dumps({"type": "context", "app": app, "title": title}))
                    print(f"    [sent context: {app!r} {title!r}]")
                    continue

                done.clear()
                await ws.send(json.dumps({"type": "query", "agent": "job", "text": text}))
                # Wait for the server to settle back to idle before prompting.
                await done.wait()
                print()
        finally:
            reader.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, EOFError):
        print("\nbye")
