"""Phase 1 server — the real brain.

Same websocket contract the stub honors, so the avatar needs no changes beyond
understanding streamed replies. What's different from `stub.py`:

  * queries go to a local model via Ollama and stream back token by token
  * proactive nudges are generated from what you actually have in focus, instead
    of drawn from a canned list
  * one shared LLM across all connections, because there is one GPU

Design note on failure: Ollama being down is a normal condition on a laptop, not
an exception to crash on. Every path that can fail ends with the avatar saying
something and going back to `idle`, never sitting on `thinking` forever.

Run:  python -m server.app      (from the backend/ directory)
"""

from __future__ import annotations

import asyncio
import json
import random

import websockets
from websockets.asyncio.server import ServerConnection, serve

from core import config
from core.protocol import (
    AgentState,
    Context,
    IntentAction,
    Query,
    intent,
    reply,
    reply_chunk,
    reply_end,
    state,
)
from llm import LLM, OllamaUnavailable
from llm import prompts
from tools import ScreenBlocked, ScreenReader, ScreenUnavailable
from tools import screen as screen_tool

# Proactive nudges. Wide and random so it doesn't read as a cron job.
NUDGE_MIN_S = 90
NUDGE_MAX_S = 240

# Where she goes when she speaks up unprompted. The LLM writes the line; the
# movement stays deterministic — the model never drives a frame.
NUDGE_ACTIONS = [
    IntentAction.APPROACH,
    IntentAction.APPROACH,
    IntentAction.WANDER,
    IntentAction.PEEK,
]


