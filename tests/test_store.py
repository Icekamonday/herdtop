import os
from pathlib import Path

from builder import NOW, Transcript, payload, register

from herdtop import store
from herdtop.readers.claude import ClaudeReader


def load(now: float = NOW) -> store.Store:
    return store.load([ClaudeReader()], now)


def test_one_id_in_two_projects_gives_two_rows(home: Path) -> None:
    a = Transcript(home, "/work/a", sid="same").user("go").write()
    b = Transcript(home, "/work/b", sid="same").user("go").write()
    sessions = load().sessions
    assert sorted(s.path for s in sessions) == sorted([a, b])
    assert all(s.twin for s in sessions)


def test_two_directories_with_one_slug_keep_their_own(home: Path) -> None:
    Transcript(home, "/a/b.c", project="-a-b-c").user("go").write()
    Transcript(home, "/a/b-c", project="-a-b-c").user("go").write()
    assert sorted(s.cwd for s in load().sessions) == ["/a/b-c", "/a/b.c"]
    assert not any(s.twin for s in load().sessions)


def parked(home: Path) -> tuple[Transcript, Transcript]:
    old = Transcript(home, "/work/a").user("go").assistant(at=NOW, output=5)
    job = Transcript(home, "/work/a")
    job.records = list(old.records)
    job.user("more", at=NOW + 10).assistant(at=NOW + 20, output=5)
    old.continued_in(job.sid)
    return old, job


def test_a_parked_conversation_is_listed_once(home: Path) -> None:
    old, job = parked(home)
    old_size = old.write().stat().st_size
    job_size = job.write().stat().st_size
    [session] = load().sessions
    assert session.id == job.sid
    assert session.tally.calls == 2
    assert session.size == old_size + job_size
    assert session.parked == [old.path]


def test_a_chain_of_parks_ends_on_the_last_job(home: Path) -> None:
    old, job = parked(home)
    last = Transcript(home, "/work/a")
    last.records = list(job.records)
    job.continued_in(last.sid)
    for t in (old, job, last):
        t.write()
    [session] = load().sessions
    assert session.id == last.sid
    assert sorted(session.parked) == sorted([old.path, job.path])


def test_a_job_that_lacks_the_old_records_hides_nothing(home: Path) -> None:
    old, job = parked(home)
    job.records = job.records[2:]
    old.write()
    job.write()
    assert len(load().sessions) == 2


def test_the_age_is_the_last_answer_not_the_file_time(home: Path) -> None:
    t = Transcript(home, "/work/a").user("go", at=NOW - 3600)
    t.assistant("answer", at=NOW - 3000)
    t.custom_title("renamed now").write(mtime=NOW)
    silent = Transcript(home, "/work/b").user("go", at=NOW - 50)
    silent.write(mtime=NOW - 10)
    by_dir = {s.cwd: s for s in load().sessions}
    assert by_dir["/work/a"].answered == NOW - 3000
    assert by_dir["/work/b"].answered == NOW - 10


def test_a_transcript_that_goes_breaks_nothing(home: Path) -> None:
    kept = Transcript(home, "/work/a").user("go").write()
    gone = Transcript(home, "/work/b").user("go").write()

    class Racing(ClaudeReader):
        def transcripts(self) -> list[Path]:
            found = super().transcripts()
            gone.unlink()
            return found

    sessions = store.load([Racing()], NOW).sessions
    assert [s.path for s in sessions] == [kept]


def test_a_live_session(home: Path) -> None:
    t = Transcript(home, "/work/a").user("go")
    t.write()
    register(home, t.sid)
    loaded = load()
    assert loaded.registry_readable
    [session] = loaded.sessions
    assert session.live is not None and session.open


def test_an_unreadable_registry_leaves_recent_transcripts_maybe_open(
        home: Path) -> None:
    Transcript(home, "/work/a").user("go").write(mtime=NOW - 30)
    Transcript(home, "/work/b").user("go").write(mtime=NOW - 600)
    loaded = load()
    assert not loaded.registry_readable
    assert {s.cwd: s.maybe_open for s in loaded.sessions} == {
        "/work/a": True, "/work/b": False}


def test_a_payload_older_than_the_last_call_keeps_only_its_ttl(
        home: Path) -> None:
    t = Transcript(home, "/work/a").user("go")
    t.assistant(at=NOW, write_5m=100, output=1).write()
    payload(home, t.sid, ttl="1h", expires_at=NOW - 60, recache=999)
    [session] = load().sessions
    assert session.cache is not None
    assert (session.cache.ttl, session.cache.expires_at) == ("1h", None)
    assert session.context == 100
    assert session.cache_ends == NOW + 3600


def test_a_fresh_payload_gives_the_context(home: Path) -> None:
    t = Transcript(home, "/work/a").user("go")
    t.assistant(at=NOW, write_5m=100, output=1).write()
    payload(home, t.sid, ttl="5m", expires_at=NOW + 900, recache=999)
    [session] = load().sessions
    assert session.context == 999
    assert session.cache_ends == NOW + 900


def test_the_search(home: Path) -> None:
    a = Transcript(home, "/work/a").user("fix the parser").write()
    Transcript(home, "/work/b").user("write the docs").write()
    assert load().search(["parser"]) == {a}


def test_the_size_of_the_store(home: Path) -> None:
    a = Transcript(home, "/work/a").user("go").write()
    (a.with_suffix("") / "tool-results").mkdir(parents=True)
    (a.with_suffix("") / "tool-results" / "r").write_bytes(b"x" * 10)
    assert load().size == os.path.getsize(a) + 10
