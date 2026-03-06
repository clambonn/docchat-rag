"""
AG-UI Protocol — Server-Sent Events emitter.

AG-UI defines a standardised event stream between agent backend and frontend.
We implement the core event types needed for chat:
  RUN_STARTED, TEXT_MESSAGE_START, TEXT_MESSAGE_CONTENT,
  TEXT_MESSAGE_END, TOOL_CALL_START, TOOL_CALL_END, RUN_FINISHED, RUN_ERROR

Spec: https://docs.ag-ui.com/concepts/events
"""

from __future__ import annotations
import json
import uuid
import time
from typing import AsyncIterator, Any


def _event(event_type: str, data: dict) -> str:
    """Format a single SSE message per AG-UI spec."""
    payload = {"type": event_type, "timestamp": int(time.time() * 1000), **data}
    return f"data: {json.dumps(payload)}\n\n"


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def run_started(run_id: str, thread_id: str) -> str:
    return _event("RUN_STARTED", {"runId": run_id, "threadId": thread_id})


def run_finished(run_id: str) -> str:
    return _event("RUN_FINISHED", {"runId": run_id})


def run_error(run_id: str, message: str) -> str:
    return _event("RUN_ERROR", {"runId": run_id, "message": message})


# ── Text streaming ────────────────────────────────────────────────────────────

def text_message_start(msg_id: str, role: str = "assistant") -> str:
    return _event("TEXT_MESSAGE_START", {"messageId": msg_id, "role": role})


def text_message_content(msg_id: str, delta: str) -> str:
    return _event("TEXT_MESSAGE_CONTENT", {"messageId": msg_id, "delta": delta})


def text_message_end(msg_id: str) -> str:
    return _event("TEXT_MESSAGE_END", {"messageId": msg_id})


# ── Tool calls (used for source citation rendering) ───────────────────────────

def tool_call_start(tool_call_id: str, tool_name: str) -> str:
    return _event("TOOL_CALL_START", {
        "toolCallId": tool_call_id,
        "toolCallName": tool_name,
        "parentMessageId": None,
    })


def tool_call_end(tool_call_id: str, result: Any) -> str:
    return _event("TOOL_CALL_END", {
        "toolCallId": tool_call_id,
        "result": result,
    })


# ── State delta (shared state between agent and frontend) ─────────────────────

def state_snapshot(state: dict) -> str:
    """Push a full state snapshot to the frontend."""
    return _event("STATE_SNAPSHOT", {"snapshot": state})


def state_delta(delta: list[dict]) -> str:
    """Push a JSON Patch (RFC 6902) diff."""
    return _event("STATE_DELTA", {"delta": delta})


# ── Custom event (sources / metadata) ─────────────────────────────────────────

def custom_event(name: str, value: Any) -> str:
    return _event("CUSTOM", {"name": name, "value": value})
