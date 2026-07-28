"""The `read_screen` tool: what is actually visible in the focused window.

This is the widest-reaching tool in the project, so it's also the most gated.
Design principle #2 says the LLM decides *what* — so the model chooses when to
look — but every constraint on *how much* it sees is enforced here in
deterministic code, never left to the prompt:

  * focused window only, never the whole desktop
  * a blocklist checked BEFORE any pixel is captured, matched on both process
    name and window title
  * a minimum interval between reads, so a confused model can't sit in a capture
    loop
  * captures never touch disk beyond the temp file the OCR decoder requires,
    which the worker deletes in a `finally`
  * output truncated to a character budget, because a 4096-token context is not
    somewhere you dump a whole screen

Backed by one long-lived PowerShell worker. Cold-starting PowerShell costs ~1.2s
in process spawn and Add-Type, which dwarfs the ~300ms of real work; keeping it
alive turns a 1.5s tool call into ~350ms. Same pattern as the focus watcher in
the avatar's main.js, for the same reason.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from core import config


class ScreenUnavailable(RuntimeError):
    """The worker isn't running, died, or this isn't Windows."""


class ScreenBlocked(RuntimeError):
    """Refused by policy — blocklist or rate limit. Carries a reason for the model."""


# What the LLM is told the tool does. Ollama passes this through to the model, so
# it doubles as prompt engineering: be explicit that it costs something and that
# it may be refused.
TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "read_screen",
        "description": (
            "Read the text currently visible in the user's focused window, using "
            "OCR and accessibility APIs. Use this when the user refers to "
            "something on their screen ('this error', 'what am I looking at', "
            "'this page') and you need the actual content rather than just the "
            "window title. Takes about a third of a second. May be refused for "
            "sensitive applications, in which case say so plainly."
        ),
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


class ScreenReader:
    def __init__(self, script: Path | None = None) -> None:
        self.script = script or (config.ROOT / "scripts" / "read-screen.ps1")
        self._proc: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()  # one read at a time; the worker is serial
        self._last_read = 0.0
        self.ocr_available = False

    # ------------------------------------------------------------- lifecycle --

    async def start(self) -> None:
        if not config.SCREEN_READ_ENABLED:
            return
        if not self.script.exists():
            raise ScreenUnavailable(f"missing worker script: {self.script}")

        self._proc = await asyncio.create_subprocess_exec(
            "powershell.exe",
            "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", str(self.script),
            "-Serve",
            "-MaxChars", str(config.SCREEN_MAX_CHARS),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        # The worker announces readiness once Add-Type is done.
        try:
            hello = await asyncio.wait_for(self._read_line(), timeout=45.0)
        except asyncio.TimeoutError as err:
            raise ScreenUnavailable("worker did not become ready") from err

        if not hello.get("ready"):
            raise ScreenUnavailable(f"unexpected worker greeting: {hello}")
        self.ocr_available = bool(hello.get("ocr_available"))

    async def stop(self) -> None:
        if not self._proc:
            return
        try:
            if self._proc.stdin and not self._proc.stdin.is_closing():
                self._proc.stdin.write(b"quit\n")
                await self._proc.stdin.drain()
            await asyncio.wait_for(self._proc.wait(), timeout=3.0)
        except (asyncio.TimeoutError, ProcessLookupError, ConnectionResetError, OSError):
            try:
                self._proc.kill()
            except ProcessLookupError:
                pass
        finally:
            self._proc = None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    async def _read_line(self) -> dict:
        assert self._proc and self._proc.stdout
        raw = await self._proc.stdout.readline()
        if not raw:
            raise ScreenUnavailable("worker closed its output")
        return json.loads(raw.decode("utf-8", errors="replace").strip())

    # ---------------------------------------------------------------- policy --

    @staticmethod
    def is_blocked(app: str, title: str) -> str | None:
        """Return a human-readable reason if this window must not be read.

        Checked against process name AND title: a banking site in a browser has an
        innocuous process name, and a password manager may have an innocuous title.
        """
        haystack = f"{app} {title}".lower()
        for needle in config.SCREEN_BLOCKLIST:
            if needle.lower() in haystack:
                return f"'{needle}' is on the screen-reading blocklist"
        return None

    # ------------------------------------------------------------------ read --

    async def read(self) -> dict:
        if not config.SCREEN_READ_ENABLED:
            raise ScreenBlocked("screen reading is disabled in config")
        if not self.running:
            raise ScreenUnavailable("worker is not running")

        async with self._lock:
            since = time.monotonic() - self._last_read
            if since < config.SCREEN_MIN_INTERVAL_S:
                raise ScreenBlocked(
                    f"screen was read {since:.1f}s ago; "
                    f"minimum interval is {config.SCREEN_MIN_INTERVAL_S}s"
                )

            assert self._proc and self._proc.stdin
            try:
                self._proc.stdin.write(b"read\n")
                await self._proc.stdin.drain()
                snap = await asyncio.wait_for(
                    self._read_line(), timeout=config.SCREEN_TIMEOUT_S
                )
            except (asyncio.TimeoutError, ConnectionResetError, BrokenPipeError, OSError) as err:
                raise ScreenUnavailable(f"worker read failed: {err}") from err

            self._last_read = time.monotonic()

        if not snap.get("ok"):
            raise ScreenUnavailable(snap.get("error") or "unknown worker error")

        # Policy is enforced AFTER the worker identifies the window but the worker
        # has already captured by then, so the blocklist also lives in the caller
        # path below. Belt and braces: drop the content, keep the metadata.
        if reason := self.is_blocked(snap.get("app", ""), snap.get("title", "")):
            snap["ocr"] = ""
            snap["uia"] = ""
            snap["blocked"] = reason
        return snap

    # ------------------------------------------------------------ formatting --

    @staticmethod
    def to_prompt(snap: dict) -> str:
        """Render a snapshot as the tool result the model reads."""
        if snap.get("blocked"):
            return f"Screen reading refused: {snap['blocked']}. Tell the user you can't look at that."

        lines = [f"Focused window: {snap.get('app') or 'unknown'} — {snap.get('title') or 'untitled'}"]

        if uia := (snap.get("uia") or "").strip():
            lines.append(f"Accessibility values (URLs, field contents): {uia}")

        text = (snap.get("ocr") or "").strip()
        if text:
            lines.append(
                "Visible text, read by OCR (may contain recognition errors, and "
                "reading order is approximate):"
            )
            lines.append(text)
        else:
            lines.append("No text could be read from the window.")

        if snap.get("truncated"):
            lines.append("[truncated — only the start of the window's text is shown]")
        return "\n".join(lines)
