import pytest

from beecli import Bee, BeeError, infer_type, parse_lines
from beecli.testing import FakeBee


def test_bare_json_lines_are_typed_by_shape():
    lines = [
        '{"utterance": {"text": "नमस्ते", "speaker": "speaker_1"}, "conversation_uuid": "u1"}\n',
        '{"conversation": {"id": 5, "uuid": "u1", "state": "processing"}}\n',
        '{"conversation": {"id": 5, "state": "processed", "short_summary": "Call"}}\n',
        '{"conversation_id": 5, "short_summary": "Call with sister"}\n',
        '{"conversation_id": 5, "location": {"latitude": 39.7, "longitude": -104.9}}\n',
        '{"conversation": {"id": 5, "title": "x"}}\n',
        '{"todo": {"id": 1, "text": "Call", "completed": false, "alarmAt": 1}}\n',
        '{"todo": {"id": 1}}\n',
        '{"journalId": 3, "text": "partial"}\n',
        '{"journalId": 3, "reason": "user"}\n',
        '{"journal": {"id": 3, "state": "processed"}}\n',
        "not json\n",
    ]
    evs = list(parse_lines(lines))
    assert [e.type for e in evs] == [
        "new-utterance", "new-conversation", "update-conversation", "update-conversation-summary",
        "update-location", "delete-conversation", "todo", "todo-deleted", "journal-text", "journal-deleted", "journal"]
    assert not any(e.exact for e in evs)
    assert evs[0].utterance["text"] == "नमस्ते" and evs[0].conversation_id == "u1"
    assert evs[2].ended and not evs[1].ended


def test_sse_blocks_keep_the_event_name():
    lines = ["event: connected\n", "data: \n", "\n",
             ": keep-alive\n",
             "event: todo-updated\n", 'data: {"todo": {"id": 1, "completed": true}}\n', "\n",
             "id: 9\n", "event: new-utterance\n", 'data: {"utterance":\n', 'data: {"text": "hi", "speaker": "s1"}}\n', "\n",
             "event: update-conversation\n", 'data: {"conversation": {"id": 2, "end_time": 1700000000000}}\n']
    evs = list(parse_lines(lines))
    assert [(e.type, e.exact) for e in evs] == [("connected", True), ("todo-updated", True),
                                               ("new-utterance", True), ("update-conversation", True)]
    assert evs[2].utterance == {"text": "hi", "speaker": "s1"}
    assert evs[3].ended and evs[3].conversation_id == 2


def test_infer_type_edges():
    assert infer_type({}) == "connected"
    assert infer_type("x") == "connected"
    assert infer_type({"something": 1}) == "unknown"


def test_stream_reconnects_with_backoff():
    fake = FakeBee()
    fake.stream_output('{"utterance": {"text": "one", "speaker": "a"}}\n')
    fake.stream_output('{"utterance": {"text": "two", "speaker": "a"}}\n')
    bee = Bee(runner=fake)
    errors, waits = [], []
    stream = bee.stream(["new-utterance"], popen=fake.popen, on_error=errors.append, backoff=(0.01, 0.02))
    stream._stop.wait = lambda d: waits.append(d)  # don't sleep in tests
    got = []
    for ev in stream:
        got.append(ev.utterance["text"])
        if len(got) == 2:
            stream.close()
    assert got == ["one", "two"]
    assert fake.calls[0] == ["bee", "stream", "--json", "--types", "new-utterance"]
    assert stream.connections == 2 and errors == ["disconnected"] and waits == [0.01]


def test_stream_without_reconnect_stops():
    fake = FakeBee().stream_output("")
    assert list(Bee(runner=fake).stream(popen=fake.popen, reconnect=False)) == []


def test_stream_missing_binary():
    def missing(cmd, **kw):
        raise FileNotFoundError(cmd[0])

    with pytest.raises(BeeError, match="not found"):
        list(Bee().stream(popen=missing))
