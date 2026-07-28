"""Async client for Ollama's native /api/chat.

Native rather than the /v1 OpenAI-compatible layer for one concrete reason:
/v1 accepts `keep_alive` and silently ignores it (it reports the default 5-minute
eviction no matter what you send). Keeping a 5GB model resident in VRAM is the
whole difference between an avatar that answers immediately and one that stalls
for ~15 seconds reloading weights at the start of every conversation.

Two things this module owns beyond plain HTTP:

  * A GPU lock. There is one Ollama service and 8GB of VRAM, so realistically
    one generation at a time. Interactive queries must not queue behind a
    background nudge, so `stream()` takes the lock and `try_stream()` gives up
    immediately if it's busy — background work uses the latter and simply skips
    its turn.
  * Honest failure. Ollama being down is normal (it's a laptop), so it raises a
    single typed exception the server can turn into something the avatar says,
    rather than a hang.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

import httpx

from core import config


class OllamaUnavailable(RuntimeError):
    """Ollama isn't reachable, or rejected the request outright."""


class LLM:
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        keep_alive: str | None = None,
    ) -> None:
        self.base_url = (base_url or config.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or config.LLM_MODEL
        self.keep_alive = keep_alive or config.LLM_KEEP_ALIVE

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                config.LLM_STREAM_TIMEOUT_S,
                connect=config.LLM_CONNECT_TIMEOUT_S,
            )
        )
        # Guards the single GPU. See module docstring.
        self._gpu = asyncio.Lock()
        self._tools_ok: bool | None = None  # cached supports_tools() answer

    async def aclose(self) -> None:
        await self._client.aclose()

    @property
    def busy(self) -> bool:
        return self._gpu.locked()

    @property
    def tools_supported(self) -> bool:
        """Sync view of the cached probe. False until supports_tools() has run."""
        return bool(self._tools_ok)

    # ------------------------------------------------------------- lifecycle --

    async def available(self) -> bool:
        try:
            r = await self._client.get(f"{self.base_url}/api/tags", timeout=3.0)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    async def installed_models(self) -> list[str]:
        try:
            r = await self._client.get(f"{self.base_url}/api/tags", timeout=5.0)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
        except (httpx.HTTPError, KeyError, ValueError) as err:
            raise OllamaUnavailable(str(err)) from err

    async def warmup(self) -> None:
        """Load the model into VRAM now, so the first real query is fast.

        Sends an empty-message request, which Ollama treats as load-only.
        """
        try:
            r = await self._client.post(
                f"{self.base_url}/api/chat",
                json={"model": self.model, "messages": [], "keep_alive": self.keep_alive},
                timeout=180.0,  # a cold 5GB load off a laptop SSD is not quick
            )
            r.raise_for_status()
        except httpx.HTTPError as err:
            raise OllamaUnavailable(f"warmup failed: {err}") from err

    # ---------------------------------------------------------------- generate --

    async def supports_tools(self) -> bool:
        """Ask Ollama whether this model accepts a `tools` array.

        Cached. Ollama answers definitively with HTTP 400 "does not support tools"
        rather than silently ignoring them, so this is a real answer and not a
        guess from a hardcoded model list.
        """
        if self._tools_ok is not None:
            return self._tools_ok

        probe = {
            "model": self.model,
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {"num_predict": 1},
            "tools": [{
                "type": "function",
                "function": {
                    "name": "noop",
                    "description": "probe",
                    "parameters": {"type": "object", "properties": {}},
                },
            }],
        }
        try:
            r = await self._client.post(f"{self.base_url}/api/chat", json=probe, timeout=120.0)
            self._tools_ok = r.status_code == 200
        except httpx.HTTPError:
            self._tools_ok = False
        return self._tools_ok

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        """Stream a text reply, waiting for the GPU if something else is using it.

        Yields content pieces as they arrive. Raises OllamaUnavailable on
        transport failure — including part-way through a stream, so callers must
        still close out their `reply_end`.
        """
        async with self._gpu:
            async for ev in self._stream_unlocked(messages, None):
                if ev["type"] == "text":
                    yield ev["text"]

    async def stream_events(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> AsyncIterator[dict]:
        """Stream with tool support, as a sequence of events.

        Yields {"type": "text", "text": ...} and, if the model decides to call
        something, {"type": "tool_calls", "calls": [...]}.

        Streaming is kept for the tool round rather than doing a blocking
        "decide, then answer" pass: if the model answers directly — the common
        case — the user sees it token by token instead of waiting out a silent
        round trip and getting the whole thing at once.
        """
        async with self._gpu:
            async for ev in self._stream_unlocked(messages, tools):
                yield ev

    async def try_stream(self, messages: list[dict]) -> AsyncIterator[str] | None:
        """Like `stream`, but returns None instead of queueing when busy.

        For background work (proactive nudges): if the user is mid-query, the
        right move is to skip this nudge entirely, not to make them wait.
        """
        if self._gpu.locked():
            return None
        return self.stream(messages)

    async def _stream_unlocked(
        self, messages: list[dict], tools: list[dict] | None
    ) -> AsyncIterator[dict]:
        body = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "keep_alive": self.keep_alive,
            "options": {
                "num_predict": config.LLM_MAX_TOKENS,
                "temperature": config.LLM_TEMPERATURE,
            },
        }
        if tools:
            body["tools"] = tools

        try:
            async with self._client.stream(
                "POST", f"{self.base_url}/api/chat", json=body
            ) as resp:
                if resp.status_code != 200:
                    detail = (await resp.aread()).decode(errors="replace")[:200]
                    raise OllamaUnavailable(f"HTTP {resp.status_code}: {detail}")

                # NDJSON: one JSON object per line.
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # don't die on one malformed frame

                    if err := data.get("error"):
                        raise OllamaUnavailable(str(err))

                    msg = data.get("message", {})

                    if calls := msg.get("tool_calls"):
                        yield {"type": "tool_calls", "calls": calls}

                    if piece := msg.get("content"):
                        yield {"type": "text", "text": piece}

                    if data.get("done"):
                        break
        except httpx.HTTPError as err:
            raise OllamaUnavailable(str(err)) from err
