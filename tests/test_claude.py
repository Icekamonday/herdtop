import os
from pathlib import Path

import pytest
from builder import NOW, Transcript, payload, register

from herdtop.readers.claude import ClaudeReader, clean, prompt_of


@pytest.fixture
def reader(home: Path) -> ClaudeReader:
    return ClaudeReader()


def test_a_call_counts_once_across_a_resume_and_its_blocks(
        home: Path, reader: ClaudeReader) -> None:
    t = Transcript(home, "/work/a")
    t.user("go", at=NOW)
    # One answer in two records: the last one holds the final output.
    t.assistant(None, at=NOW + 1, request="r1", message="m1", input=10, output=1)
    t.assistant("done", at=NOW + 2, request="r1", message="m1", input=10, output=50)
    copy = list(t.records)
    t.records += copy
    t.assistant("again", at=NOW + 60, request="r2", message="m2", read=100,
                output=5)
    digest = reader.digest(t.write())
    counts = digest.tally.models["claude-opus-4-1-20250805"]
    assert digest.tally.calls == 2
    assert (counts.input, counts.output, counts.read) == (10, 55, 100)


def test_a_call_with_no_tokens_does_not_count(
        home: Path, reader: ClaudeReader) -> None:
    t = Transcript(home, "/work/a").user("go").assistant("interrupted")
    assert reader.digest(t.write()).tally.calls == 0


def test_the_tally(home: Path, reader: ClaudeReader) -> None:
    t = Transcript(home, "/work/a").user("go")
    t.assistant(at=NOW, write_1h=5000, output=10, thinking=4)
    t.assistant(at=NOW + 60, write_5m=100, read=5000, output=10)
    # A gap of an hour is two sittings, and the cache was cold again.
    t.assistant(at=NOW + 3660, write_5m=6000, read=0, output=10,
                model="claude-sonnet-4-5-20250929")
    t.assistant(at=NOW + 3720, input=3, write_5m=10, read=6000, output=500,
                model="claude-sonnet-4-5-20250929")
    tally = reader.digest(t.write()).tally
    assert tally.calls == 4
    assert tally.restarts == 2
    assert tally.worked == 120
    assert tally.last_call == NOW + 3720
    assert tally.last_context == 3 + 10 + 6000
    assert tally.last_ttl == "5m"
    assert tally.model == "claude-sonnet-4-5-20250929"
    assert tally.models["claude-opus-4-1-20250805"].thinking == 4


def test_an_early_rename_wins_over_a_late_generated_title(
        home: Path, reader: ClaudeReader) -> None:
    t = Transcript(home, "/work/a").user("go").custom_title("first name")
    t.custom_title("my name")
    for i in range(3000):
        t.assistant("x" * 40, at=NOW + i)
    t.ai_title("generated")
    digest = reader.digest(t.write())
    assert (digest.title, digest.title_set) == ("my name", True)


def test_the_last_generated_title_wins(home: Path, reader: ClaudeReader) -> None:
    t = Transcript(home, "/work/a").user("go").ai_title("one").ai_title("two")
    digest = reader.digest(t.write())
    assert (digest.title, digest.title_set) == ("two", False)


def test_without_a_title_the_first_prompt_names_the_session(
        home: Path, reader: ClaudeReader) -> None:
    t = Transcript(home, "/work/a")
    t.user("<system-reminder>context</system-reminder>", isMeta=True)
    t.user("fix the parser\nthen the tests").assistant("ok")
    digest = reader.digest(t.write())
    assert (digest.title, digest.first_prompt) == (None, "fix the parser")


def test_the_working_directory_comes_from_the_file(
        home: Path, reader: ClaudeReader) -> None:
    t = Transcript(home, "/a/b.c", project="-a-b-c").user("go")
    assert reader.digest(t.write()).cwd == "/a/b.c"


