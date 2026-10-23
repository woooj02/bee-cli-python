"""Helpers for conversation payloads: times and transcripts."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def to_ms(value: Any) -> int | None:
    """Epoch milliseconds from whatever Bee sent: ms, seconds, a digit string
    or an ISO date (the CLI itself accepts all of these). None if it can't tell."""
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, str):
        if value.strip().isdigit():
            value = int(value)
        else:
            try:
                return int(datetime.fromisoformat(value.strip().replace("Z", "+00:00")).timestamp() * 1000)
            except ValueError:
                return None
    if isinstance(value, (int, float)):
        if value > 1e12:
            return int(value)
        if value > 1e9:
            return int(value * 1000)
    return None


def unwrap(payload: Any, key: str) -> Any:
    """`conversations get --json` answers {"conversation": {...}}; list commands
    answer {"conversations": [...]}. unwrap(x, "conversation") returns the inner
    value whichever shape arrived."""
    if isinstance(payload, dict) and key in payload:
        return payload[key]
    return payload


def utterances(conversation: dict) -> list[dict]:
    """The transcript in spoken order. Each line keeps Bee's fields and gains
    `at` (epoch ms). When Bee holds both a realtime and a final transcription,
    the final one wins, as in the CLI's own markdown output."""
    conversation = unwrap(conversation, "conversation") or {}
    transcriptions = conversation.get("transcriptions") or []
    if not transcriptions:
        return []
    chosen = next((t for t in transcriptions if not t.get("realtime")), transcriptions[0])
    items = []
    for u in chosen.get("utterances") or []:
        text = (u.get("text") or "").strip()
        if not text:
            continue
        items.append({**u, "text": text, "speaker": str(u.get("speaker") or "unknown"),
                      "at": to_ms(u.get("spoken_at")) or to_ms(u.get("start"))})
    items.sort(key=lambda u: (u["at"] or 0, u.get("id") or 0))
    return items


def word_count(items: list[dict]) -> int:
    return sum(len((u.get("text") or "").split()) for u in items)


def speakers(items: list[dict]) -> list[str]:
    """Speaker labels in order of first appearance."""
    seen: dict[str, None] = {}
    for u in items:
        seen.setdefault(u["speaker"], None)
    return list(seen)
