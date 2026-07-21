"""The websocket contract between avatar (client) and backend (server).

LOCKED at Phase 0. The stub honors it now; the real orchestrator honors the
SAME shape later. Do not change these message types without updating both
sides deliberately.

    avatar -> backend:
        {"type": "query", "agent": "job", "text": "..."}

    backend -> avatar:
        {"type": "reply", "text": "..."}
        {"type": "state", "value": "thinking" | "idle" | "needs-you"}
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AgentState(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    NEEDS_YOU = "needs-you"


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


def reply(text: str) -> dict:
    """backend -> avatar"""
    return {"type": "reply", "text": text}


def state(value: AgentState | str) -> dict:
    """backend -> avatar"""
    v = value.value if isinstance(value, AgentState) else value
    return {"type": "state", "value": v}