def test_the_last_answer(home: Path, reader: ClaudeReader) -> None:
    t = Transcript(home, "/work/a").user("go", at=NOW)
    t.assistant("answer", at=NOW + 10)
    t.assistant(None, at=NOW + 20, output=3)
    t.custom_title("named later")
    assert reader.digest(t.write()).last_answer == NOW + 10


def test_a_parked_transcript_names_its_job(
        home: Path, reader: ClaudeReader) -> None:
    t = Transcript(home, "/work/a").user("go").assistant().continued_in("job-id")
    digest = reader.digest(t.write())
    assert digest.continued_in == "job-id"
    assert digest.last_record == t.records[-2]["uuid"]


def test_a_broken_line_is_skipped(home: Path, reader: ClaudeReader) -> None:
    path = Transcript(home, "/work/a").user("go").assistant(output=1).write()
    with path.open("a") as f:
        f.write('{"type": "assistant", "trunc\n[1]\n')
    assert reader.digest(path).tally.calls == 1


@pytest.mark.parametrize(("typed", "prompt"), [
    (("<command-message>x</command-message>\n<command-name>/review</command-name>"
      "\n<command-args>12 --fast</command-args>"), "/review 12 --fast"),
    ("<command-name>clear</command-name>", "/clear"),
    ("<bash-input>ls -l</bash-input>", "! ls -l"),
    ('<pasted_content id="1">the log</pasted_content id="1">\nwhy?',
     "the log\nwhy?"),
    ("<ide_selection>lines 1-3</ide_selection>explain this", "explain this"),
    ("[Image #2] what is it", "what is it"),
    ("look<system-reminder>a hint</system-reminder>", "look"),
    ("[Request interrupted by user]", ""),
    ("<local-command-stdout>out</local-command-stdout>", ""),
])
def test_what_the_client_adds_is_removed(typed: str, prompt: str) -> None:
    assert clean(typed) == prompt


@pytest.mark.parametrize("extra", [
    {"isMeta": True},
    {"isCompactSummary": True},
    {"origin": {"kind": "task-notification"}},
])
def test_records_that_no_person_typed(extra: dict) -> None:
    record = {"type": "user", "message": {"content": "text"}, **extra}
    assert prompt_of(record) is None


def test_a_tool_result_is_no_prompt() -> None:
    content = [{"type": "tool_result", "content": "output"}]
    assert prompt_of({"type": "user", "message": {"content": content}}) is None
    assert prompt_of({"type": "user", "origin": {"kind": "human"},
                      "message": {"content": [{"type": "text", "text": "hi"}]}}) == "hi"


def test_the_exchanges(home: Path, reader: ClaudeReader) -> None:
    t = Transcript(home, "/work/a")
    t.user("one", at=NOW).assistant("first", at=NOW + 1)
    t.assistant("last", at=NOW + 2)
    t.user([{"type": "tool_result", "content": "x"}], at=NOW + 3)
    t.user("two", at=NOW + 4)
    t.records += list(t.records)
    exchanges = reader.exchanges(t.write())
    assert [(e.prompt, e.answer) for e in exchanges] == [("one", "last"),
                                                         ("two", "")]
    assert exchanges[0].time == NOW


def test_the_search_reads_prompts_and_agent_prompts_not_answers(
        home: Path, reader: ClaudeReader) -> None:
    t = Transcript(home, "/work/a").user("Fix the Parser")
    t.assistant("the lexer is fine", tool_prompt="check the Été module")
    path = t.write()
    assert reader.matches(path, ["parser", "fix"])
    assert reader.matches(path, ["été"])
    assert not reader.matches(path, ["lexer"])
    assert not reader.matches(path, ["absent"])
    assert not reader.matches(home / "gone.jsonl", ["fix"])


