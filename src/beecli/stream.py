"""Live events from `bee stream`, as typed Python objects, with reconnects.

`bee stream --json` may print plain JSON lines (only each event's `data`) or
SSE-style `event:` / `data:` lines. The Node library in @beeai/cli skips the
`event:` lines, so its callers never learn which event arrived. Here an
`event:` line is kept when there is one, and otherwise the type is inferred
from the payload's shape. `Event.exact` says which of the two happened.
"""

from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Iterator, Sequence

EVENT_TYPES = (
    "connected", "new-utterance", "new-conversation", "update-conversation", "update-conversation-summary",
    "delete-conversation", "update-location", "todo-created", "todo-updated", "todo-deleted",
    "journal-created", "journal-updated", "journal-deleted", "journal-text",
)


@dataclass
class Event:
    type: str            # one of EVENT_TYPES, or a family name when inferred ("todo", "journal")
    data: Any
    exact: bool = True   # False when the type was inferred from the payload
    raw: str = field(default="", repr=False)

    # Handy accessors for the common events.
    @property
    def utterance(self) -> dict | None:
        return self.data.get("utterance") if isinstance(self.data, dict) else None

    @property
    def conversation(self) -> dict | None:
        return self.data.get("conversation") if isinstance(self.data, dict) else None

    @property
    def conversation_id(self) -> Any:
        if not isinstance(self.data, dict):
            return None
        conv = self.data.get("conversation") or {}
        return (self.data.get("conversation_id") or self.data.get("conversation_uuid")
                or conv.get("id") or conv.get("uuid"))

    @property
    def ended(self) -> bool:
        """A conversation update that means it's finished and ready to read."""
        conv = self.conversation or {}
        return self.type in ("update-conversation", "conversation") and (
            bool(conv.get("end_time")) or str(conv.get("state", "")).lower() in ("processed", "completed"))


def infer_type(data: Any) -> str:
    """The most specific event type the payload's shape allows (see the CLI README's
    "Stream Events"). Some families can't be told apart without the name:
    todo-created and todo-updated carry the same payload, so they come back as "todo"."""
    if not isinstance(data, dict) or not data:
        return "connected"
    if "utterance" in data:
        return "new-utterance"
    if "todo" in data:
        todo = data["todo"] or {}
        return "todo" if "completed" in todo else "todo-deleted"
    if "journalId" in data:
        return "journal-text" if "text" in data else "journal-deleted"
    if "journal" in data:
        return "journal"
    if "location" in data and "conversation_id" in data:
        return "update-location"
    if "short_summary" in data and "conversation_id" in data:
        return "update-conversation-summary"
    if "conversation" in data:
        conv = data["conversation"] or {}
        state = str(conv.get("state", "")).lower()
        if state == "processing" and "uuid" in conv:
            return "new-conversation"
        if "state" not in conv and set(conv) <= {"id", "title"}:
            return "delete-conversation"
        return "update-conversation"
    return "unknown"


def parse_lines(lines: Iterable[str]) -> Iterator[Event]:
    """Events from the CLI's output lines: bare JSON lines or SSE blocks."""
    name: str | None = None
    data: list[str] = []

    def emit() -> Event | None:
        nonlocal name, data
        payload, event_name = "\n".join(data).strip(), name
        name, data = None, []
        if not payload or payload == "[DONE]":
            return Event("connected", {}, True) if event_name == "connected" else None
        try:
            value = json.loads(payload)
        except json.JSONDecodeError:
            return None
        if event_name:
            return Event(event_name, value, True, payload)
        return Event(infer_type(value), value, False, payload)

    for line in lines:
        line = line.rstrip("\r\n")
        stripped = line.strip()
        if not stripped:
            if name or data:
                ev = emit()
                if ev:
                    yield ev
            continue
        if stripped.startswith(":") or stripped.startswith("id:") or stripped.startswith("retry:"):
            continue
        if stripped.startswith("event:"):
            if data:  # a new block started without a blank line
                ev = emit()
                if ev:
                    yield ev
            name = stripped[6:].strip()
            continue
        if stripped.startswith("data:"):
            data.append(stripped[5:].lstrip())
            continue
        if stripped[:1] in "{[":  # a bare JSON line: one event on its own
            if name or data:
                data.append(stripped)
                ev = emit()
            else:
                try:
                    value = json.loads(stripped)
                    ev = Event(infer_type(value), value, False, stripped)
                except json.JSONDecodeError:
                    ev = None
            if ev:
                yield ev
    if name or data:
        ev = emit()
        if ev:
            yield ev


class Stream:
    """Iterate live events; reconnects with backoff until `close()`.

    >>> with bee.stream(["new-utterance", "update-conversation"]) as events:
    ...     for ev in events:
    ...         if ev.type == "new-utterance":
    ...             print(ev.utterance["speaker"], ev.utterance["text"])
    ...         elif ev.ended:
    ...             print("finished:", ev.conversation_id)

    reconnect=False stops at the first disconnect. on_error(message) hears why a
    connection dropped (stderr of the CLI), so callers can show it.
    """

    def __init__(self, bee, types: Sequence[str] | str = ("all",), *, reconnect: bool = True,
                 backoff: tuple[float, float] = (2.0, 60.0), on_error: Callable[[str], None] | None = None,
                 popen: Callable[..., subprocess.Popen] | None = None):
        self.bee = bee
        self.types = [types] if isinstance(types, str) else list(types)
        self.reconnect = reconnect
        self.backoff = backoff
        self.on_error = on_error
        self._popen = popen or subprocess.Popen
        self._stop = threading.Event()
        self._proc: subprocess.Popen | None = None
        self.connections = 0

    def command(self) -> list[str]:
        return self.bee.command("stream", "--json", "--types", ",".join(self.types) or "all")

    def close(self) -> None:
        self._stop.set()
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    def __enter__(self) -> "Stream":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __iter__(self) -> Iterator[Event]:
        delay = self.backoff[0]
        while not self._stop.is_set():
            try:
                self._proc = self._popen(self.command(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                         stdin=subprocess.DEVNULL, text=True)
            except FileNotFoundError:
                from .client import BeeError

                raise BeeError(f"`{self.bee.binary}` not found. Install it with: npm install -g @beeai/cli")
            self.connections += 1
            try:
                for ev in parse_lines(self._proc.stdout):  # type: ignore[arg-type]
                    if self._stop.is_set():
                        return
                    delay = self.backoff[0]
                    yield ev
            finally:
                if self._proc.poll() is None:
                    self._proc.terminate()
                    try:
                        self._proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self._proc.kill()
            if self._stop.is_set():
                return
            err = (self._proc.stderr.read() if self._proc.stderr else "") or ""
            if self.on_error:
                self.on_error(err.strip() or f"stream ended (exit {self._proc.returncode})")
            if not self.reconnect:
                return
            self._stop.wait(delay)
            delay = min(delay * 2, self.backoff[1])
