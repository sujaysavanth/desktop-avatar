"""Tests for the LLM client and the streaming protocol.

Deliberately split: the protocol/failure tests use a fake HTTP server so they run
in milliseconds and need no GPU, and the one test that does hit the real model is
marked so you can skip it.

    python -m tests.test_llm            # everything, including the live model
    python -m tests.test_llm --fast     # skip the live model
"""

from __future__ import annotations

import asyncio
import json
import sys

from core.protocol import Context, Query, reply, reply_chunk, reply_end, state
from llm import LLM, OllamaUnavailable

PASS, FAIL = "  ok  ", " FAIL "
failures: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"[{PASS if cond else FAIL}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(name)


# --------------------------------------------------------------- protocol --


def test_protocol_shapes() -> None:
    check("reply_chunk shape", reply_chunk("hi") == {"type": "reply_chunk", "text": "hi"})
    check("reply_end shape", reply_end() == {"type": "reply_end"})
    check("reply still atomic", reply("x") == {"type": "reply", "text": "x"})
    check("state accepts str", state("idle") == {"type": "state", "value": "idle"})

    q = Query.from_dict({"type": "query", "agent": "job", "text": "hello"})
    check("Query parses", q.agent == "job" and q.text == "hello")

    # Context fields are advisory — a partial message must not raise.
    c = Context.from_dict({"type": "context", "app": "Code"})
    check("Context tolerates missing title", c.app == "Code" and c.title == "")

    for bad in ({"type": "reply"}, {"type": "context"}):
        try:
            Query.from_dict(bad)
            check("Query rejects wrong type", False, f"accepted {bad}")
        except (ValueError, KeyError):
            check("Query rejects wrong type", True)
            break


# ------------------------------------------------------------ fake ollama --


class FakeOllama:
    """Minimal /api/chat that streams NDJSON, so we can test without a GPU."""

    def __init__(self, pieces: list[str], *, fail_midway: bool = False,
                 status: int = 200, error: str | None = None) -> None:
        self.pieces = pieces
        self.fail_midway = fail_midway
        self.status = status
        self.error = error
        self.last_body: dict | None = None
        self.server: asyncio.Server | None = None
        self.port = 0

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            # Read request line + headers, then the body by Content-Length.
            head = await reader.readuntil(b"\r\n\r\n")
            path = head.split(b" ")[1].decode()
            length = 0
            for line in head.decode(errors="replace").split("\r\n"):
                if line.lower().startswith("content-length:"):
                    length = int(line.split(":")[1])
            body = await reader.readexactly(length) if length else b"{}"
            try:
                self.last_body = json.loads(body)
            except json.JSONDecodeError:
                self.last_body = {}

            if path.endswith("/api/tags"):
                payload = json.dumps({"models": [{"name": "fake:latest"}]}).encode()
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                    b"Content-Length: " + str(len(payload)).encode() + b"\r\n\r\n" + payload
                )
                await writer.drain()
                return

            if self.status != 200:
                msg = b'{"error":"boom"}'
                writer.write(
                    f"HTTP/1.1 {self.status} Bad\r\nContent-Length: {len(msg)}\r\n\r\n".encode() + msg
                )
                await writer.drain()
                return

            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/x-ndjson\r\n"
                b"Transfer-Encoding: chunked\r\n\r\n"
            )

            async def send_line(obj: dict) -> None:
                data = (json.dumps(obj) + "\n").encode()
                writer.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")
                await writer.drain()

            if self.error:
                await send_line({"error": self.error})
            else:
                for i, p in enumerate(self.pieces):
                    if self.fail_midway and i == len(self.pieces) // 2:
                        writer.close()  # simulate the connection dropping
                        return
                    await send_line({"message": {"content": p}, "done": False})
                await send_line({"message": {"content": ""}, "done": True})

            writer.write(b"0\r\n\r\n")
            await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass


# ---------------------------------------------------------- client tests --


async def test_stream_happy() -> None:
    fake = FakeOllama(["Hel", "lo ", "there"])
    await fake.start()
    llm = LLM(base_url=fake.url, model="fake:latest")
    try:
        got = [p async for p in llm.stream([{"role": "user", "content": "hi"}])]
        check("streams every piece in order", got == ["Hel", "lo ", "there"], str(got))
        check(
            "keep_alive is sent (the whole reason for the native api)",
            fake.last_body.get("keep_alive") == llm.keep_alive,
            str(fake.last_body),
        )
        check(
            "token ceiling is sent",
            fake.last_body.get("options", {}).get("num_predict") is not None,
        )
    finally:
        await llm.aclose()
        await fake.stop()