def test_the_sidecar_size(home: Path, reader: ClaudeReader) -> None:
    path = Transcript(home, "/work/a").user("go").write()
    sidecar = path.with_suffix("")
    (sidecar / "subagents").mkdir(parents=True)
    (sidecar / "subagents" / "agent-1.jsonl").write_bytes(b"x" * 100)
    (sidecar / "tool-results").mkdir()
    (sidecar / "tool-results" / "r.txt").write_bytes(b"x" * 20)
    assert reader.sidecar_size(path) == 120
    assert reader.sidecar_size(home / "none.jsonl") == 0


def test_a_live_entry(home: Path, reader: ClaudeReader) -> None:
    register(home, "s1", kind="bg", parkedJobId="abcd1234")
    liveness = reader.live()
    assert liveness.readable
    live = liveness.sessions["s1"]
    assert (live.pid, live.kind, live.parked_job) == (os.getpid(), "bg",
                                                      "abcd1234")


def test_an_entry_whose_pid_was_reused_is_not_live(
        home: Path, reader: ClaudeReader) -> None:
    register(home, "s1", proc_start="1")
    liveness = reader.live()
    assert liveness.readable
    assert liveness.sessions == {}


def test_an_entry_whose_process_is_gone_is_not_live(
        home: Path, reader: ClaudeReader) -> None:
    register(home, "s1", pid=2**22 + 1, proc_start="5", domain=None)
    assert not reader.live().readable


def test_an_entry_of_another_namespace_proves_nothing(
        home: Path, reader: ClaudeReader) -> None:
    register(home, "s1", domain="linux:other:pid:[1]")
    liveness = reader.live()
    assert (liveness.readable, liveness.sessions) == (False, {})


def test_a_broken_registry_file_is_skipped(home: Path, reader: ClaudeReader) -> None:
    sessions = home / ".claude" / "sessions"
    sessions.mkdir(parents=True)
    (sessions / "1.json").write_text("{")
    (sessions / "2.json").write_text('{"pid": "x"}')
    assert reader.live().sessions == {}


def test_the_cache_of_a_session(home: Path, reader: ClaudeReader) -> None:
    payload(home, "s1", ttl="1h", expires_at=NOW + 600, recache=1234)
    cache = reader.cache("s1")
    assert cache is not None
    assert (cache.ttl, cache.expires_at, cache.recache_tokens) == ("1h", NOW + 600,
                                                                   1234)
    assert reader.cache("none") is None


def test_the_newest_payload_gives_the_gauges(home: Path, reader: ClaudeReader) -> None:
    payload(home, "old", five_hour=(90, NOW + 100), mtime=NOW - 100)
    payload(home, "new", five_hour=(12, NOW + 100), seven_day=(40, NOW - 1),
            mtime=NOW)
    gauges = reader.gauges(NOW)
    assert gauges is not None
    assert gauges.five_hour is not None and gauges.five_hour.used == 12
    assert gauges.seven_day is None


def test_no_payload_gives_no_gauges(home: Path, reader: ClaudeReader) -> None:
    assert reader.gauges(NOW) is None
    payload(home, "s1")
    assert reader.gauges(NOW) is None


def test_the_store_is_found_by_its_glob(home: Path, reader: ClaudeReader) -> None:
    a = Transcript(home, "/work/a").user("go").write()
    (home / ".claude" / "projects" / "-x" / "s" / "subagents").mkdir(parents=True)
    assert reader.transcripts() == [a]
    assert reader.project(a) == "-work-a"


def test_the_total_of_the_cache_writes_is_the_authority(
        home: Path, reader: ClaudeReader) -> None:
    t = Transcript(home, "/work/a").user("go").assistant()
    t.records[-1]["message"]["usage"]["cache_creation"] = {
        "ephemeral_1h_input_tokens": 1282, "ephemeral_5m_input_tokens": 0}
    t.assistant(write_1h=30, write_5m=20, output=1)
    del t.records[-1]["message"]["usage"]["cache_creation"]
    tally = reader.digest(t.write()).tally
    counts = tally.models["claude-opus-4-1-20250805"]
    assert tally.calls == 1
    assert (counts.write_5m, counts.write_1h) == (50, 0)
