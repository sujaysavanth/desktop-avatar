"""Tiny CLI client to prove the stub server works — stands in for the avatar.

Type a message, hit enter, watch the server's state + reply come back. This is
how you verify the backend half of Phase 0 in isolation, before the Electron
shell exists.

Run (in a second terminal, with the stub already running):
    python -m server.test_client
"""

from __future__ import annotations

import asyncio
import json

import websockets

from core import config
from core.protocol import Query


async def main() -> None:
    uri = f"ws://{config.WS_HOST}:{config.WS_PORT}"
    print(f"connecting to {uri} ...")
    async with websockets.connect(uri) as ws:
        print("connected. type a message (or 'quit' to exit).\n")
        while True:
            text = await asyncio.to_thread(input, "you > ")
            if text.strip().lower() in {"quit", "exit"}:
                break

            # send a query that matches the locked contract
            msg = {"type": "query", "agent": "job", "text": text}
            await ws.send(json.dumps(msg))

            # the server sends: state(thinking) -> reply -> state(idle)
            # read frames until we've seen the reply
            while True:
                raw = await ws.recv()
                data = json.loads(raw)
                if data["type"] == "state":
                    print(f"    [state: {data['value']}]")
                elif data["type"] == "reply":
                    print(f"bot > {data['text']}")
                    # after reply we expect one more state(idle); grab it then stop
                    idle = json.loads(await ws.recv())
                    print(f"    [state: {idle['value']}]\n")
                    break


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, EOFError):
        print("\nbye")