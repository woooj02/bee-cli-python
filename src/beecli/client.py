"""The Bee client: every `bee` CLI data command, as Python calls that return JSON.

It runs the official binary with `--json`, the same way the Node library that
ships with @beeai/cli does (`createBeeClient` in `dist/lib`). Authentication,
the API host and certificates all stay inside Bee's own client.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any, Callable, Sequence

Runner = Callable[..., subprocess.CompletedProcess]


class BeeError(RuntimeError):
    """The CLI failed, timed out, is missing, or printed something that isn't JSON."""

    def __init__(self, message: str, *, args: Sequence[str] = (), exit_code: int | None = None):
        super().__init__(message)
        self.command = list(args)
        self.exit_code = exit_code


class Bee:
    """One Bee account, through the `bee` CLI.

    >>> bee = Bee()
    >>> bee.me()["first_name"]
    >>> bee.conversations.list(limit=5)
    >>> bee.todos.create("Call Kamala", alarm_at="2026-10-19T09:00:00-06:00")

    `binary` defaults to $BEE_BIN, then `bee` on PATH. `staging=True` adds
    `--staging`, like the Node library's `environment: "staging"`. `runner`
    replaces `subprocess.run` (see `beecli.testing.FakeBee`).
    """

    def __init__(self, binary: str | None = None, *, staging: bool = False, timeout: float = 60,
                 env: dict[str, str] | None = None, runner: Runner | None = None):
        self.binary = binary or os.environ.get("BEE_BIN") or "bee"
        self.staging = staging
        self.timeout = timeout
        self.env = env
        self._run = runner or subprocess.run
        self.facts = _Facts(self)
        self.todos = _Todos(self)
        self.conversations = _Conversations(self)
        self.daily = _Daily(self)
        self.journals = _Journals(self)
        self.insights = _Insights(self)
        self.locations = _Locations(self)
        self.photos = _Photos(self)

    # ---- plumbing ----
    def command(self, *args: str) -> list[str]:
        return [self.binary, *(["--staging"] if self.staging else []), *args]

    def run(self, *args: str, timeout: float | None = None) -> subprocess.CompletedProcess:
        """Run any bee command; returns the finished process (no JSON parsing)."""
        cmd = self.command(*args)
        env = {**os.environ, **self.env} if self.env else None
        try:
            return self._run(cmd, capture_output=True, text=True, timeout=timeout or self.timeout, env=env)
        except FileNotFoundError as exc:
            raise BeeError(f"`{self.binary}` not found. Install it with: npm install -g @beeai/cli", args=cmd) from exc
        except subprocess.TimeoutExpired as exc:
            raise BeeError(f"`{' '.join(cmd[:3])}` timed out after {timeout or self.timeout:.0f}s", args=cmd) from exc

    def json(self, *args: str, timeout: float | None = None) -> Any:
        """Run a command with `--json` and parse what it prints. Empty output is None."""
        if "--json" not in args:
            args = (*args, "--json")
        proc = self.run(*args, timeout=timeout)
        if proc.returncode != 0:
            lines = (proc.stderr or proc.stdout or "").strip().splitlines()
            msg = lines[-1] if lines else f"exited with code {proc.returncode}"
            raise BeeError(f"`bee {' '.join(args[:2])}` failed: {msg}", args=self.command(*args),
                           exit_code=proc.returncode)
        out = (proc.stdout or "").strip()
        if not out:
            return None
        try:
            return json.loads(out)
        except json.JSONDecodeError as exc:
            raise BeeError(f"`bee {' '.join(args[:2])}` did not print JSON", args=self.command(*args)) from exc

    def available(self) -> bool:
        """Is the binary installed?"""
        return bool(shutil.which(self.binary)) or os.path.isfile(self.binary)

    def logged_in(self) -> bool:
        try:
            self.me()
            return True
        except BeeError:
            return False

    def stream(self, types: Sequence[str] | str = ("all",), **kwargs):
        """Live events. See `beecli.stream.Stream`."""
        from .stream import Stream

        return Stream(self, types=types, **kwargs)

    # ---- top-level commands ----
    def me(self) -> dict:
        return self.json("me", timeout=20)

    def version(self) -> Any:
        return self.json("version", timeout=20)

    def today(self, context: bool = False) -> Any:
        """Today's brief (calendar and email), or with context=True the wearable context
        (daily summary, active todos, notes, conversations)."""
        return self.json("today", *(["--context"] if context else []))

    def now(self) -> Any:
        """Conversations from the last 10 hours, with utterances."""
        return self.json("now")

    def activity(self, limit: int | None = None) -> Any:
        return self.json("activity", *_opt("--limit", limit))

    def changed(self, cursor: str | None = None) -> Any:
        return self.json("changed", *_opt("--cursor", cursor))

    def search(self, query: str, *, limit: int | None = None, filter: str | None = None, sort: str | None = None,
               since: int | None = None, until: int | None = None, neural: bool = False) -> Any:
        """Keyword search across conversations, daily summaries and facts
        (filter: conversations|daily|facts|all; sort: relevance|mostRecent), or
        neural=True for semantic conversation search. since/until are epoch ms."""
        if neural and (filter or sort):
            raise ValueError("filter and sort don't apply to neural search")
        args = ["search", "--query", query, *_opt("--limit", limit), *_opt("--since", since), *_opt("--until", until)]
        args += ["--neural"] if neural else [*_opt("--filter", filter), *_opt("--sort", sort)]
        return self.json(*args)


