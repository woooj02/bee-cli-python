# bee-cli-python

A Python client for [Bee](https://www.bee.computer/), the wearable that turns your day into
transcripts, facts, todos and summaries.

Bee ships an official CLI ([`@beeai/cli`](https://github.com/bee-computer/bee-cli)) with a small
Node library inside it. Python developers had nothing. This package fills that gap, and covers more
of the CLI than the Node library does:

| | Node library in `@beeai/cli` 0.8.0 | **bee-cli-python** |
|---|---|---|
| me, today, now, changed, search | yes | yes (+ `today --context`, `activity`) |
| facts | list, get, create, update, confirm, delete | + **search** |
| todos | list, get, create, update, delete | + **complete, suggestions, accept/dismiss** |
| conversations | list, get | + **transcript --since** (live polling), **related** |
| daily summaries | list, get | + **find by date** |
| journals | list, get | + **search** |
| insights, locations, photos | – | **yes** |
| live events | data only; `event:` names dropped | **typed `Event`s**: the name is kept, or inferred from the payload |
| reconnects | – | backoff, `on_error` |
| testing without a device | – | **`FakeBee`** |

It runs the official binary with `--json`, exactly as the Node library does, so login, the API host
and certificates stay inside Bee's own client. No dependencies beyond Python 3.10+.

## Install

```bash
npm install -g @beeai/cli && bee login      # once; approve in the Bee app
pip install git+https://github.com/woooj02/bee-cli-python
python -m beecli doctor                     # PASS/FAIL: installed, logged in, recent data
```

## Use

```python
from beecli import Bee, utterances

bee = Bee()
print(bee.me())

convs = bee.conversations.list(limit=5)["conversations"]
for line in utterances(bee.conversations.get(convs[0]["id"])):
    print(line["at"], line["speaker"], line["text"])     # final transcript, in order, times in epoch ms

bee.facts.create("Kamala is my sister in Kathmandu")
bee.todos.create("Call Kamala", alarm_at="2026-10-19T09:00:00-06:00")
bee.search("doctor", filter="conversations", sort="mostRecent")
bee.locations.recent(start="2026-10-18")
bee.photos.list(date="2026-10-18", limit=6)
```

Every method returns the CLI's JSON as plain Python values. Failures raise `BeeError` with the
CLI's own message, the command and the exit code.

### Live events

```python
with bee.stream(["new-utterance", "update-conversation"]) as events:
    for ev in events:
        if ev.type == "new-utterance":
            print(ev.utterance["speaker"], ev.utterance["text"])
        elif ev.ended:                      # processed or has an end_time
            print("ready to read:", ev.conversation_id)
```

`bee stream --json` can print bare JSON lines (only each event's `data`). When it does, the type is
inferred from the payload's shape, following the CLI README's "Stream Events" section, and
`ev.exact` is `False`. `todo-created` and `todo-updated` carry identical payloads, so those two come
back as the family name `"todo"`. The stream reconnects with exponential backoff until `close()`.
`python -m beecli stream new-utterance` prints events as they arrive.

### Helpers

- `utterances(conversation)` returns the transcript in spoken order. It prefers the final
  transcription over the realtime one, skips empty lines, and adds `at` in epoch ms.
- `to_ms(x)` converts epoch ms, epoch seconds, digit strings or ISO dates to epoch ms. Bee uses all
  of these.
- `speakers(items)`, `word_count(items)`, and `unwrap(payload, "conversation")`.

### Testing your app without a Bee

```python
from beecli import Bee
from beecli.testing import FakeBee

fake = FakeBee()
fake.reply("conversations list", {"conversations": [{"id": 1}]})
fake.reply("todos create", lambda argv: {"id": 9, "text": argv[argv.index("--text") + 1]})
fake.fail("facts list", "Not authenticated")
fake.stream_output('{"utterance": {"text": "hello", "speaker": "speaker_1"}}\n')

bee = Bee(runner=fake)
bee.todos.create("Call Kamala")
assert fake.calls[-1][:3] == ["bee", "todos", "create"]
events = bee.stream(popen=fake.popen, reconnect=False)
```

## Develop

```bash
python -m venv venv && ./venv/bin/pip install -e ".[dev]" && ./venv/bin/pytest -q
```

The command arguments mirror `createDataApi` in `@beeai/cli/dist/lib` and the command list in
the CLI README (version 0.8.0). If the CLI adds a command, add a method and a row to
`tests/test_client.py`.

Built during the [Build, Ship, Shape](https://amazonappdev2026.devpost.com/) hackathon for
[Memory Lane](https://github.com/woooj02/memory-lane). Not affiliated with Bee or Amazon.

## License

MIT
