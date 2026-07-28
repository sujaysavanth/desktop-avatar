"""The websocket contract between avatar (client) and backend (server).

LOCKED at Phase 0. The stub honors it now; the real orchestrator honors the
SAME shape later. Do not change these message types without updating both
sides deliberately.

    avatar -> backend:
        {"type": "query",   "agent": "job", "text": "..."}
        {"type": "context", "app": "Code", "title": "renderer.js — desk-avatars"}

    backend -> avatar:
        {"type": "reply",       "text": "..."}
        {"type": "reply_chunk", "text": "..."}
        {"type": "reply_end"}
        {"type": "state",       "value": "thinking" | "idle" | "needs-you"}
        {"type": "intent",      "action": "wander" | ..., "text": "..." | null}

Two ways to say something, and the difference matters:

  * `reply` is one complete utterance. Right for anything already known in full
    — a canned line, an error, a proactive one-liner attached to an intent.
  * `reply_chunk`* then `reply_end` streams a generated reply token by token.
    A 7B model needs several seconds for a few sentences; without streaming the
    avatar just stands on `thinking` for all of it. The avatar accumulates
    chunks into one bubble and only starts the dismiss timer on `reply_end`.

`reply_end` is not optional — it's what closes the bubble. If generation fails
midway, send `reply_end` anyway (then a `reply` explaining, if you like).

`context` and `intent` were added deliberately for the roaming avatar:

  * `context` tells the backend which app has focus, so it has something to be
    proactive *about*. Sent only on change, never as a heartbeat.
  * `intent` is a nudge, not a command. The avatar's behavior state machine
    queues it and applies it at the next transition — the backend biases *what*
    the avatar does next; the renderer still owns *how* and every frame of it.
    Nothing breaks if the backend never sends one.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AgentState(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    NEEDS_YOU = "needs-you"


class IntentAction(str, Enum):
    """What the backend can ask the avatar to *feel like* doing next."""

    WANDER = "wander"      # pick a new spot and stroll to it
    APPROACH = "approach"  # come toward the middle of the screen (get noticed)
    PEEK = "peek"          # head for the nearest screen edge
    SLEEP = "sleep"        # settle down and nap
    IDLE = "idle"          # just stand there


@dataclass
class Query:
    """avatar -> backend"""
    agent: str
    text: str

    @classmethod
    def from_dict(cls, d: dict) -> "Query":
        if d.get("type") != "query":
            raise ValueError(f"expected type=query, got {d.get('type')!r}")
        return cls(agent=d["agent"], text=d["text"])


@dataclass
class Context:
    """avatar -> backend. Which app the human is actually looking at."""
    app: str
    title: str

    @classmethod
    def from_dict(cls, d: dict) -> "Context":
        if d.get("type") != "context":
            raise ValueError(f"expected type=context, got {d.get('type')!r}")
        # Both fields are advisory — a missing one shouldn't break a connection.
        return cls(app=d.get("app", ""), title=d.get("title", ""))


def reply(text: str) -> dict:
    """backend -> avatar"""
    return {"type": "reply", "text": text}


def reply_chunk(text: str) -> dict:
    """backend -> avatar. One piece of a streaming reply."""
    return {"type": "reply_chunk", "text": text}


def reply_end() -> dict:
    """backend -> avatar. Closes a streamed reply. Always send one."""
    return {"type": "reply_end"}


def state(value: AgentState | str) -> dict:
    """backend -> avatar"""
    v = value.value if isinstance(value, AgentState) else value
    return {"type": "state", "value": v}


def intent(action: IntentAction | str, text: str | None = None) -> dict:
    """backend -> avatar. `text` is an optional line to say on arrival."""
    a = action.value if isinstance(action, IntentAction) else action
    return {"type": "intent", "action": a, "text": text}