def _opt(flag: str, value: Any) -> list[str]:
    if value is None or value is False:
        return []
    if value is True:
        return [flag]
    return [flag, str(value).lower() if isinstance(value, bool) else str(value)]


def _page(limit: int | None, cursor: str | None) -> list[str]:
    return [*_opt("--limit", limit), *_opt("--cursor", cursor)]


class _Group:
    def __init__(self, bee: Bee):
        self._bee = bee

    def _json(self, *args: str, **kw) -> Any:
        return self._bee.json(*args, **kw)


class _Facts(_Group):
    """Things Bee remembers about the wearer."""

    def list(self, limit: int | None = None, cursor: str | None = None, unconfirmed: bool = False) -> Any:
        return self._json("facts", "list", *_page(limit, cursor), *_opt("--unconfirmed", unconfirmed))

    def get(self, fact_id: int | str) -> Any:
        return self._json("facts", "get", str(fact_id))

    def create(self, text: str) -> Any:
        return self._json("facts", "create", "--text", text)

    def update(self, fact_id: int | str, text: str | None = None, confirmed: bool | None = None) -> Any:
        args = ["facts", "update", str(fact_id), *_opt("--text", text)]
        if confirmed is not None:
            args += ["--confirmed", "true" if confirmed else "false"]
        return self._json(*args)

    def confirm(self, fact_id: int | str) -> Any:
        return self._json("facts", "confirm", str(fact_id))

    def delete(self, fact_id: int | str) -> Any:
        return self._json("facts", "delete", str(fact_id))

    def search(self, query: str, limit: int | None = None) -> Any:
        return self._json("facts", "search", "--query", query, *_opt("--limit", limit))


