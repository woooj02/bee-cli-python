"""python -m beecli doctor    check the CLI, login and recent data
python -m beecli stream    print live events with their types"""

from __future__ import annotations

import json
import sys

from . import Bee, BeeError, utterances, word_count


def doctor(bee: Bee) -> int:
    ok = True

    def line(passed: bool, what: str, detail: str = "") -> None:
        nonlocal ok
        ok &= passed
        print(f"{'PASS' if passed else 'FAIL'}  {what}{('  ' + detail) if detail else ''}")

    line(bee.available(), "bee CLI installed", "" if bee.available() else "npm install -g @beeai/cli")
    if not bee.available():
        return 1
    try:
        me = bee.me() or {}
        line(True, "logged in", str(me.get("first_name") or me.get("email") or ""))
    except BeeError as exc:
        line(False, "logged in", f"{exc}  (run: bee login)")
        return 1
    try:
        convs = (bee.conversations.list(limit=5) or {}).get("conversations", [])
        line(bool(convs), "recent conversations", f"{len(convs)} found" if convs else "record something first")
        if convs:
            items = utterances(bee.conversations.get(convs[0]["id"]))
            line(bool(items), "newest transcript", f"{len(items)} lines, {word_count(items)} words")
    except BeeError as exc:
        line(False, "conversations", str(exc))
    for name, call in (("facts", lambda: bee.facts.list(limit=1)), ("daily summaries", lambda: bee.daily.list(limit=1))):
        try:
            call()
            line(True, name)
        except BeeError as exc:
            line(False, name, str(exc))
    return 0 if ok else 1


def main(argv: list[str]) -> int:
    bee = Bee()
    cmd = argv[0] if argv else "doctor"
    if cmd == "doctor":
        return doctor(bee)
    if cmd == "stream":
        types = argv[1].split(",") if len(argv) > 1 else ["all"]
        with bee.stream(types, on_error=lambda m: print(f"(reconnecting: {m})", file=sys.stderr)) as events:
            for ev in events:
                guess = "" if ev.exact else " (inferred)"
                print(f"{ev.type}{guess}: {json.dumps(ev.data, ensure_ascii=False)[:160]}", flush=True)
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(130)
