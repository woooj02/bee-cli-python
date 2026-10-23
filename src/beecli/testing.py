"""A fake Bee for tests: no device, no account, no network.

    from beecli import Bee
    from beecli.testing import FakeBee

    fake = FakeBee()
    fake.reply("conversations list", {"conversations": [{"id": 1}]})
    bee = Bee(runner=fake)
    assert bee.conversations.list()["conversations"][0]["id"] == 1
    assert fake.calls[-1][:3] == ["bee", "conversations", "list"]

Replies are matched on the leading words of the command ("todos create"
matches `bee todos create --text ...`); the longest match wins. A reply can be
a value (printed as JSON), a BeeFailure, or a function of the argument list.
`fake.popen` plays canned stream output for `Bee.stream(..., popen=fake.popen)`.
"""

from __future__ import annotations

import io
import json
import subprocess
from dataclasses import dataclass
from typing import Any


@dataclass
class BeeFailure:
    stderr: str = "error"
    exit_code: int = 1


class FakeBee:
    def __init__(self):
        self.replies: dict[str, Any] = {}
        self.calls: list[list[str]] = []
        self.streams: list[list[str]] = []

    def reply(self, command: str, value: Any) -> "FakeBee":
        self.replies[command] = value
        return self

    def fail(self, command: str, stderr: str = "error", exit_code: int = 1) -> "FakeBee":
        return self.reply(command, BeeFailure(stderr, exit_code))

    def stream_output(self, *chunks: str) -> "FakeBee":
        """Queue one connection's worth of stdout for the next `bee stream`."""
        self.streams.append(list(chunks))
        return self

    def _words(self, cmd: list[str]) -> list[str]:
        return [a for a in cmd[1:] if a != "--staging"]

    def __call__(self, cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
        self.calls.append(list(cmd))
        words = self._words(cmd)
        key = max((k for k in self.replies if words[: len(k.split())] == k.split()), key=len, default=None)
        if key is None:
            return subprocess.CompletedProcess(cmd, 1, "", f"FakeBee: no reply for {' '.join(words)}")
        value = self.replies[key]
        if callable(value):
            value = value(words)
        if isinstance(value, BeeFailure):
            return subprocess.CompletedProcess(cmd, value.exit_code, "", value.stderr)
        out = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return subprocess.CompletedProcess(cmd, 0, out, "")

    def popen(self, cmd: list[str], **kwargs) -> "_FakeProc":
        self.calls.append(list(cmd))
        chunks = self.streams.pop(0) if self.streams else []
        return _FakeProc("".join(chunks))


class _FakeProc:
    def __init__(self, out: str, stderr: str = "disconnected"):
        self.stdout = io.StringIO(out)
        self.stderr = io.StringIO(stderr)
        self.returncode = 1

    def poll(self):
        return self.returncode

    def terminate(self):
        pass

    def kill(self):
        pass

    def wait(self, timeout=None):
        return self.returncode