class Session:
    """One connected avatar: its history, its focus context, its nudger."""

    def __init__(self, ws: ServerConnection, llm: LLM, screen: ScreenReader | None = None) -> None:
        self.ws = ws
        self.llm = llm
        self.screen = screen
        self.ctx = Context(app="", title="")
        self.history: list[dict] = []

    async def send(self, msg: dict) -> None:
        await self.ws.send(json.dumps(msg))

    # ------------------------------------------------------------- messages --

    def _build_messages(self, agent: str, user_text: str) -> list[dict]:
        msgs: list[dict] = [{"role": "system", "content": prompts.system_prompt(agent)}]

        # Focus is a separate system message so it can be refreshed every turn
        # without rebuilding the personality block.
        if note := prompts.focus_note(self.ctx.app, self.ctx.title):
            msgs.append({"role": "system", "content": note})

        msgs.extend(self.history)
        msgs.append({"role": "user", "content": user_text})
        return msgs

    # ------------------------------------------------------------------ tools --

    def tools_spec(self) -> list[dict] | None:
        """The tool list for this turn, or None if tools can't be used at all."""
        if not (self.screen and self.screen.running and self.llm.tools_supported):
            return None
        return [screen_tool.TOOL_SPEC]

    async def run_tool_calls(self, calls: list[dict]) -> list[dict]:
        """Execute tool calls and return `tool` role messages for the next round.

        Every failure path returns a message rather than raising: the model needs
        to be *told* it couldn't look, so it can say so, instead of the whole turn
        collapsing into a generic error.
        """
        out: list[dict] = []
        for call in calls:
            name = call.get("function", {}).get("name", "")
            if name != "read_screen":
                print(f"[app] model asked for unknown tool {name!r}")
                out.append({"role": "tool", "content": f"No such tool: {name}."})
                continue

            try:
                snap = await self.screen.read()
                where = f"{snap.get('app')} | {(snap.get('title') or '')[:40]}"
                if snap.get("blocked"):
                    print(f"[app] read_screen REFUSED ({where}): {snap['blocked']}")
                else:
                    print(
                        f"[app] read_screen ok ({where}) "
                        f"{len(snap.get('ocr') or '')} chars in {snap.get('ocr_ms')}ms"
                    )
                out.append({"role": "tool", "content": ScreenReader.to_prompt(snap)})

            except ScreenBlocked as err:
                print(f"[app] read_screen blocked: {err}")
                out.append({
                    "role": "tool",
                    "content": f"Screen reading refused: {err}. Tell the user plainly.",
                })
            except ScreenUnavailable as err:
                print(f"[app] read_screen unavailable: {err}")
                out.append({
                    "role": "tool",
                    "content": "Screen reading is not working right now. Say so and answer without it.",
                })
        return out

    def _remember(self, user_text: str, assistant_text: str) -> None:
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": assistant_text})
        # Crude window; Phase 2 replaces it with retrieval.
        limit = config.LLM_HISTORY_TURNS * 2
        if len(self.history) > limit:
            del self.history[: len(self.history) - limit]

    # ---------------------------------------------------------------- query --

    async def handle_query(self, query: Query) -> None:
        print(f"[app] query from '{query.agent}': {query.text!r}")
        await self.send(state(AgentState.THINKING))

        collected: list[str] = []
        started = False
        messages = self._build_messages(query.agent, query.text)
        tools = self.tools_spec()

        try:
            # One tool round at most. A desk pet that can chain tool calls can
            # also loop on them, and there's exactly one tool to call.
            for round_index in range(2):
                calls: list[dict] = []

                async for ev in self.llm.stream_events(messages, tools if round_index == 0 else None):
                    if ev["type"] == "tool_calls":
                        calls.extend(ev["calls"])
                    elif ev["type"] == "text":
                        started = True
                        collected.append(ev["text"])
                        await self.send(reply_chunk(ev["text"]))

                if not calls:
                    break

                # The model wants to look at the screen. Tell the avatar, because
                # this is the one moment the human should know it's watching.
                await self.send(state(AgentState.NEEDS_YOU))
                results = await self.run_tool_calls(calls)
                await self.send(state(AgentState.THINKING))

                messages = messages + [{"role": "assistant", "content": "", "tool_calls": calls}]
                messages.extend(results)

        except OllamaUnavailable as err:
            print(f"[app] llm unavailable: {err}")
            # If we'd already opened a bubble, close it before explaining.
            if started:
                await self.send(reply_end())
            await self.send(
                reply("my brain isn't running right now — is ollama started?")
            )
            await self.send(state(AgentState.IDLE))
            return

        except websockets.ConnectionClosed:
            raise  # the avatar went away; nothing to send

        if started:
            await self.send(reply_end())

        text = "".join(collected).strip()
        if text:
            self._remember(query.text, text)
        else:
            # Model returned nothing at all — say *something* rather than stare.
            await self.send(reply("...i lost my train of thought. ask again?"))

        await self.send(state(AgentState.IDLE))

    # -------------------------------------------------------------- context --

    def handle_context(self, data: dict) -> None:
        incoming = Context.from_dict(data)
        self.ctx.app, self.ctx.title = incoming.app, incoming.title
        # Truncated on purpose: window titles routinely contain email subject
        # lines and document names, and this print lands in terminal scrollback.
        shown = self.ctx.title if len(self.ctx.title) <= 40 else self.ctx.title[:37] + "..."
        print(f"[app] focus: {self.ctx.app} | {shown!r}")

    # --------------------------------------------------------------- nudges --

    async def nudge_loop(self) -> None:
        """Occasionally speak up unprompted. Cancelled on disconnect."""
        try:
            while True:
                await asyncio.sleep(random.uniform(NUDGE_MIN_S, NUDGE_MAX_S))
                await self._nudge_once()
        except (asyncio.CancelledError, websockets.ConnectionClosed):
            pass

    async def _nudge_once(self) -> None:
        action = random.choice(NUDGE_ACTIONS)

        # No focus info yet, or the GPU is busy with a real query? Still move —
        # she just does it without a comment. Roaming never depends on the LLM.
        line = None
        if self.ctx.app:
            line = await self._generate_nudge_line()

        print(f"[app] nudge -> {action.value}" + (f" {line!r}" if line else " (silent)"))
        await self.send(intent(action, line))

    async def _generate_nudge_line(self) -> str | None:
        msgs = [
            {"role": "system", "content": prompts.NUDGE},
            {"role": "system", "content": prompts.focus_note(self.ctx.app, self.ctx.title)},
            {"role": "user", "content": "Say your one sentence now."},
        ]

        # try_stream yields None when the GPU is in use — a nudge should be
        # skipped, never queued ahead of the human.
        stream = await self.llm.try_stream(msgs)
        if stream is None:
            return None

        try:
            pieces = [p async for p in stream]
        except OllamaUnavailable as err:
            print(f"[app] nudge skipped, llm unavailable: {err}")
            return None

        line = "".join(pieces).strip().strip('"')
        # One sentence, and short enough for the bubble. The model will
        # occasionally ignore both instructions.
        if len(line) > 160:
            line = line[:157].rstrip() + "..."
        return line or None