async def test_stream_failures() -> None:
    # Nothing listening at all.
    llm = LLM(base_url="http://127.0.0.1:1", model="fake:latest")
    try:
        try:
            [p async for p in llm.stream([{"role": "user", "content": "hi"}])]
            check("connection refused raises OllamaUnavailable", False, "no raise")
        except OllamaUnavailable:
            check("connection refused raises OllamaUnavailable", True)
        check("available() is False when down", not await llm.available())
    finally:
        await llm.aclose()

    # Non-200.
    fake = FakeOllama([], status=500)
    await fake.start()
    llm = LLM(base_url=fake.url, model="fake:latest")
    try:
        try:
            [p async for p in llm.stream([{"role": "user", "content": "hi"}])]
            check("HTTP 500 raises OllamaUnavailable", False, "no raise")
        except OllamaUnavailable:
            check("HTTP 500 raises OllamaUnavailable", True)
    finally:
        await llm.aclose()
        await fake.stop()

    # An {"error": ...} frame inside a 200 stream.
    fake = FakeOllama([], error="model not found")
    await fake.start()
    llm = LLM(base_url=fake.url, model="fake:latest")
    try:
        try:
            [p async for p in llm.stream([{"role": "user", "content": "hi"}])]
            check("in-stream error frame raises", False, "no raise")
        except OllamaUnavailable:
            check("in-stream error frame raises", True)
    finally:
        await llm.aclose()
        await fake.stop()

    # Dropped mid-stream: pieces already yielded, THEN it raises. The server must
    # still be able to close out its reply_end.
    fake = FakeOllama(["a", "b", "c", "d"], fail_midway=True)
    await fake.start()
    llm = LLM(base_url=fake.url, model="fake:latest")
    try:
        got, raised = [], False
        try:
            async for p in llm.stream([{"role": "user", "content": "hi"}]):
                got.append(p)
        except OllamaUnavailable:
            raised = True
        check("mid-stream drop yields partial then raises", raised and len(got) > 0,
              f"raised={raised} got={got}")
    finally:
        await llm.aclose()
        await fake.stop()


async def test_gpu_lock() -> None:
    """try_stream must SKIP when the GPU is busy, not queue behind it."""
    fake = FakeOllama(["x"] * 6)
    await fake.start()
    llm = LLM(base_url=fake.url, model="fake:latest")
    try:
        started = asyncio.Event()
        release = asyncio.Event()

        async def slow_consumer() -> None:
            async for _ in llm.stream([{"role": "user", "content": "hi"}]):
                started.set()
                await release.wait()  # hold the lock

        task = asyncio.create_task(slow_consumer())
        await asyncio.wait_for(started.wait(), timeout=5)

        check("busy reports True while streaming", llm.busy)
        skipped = await llm.try_stream([{"role": "user", "content": "nudge"}])
        check("try_stream returns None when busy (nudge is skipped)", skipped is None)

        release.set()
        await asyncio.wait_for(task, timeout=5)

        check("lock released after stream", not llm.busy)
        again = await llm.try_stream([{"role": "user", "content": "nudge"}])
        check("try_stream works once free", again is not None)
        if again is not None:
            [p async for p in again]  # drain so the lock doesn't leak
    finally:
        await llm.aclose()
        await fake.stop()


async def test_live_model() -> None:
    """The one test that needs Ollama and a pulled model."""
    llm = LLM()
    try:
        if not await llm.available():
            print("[ skip ] live model — ollama not reachable")
            return
        if llm.model not in await llm.installed_models():
            print(f"[ skip ] live model — {llm.model} not pulled")
            return

        # Must be a prompt that necessarily spans several tokens — a one-word
        # answer streams as a single chunk and would fail for the wrong reason.
        pieces = [p async for p in llm.stream(
            [{"role": "user", "content": "Count from one to five, words only."}]
        )]
        text = "".join(pieces).strip()
        check("live model streams more than one chunk", len(pieces) > 1, f"{len(pieces)} chunks")
        check("live model returns text", bool(text), repr(text))
    finally:
        await llm.aclose()


async def main() -> None:
    fast = "--fast" in sys.argv

    test_protocol_shapes()
    await test_stream_happy()
    await test_stream_failures()
    await test_gpu_lock()
    if fast:
        print("[ skip ] live model — --fast")
    else:
        await test_live_model()

    print()
    if failures:
        print(f"{len(failures)} FAILED: {', '.join(failures)}")
        sys.exit(1)
    print("all passed")


if __name__ == "__main__":
    asyncio.run(main())
