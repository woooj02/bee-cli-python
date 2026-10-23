import subprocess

import pytest

from beecli import Bee, BeeError
from beecli.testing import FakeBee


@pytest.fixture
def fake():
    return FakeBee()


def test_every_call_adds_json_and_parses(fake):
    fake.reply("me", {"first_name": "Sita"})
    bee = Bee(runner=fake)
    assert bee.me() == {"first_name": "Sita"}
    assert fake.calls[-1] == ["bee", "me", "--json"]


@pytest.mark.parametrize("call, argv", [
    (lambda b: b.conversations.list(limit=5, cursor="c1"), ["conversations", "list", "--limit", "5", "--cursor", "c1"]),
    (lambda b: b.conversations.get(42), ["conversations", "get", "42"]),
    (lambda b: b.conversations.transcript(42, since=1700000000000), ["conversations", "transcript", "42", "--since", "1700000000000"]),
    (lambda b: b.conversations.related(42, limit=3), ["conversations", "related", "42", "--limit", "3"]),
    (lambda b: b.facts.list(unconfirmed=True), ["facts", "list", "--unconfirmed"]),
    (lambda b: b.facts.create("Kamala is my sister"), ["facts", "create", "--text", "Kamala is my sister"]),
    (lambda b: b.facts.update(7, confirmed=False), ["facts", "update", "7", "--confirmed", "false"]),
    (lambda b: b.facts.confirm(7), ["facts", "confirm", "7"]),
    (lambda b: b.facts.search("sister", limit=2), ["facts", "search", "--query", "sister", "--limit", "2"]),
    (lambda b: b.todos.create("Call Kamala", alarm_at="2026-10-19T09:00:00-06:00"),
     ["todos", "create", "--text", "Call Kamala", "--alarm-at", "2026-10-19T09:00:00-06:00"]),
    (lambda b: b.todos.update(3, completed=True, clear_alarm=True), ["todos", "update", "3", "--completed", "true", "--clear-alarm"]),
    (lambda b: b.todos.complete(3), ["todos", "complete", "3"]),
    (lambda b: b.todos.suggestions(limit=4), ["todos", "suggestions", "--limit", "4"]),
    (lambda b: b.todos.accept_suggestion(9), ["todos", "accept-suggestion", "9"]),
    (lambda b: b.daily.find("2026-10-18"), ["daily", "find", "2026-10-18"]),
    (lambda b: b.journals.search("garden"), ["journals", "search", "--query", "garden"]),
    (lambda b: b.insights.list(limit=2), ["insights", "list", "--limit", "2"]),
    (lambda b: b.locations.clusters(min_visits=2, visits=True), ["locations", "clusters", "--min-visits", "2", "--visits"]),
    (lambda b: b.locations.recent(start="2026-10-17", end="2026-10-18"), ["locations", "recent", "--from", "2026-10-17", "--to", "2026-10-18"]),
    (lambda b: b.photos.list(date="2026-10-18", limit=6), ["photos", "list", "--date", "2026-10-18", "--limit", "6"]),
    (lambda b: b.photos.get(5, "/tmp/p.jpg"), ["photos", "get", "5", "--output", "/tmp/p.jpg"]),
    (lambda b: b.today(context=True), ["today", "--context"]),
    (lambda b: b.activity(limit=10), ["activity", "--limit", "10"]),
    (lambda b: b.search("doctor", filter="conversations", sort="mostRecent", since=1),
     ["search", "--query", "doctor", "--since", "1", "--filter", "conversations", "--sort", "mostRecent"]),
    (lambda b: b.search("doctor", neural=True), ["search", "--query", "doctor", "--neural"]),
])
def test_arguments_match_the_cli(fake, call, argv):
    fake.reply(argv[0], {"ok": True})
    call(Bee(runner=fake))
    assert fake.calls[-1] == ["bee", *argv, "--json"]


def test_staging_and_binary(fake):
    fake.reply("me", {})
    Bee("/opt/bee", staging=True, runner=fake).me()
    assert fake.calls[-1] == ["/opt/bee", "--staging", "me", "--json"]


def test_errors_carry_the_cli_message(fake):
    fake.fail("conversations get", "Error: Not authenticated\nRun bee login", exit_code=2)
    with pytest.raises(BeeError, match="Run bee login") as info:
        Bee(runner=fake).conversations.get(1)
    assert info.value.exit_code == 2 and info.value.command[1:3] == ["conversations", "get"]


def test_not_json_and_empty(fake):
    fake.reply("facts delete", "")
    fake.reply("facts list", "# Facts\n- not json")
    bee = Bee(runner=fake)
    assert bee.facts.delete(1) is None
    with pytest.raises(BeeError, match="did not print JSON"):
        bee.facts.list()


def test_missing_binary_and_timeout():
    def missing(cmd, **kw):
        raise FileNotFoundError(cmd[0])

    def slow(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])

    with pytest.raises(BeeError, match="npm install -g @beeai/cli"):
        Bee(runner=missing).me()
    with pytest.raises(BeeError, match="timed out after 20s"):
        Bee(runner=slow).me()


def test_bad_combinations(fake):
    bee = Bee(runner=fake)
    with pytest.raises(ValueError):
        bee.search("x", neural=True, sort="relevance")
    with pytest.raises(ValueError):
        bee.todos.update(1, alarm_at="2026-10-19T09:00:00Z", clear_alarm=True)
    assert fake.calls == []


def test_fake_reply_can_be_a_function(fake):
    fake.reply("conversations get", lambda words: {"conversation": {"id": int(words[2])}})
    assert Bee(runner=fake).conversations.get(77) == {"conversation": {"id": 77}}


def test_logged_in(fake):
    assert Bee(runner=fake).logged_in() is False
    fake.reply("me", {"id": 1})
    assert Bee(runner=fake).logged_in() is True