class _Todos(_Group):
    def list(self, limit: int | None = None, cursor: str | None = None) -> Any:
        return self._json("todos", "list", *_page(limit, cursor))

    def get(self, todo_id: int | str) -> Any:
        return self._json("todos", "get", str(todo_id))

    def create(self, text: str, alarm_at: str | None = None) -> Any:
        """alarm_at is an ISO time; the Bee app rings then."""
        return self._json("todos", "create", "--text", text, *_opt("--alarm-at", alarm_at))

    def update(self, todo_id: int | str, text: str | None = None, completed: bool | None = None,
               alarm_at: str | None = None, clear_alarm: bool = False) -> Any:
        if alarm_at and clear_alarm:
            raise ValueError("pass alarm_at or clear_alarm, not both")
        args = ["todos", "update", str(todo_id), *_opt("--text", text)]
        if completed is not None:
            args += ["--completed", "true" if completed else "false"]
        args += [*_opt("--alarm-at", alarm_at), *_opt("--clear-alarm", clear_alarm)]
        return self._json(*args)

    def complete(self, todo_id: int | str) -> Any:
        return self._json("todos", "complete", str(todo_id))

    def delete(self, todo_id: int | str) -> Any:
        return self._json("todos", "delete", str(todo_id))

    def suggestions(self, limit: int | None = None) -> Any:
        """Todos Bee suggested from conversations, waiting to be accepted."""
        return self._json("todos", "suggestions", *_opt("--limit", limit))

    def accept_suggestion(self, suggestion_id: int | str) -> Any:
        return self._json("todos", "accept-suggestion", str(suggestion_id))

    def dismiss_suggestion(self, suggestion_id: int | str) -> Any:
        return self._json("todos", "dismiss-suggestion", str(suggestion_id))


class _Conversations(_Group):
    def list(self, limit: int | None = None, cursor: str | None = None) -> Any:
        return self._json("conversations", "list", *_page(limit, cursor))

    def get(self, conversation_id: int | str) -> Any:
        """The full conversation, with `transcriptions[].utterances[]`."""
        return self._json("conversations", "get", str(conversation_id))

    def transcript(self, conversation_id: int | str, since: int | None = None) -> Any:
        """Just the utterances; since (epoch ms) returns only newer ones, for polling a live transcript."""
        return self._json("conversations", "transcript", str(conversation_id), *_opt("--since", since))

    def related(self, conversation_id: int | str, limit: int | None = None) -> Any:
        return self._json("conversations", "related", str(conversation_id), *_opt("--limit", limit))


class _Daily(_Group):
    def list(self, limit: int | None = None, cursor: str | None = None) -> Any:
        return self._json("daily", "list", *_page(limit, cursor))

    def get(self, daily_id: int | str) -> Any:
        return self._json("daily", "get", str(daily_id))

    def find(self, date: str) -> Any:
        """The daily summary for YYYY-MM-DD."""
        return self._json("daily", "find", date)


class _Journals(_Group):
    def list(self, limit: int | None = None, cursor: str | None = None) -> Any:
        return self._json("journals", "list", *_page(limit, cursor))

    def get(self, journal_id: int | str) -> Any:
        return self._json("journals", "get", str(journal_id))

    def search(self, query: str, limit: int | None = None) -> Any:
        return self._json("journals", "search", "--query", query, *_opt("--limit", limit))


class _Insights(_Group):
    def list(self, limit: int | None = None, cursor: str | None = None) -> Any:
        return self._json("insights", "list", *_page(limit, cursor))

    def get(self, insight_id: int | str) -> Any:
        return self._json("insights", "get", str(insight_id))


class _Locations(_Group):
    def clusters(self, limit: int | None = None, min_visits: int | None = None, visits: bool = False) -> Any:
        """Places grouped by how often they're visited; visits=True includes each visit."""
        return self._json("locations", "clusters", *_opt("--limit", limit), *_opt("--min-visits", min_visits),
                          *_opt("--visits", visits))

    def recent(self, start: str | None = None, end: str | None = None, limit: int | None = None) -> Any:
        """Recent individual visits, optionally between two dates."""
        return self._json("locations", "recent", *_opt("--from", start), *_opt("--to", end), *_opt("--limit", limit))

    def current(self) -> Any:
        return self._json("locations", "current")


class _Photos(_Group):
    def list(self, date: str | None = None, daily_id: int | None = None, limit: int | None = None) -> Any:
        """Photos synced from the phone's gallery, newest first."""
        return self._json("photos", "list", *_opt("--daily-id", daily_id), *_opt("--date", date), *_opt("--limit", limit))

    def get(self, photo_id: int | str, output: str) -> Any:
        """Download one photo to `output`."""
        return self._json("photos", "get", str(photo_id), "--output", output, timeout=120)