# ------------------------------------------------------------------ plumbing --


async def handle(ws: ServerConnection, llm: LLM, screen: ScreenReader | None) -> None:
    print(f"[app] client connected: {ws.remote_address}")
    session = Session(ws, llm, screen)
    nudger = asyncio.create_task(session.nudge_loop())

    try:
        async for raw in ws:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                print(f"[app] ignoring non-JSON: {raw!r}")
                continue

            kind = data.get("type")
            if kind == "context":
                session.handle_context(data)
            elif kind == "query":
                await session.handle_query(Query.from_dict(data))
            else:
                print(f"[app] ignoring unknown type: {kind!r}")

    except websockets.ConnectionClosed:
        print("[app] client disconnected")
    finally:
        nudger.cancel()


async def main() -> None:
    llm = LLM()
    screen: ScreenReader | None = None

    print(f"[app] model: {llm.model}  (keep_alive {llm.keep_alive})")
    if not await llm.available():
        print(f"[app] WARNING: ollama not reachable at {llm.base_url}")
        print("[app] the avatar will connect and roam, but can't talk. start ollama.")
    else:
        models = await llm.installed_models()
        if llm.model not in models:
            print(f"[app] WARNING: '{llm.model}' is not pulled. have: {', '.join(models)}")
            print(f"[app] run:  ollama pull {llm.model}")
        else:
            print("[app] warming up (loading weights into VRAM)...")
            try:
                await llm.warmup()
                # ASCII only: a Windows console in cp1252 mangles an em-dash.
                print("[app] warm - first reply will be fast")
            except OllamaUnavailable as err:
                print(f"[app] warmup failed: {err}")

            if await llm.supports_tools():
                print("[app] tools: supported")
            else:
                print(f"[app] tools: NOT supported by '{llm.model}' - screen reading is off")
                print("[app] a tool-capable model (e.g. qwen2.5:7b) is required for read_screen")

    # Screen reading is a separate subsystem: if its worker won't start, the rest
    # of the avatar carries on knowing only window titles.
    if config.SCREEN_READ_ENABLED and llm.tools_supported:
        screen = ScreenReader()
        try:
            await screen.start()
            print(
                f"[app] screen reading: on  (ocr={'yes' if screen.ocr_available else 'no'}, "
                f"max {config.SCREEN_MAX_CHARS} chars, "
                f"{len(config.SCREEN_BLOCKLIST)} blocklist entries)"
            )
        except ScreenUnavailable as err:
            print(f"[app] screen reading: unavailable ({err})")
            screen = None
    else:
        print("[app] screen reading: off")

    print(f"[app] listening on ws://{config.WS_HOST}:{config.WS_PORT}")
    try:
        async with serve(lambda ws: handle(ws, llm, screen), config.WS_HOST, config.WS_PORT):
            await asyncio.Future()  # run forever
    finally:
        if screen:
            await screen.stop()
        await llm.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[app] shutting down")
