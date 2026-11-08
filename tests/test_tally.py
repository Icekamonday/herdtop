import json
from pathlib import Path

import pytest
from builder import NOW, Transcript

from herdtop.model import Digest
from herdtop.readers.claude import ClaudeReader
from herdtop.tally import SHAPE, TallyCache


class Counting(ClaudeReader):
    def __init__(self) -> None:
        super().__init__()
        self.reads = 0

    def digest(self, path: Path) -> Digest:
        self.reads += 1
        return super().digest(path)


@pytest.fixture
def transcript(home: Path) -> Transcript:
    t = Transcript(home, "/work/a").user("go").custom_title("named")
    t.assistant(at=NOW, write_1h=10, output=3)
    t.write()
    return t


def run(reader: Counting, path: Path) -> Digest:
    cache = TallyCache()
    digest = cache.digest(reader, path, path.stat())
    cache.save()
    return digest


def test_a_second_run_reads_the_cache(transcript: Transcript) -> None:
    reader = Counting()
    first = run(reader, transcript.path)
    second = run(reader, transcript.path)
    assert reader.reads == 1
    assert second == first
    assert second.tally.models == first.tally.models


def test_a_grown_transcript_is_read_again(transcript: Transcript) -> None:
    reader = Counting()
    run(reader, transcript.path)
    transcript.assistant(at=NOW + 10, read=10, output=1).write()
    assert run(reader, transcript.path).tally.calls == 2
    assert reader.reads == 2


def test_a_cache_of_another_shape_is_rebuilt(transcript: Transcript) -> None:
    reader = Counting()
    run(reader, transcript.path)
    cache = TallyCache()
    data = json.loads(cache.path.read_text())
    data["shape"] = SHAPE + 1
    cache.path.write_text(json.dumps(data))
    run(reader, transcript.path)
    assert reader.reads == 2


def test_a_broken_entry_is_read_again(transcript: Transcript) -> None:
    reader = Counting()
    run(reader, transcript.path)
    cache = TallyCache()
    data = json.loads(cache.path.read_text())
    for entry in data["entries"].values():
        entry["digest"] = {"id": "x"}
    cache.path.write_text(json.dumps(data))
    assert run(reader, transcript.path).title == "named"
    assert reader.reads == 2


def test_a_broken_cache_file_is_ignored(transcript: Transcript) -> None:
    cache = TallyCache()
    cache.path.parent.mkdir(parents=True)
    cache.path.write_text("{")
    assert run(Counting(), transcript.path).title == "named"


def test_a_transcript_that_is_gone_leaves_the_cache(
        home: Path, transcript: Transcript) -> None:
    other = Transcript(home, "/work/b").user("go").write()
    reader = Counting()
    cache = TallyCache()
    for path in (transcript.path, other):
        cache.digest(reader, path, path.stat())
    cache.save()
    run(reader, transcript.path)
    assert len(json.loads(TallyCache().path.read_text())["entries"]) == 1


def test_an_unwritable_cache_costs_only_time(
        home: Path, transcript: Transcript) -> None:
    blocker = home / "cache"
    blocker.write_text("a file where the directory should be")
    reader = Counting()
    run(reader, transcript.path)
    run(reader, transcript.path)
    assert reader.reads == 2
