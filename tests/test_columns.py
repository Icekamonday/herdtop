import pytest
from builder import NOW, session

from herdtop import columns
from herdtop.columns import COLUMNS, choose, group_cell, session_cell
from herdtop.model import CacheState, Call

BY_NAME = {c.name: c for c in COLUMNS}


@pytest.mark.parametrize(("seconds", "text"), [
    (-5, "now"), (59, "now"), (60, "1m"), (3599, "59m"), (3600, "1h"),
    (86399, "23h"), (86400, "1d"), (29 * 86400, "29d"), (30 * 86400, "4w"),
    (400 * 86400, "1y"),
])
def test_age(seconds: float, text: str) -> None:
    assert columns.age(seconds) == text


@pytest.mark.parametrize(("seconds", "text"), [
    (0, "0m"), (59 * 60, "59m"), (3600 + 5 * 60, "1h05"), (12 * 3600, "12h"),
    (150 * 3600, "6d"),
])
def test_duration(seconds: float, text: str) -> None:
    assert columns.duration(seconds) == text


@pytest.mark.parametrize(("n", "text"), [
    (10, "10B"), (2048, "2K"), (5 * 2**20, "5.0M"), (123 * 2**20, "123M"),
    (3 * 2**30, "3.0G"), (2**50, "1024T"),
])
def test_size(n: int, text: str) -> None:
    assert columns.size(n) == text


@pytest.mark.parametrize(("n", "text"), [
    (999, "999"), (1500, "2k"), (212_000, "212k"), (999_499, "999k"),
    (1_200_000, "1.2M"),
])
def test_tokens(n: int, text: str) -> None:
    assert columns.tokens(n) == text


def test_short_model() -> None:
    assert columns.short_model("claude-opus-4-1-20250805") == "opus-4-1"
    assert columns.short_model("claude-fable-5-1") == "fable-5-1"
    assert columns.short_model(None) == "-"


def names(found) -> list[str]:
    return [c.name for c in found]


def test_the_columns_drop_by_rank_and_keep_their_order() -> None:
    assert names(choose(200, grouped=True)) == [c.name for c in COLUMNS]
    assert names(choose(200, grouped=False)) == [
        c.name for c in COLUMNS if c.name != "sess"]
    assert names(choose(7, grouped=True)) == ["ctx"]
    # cost does not fit in what ctx leaves, and the narrower cache does.
    assert names(choose(13, grouped=True)) == ["ctx", "cache"]
    assert names(choose(19, grouped=True)) == ["cost", "ctx"]
    assert names(choose(31, grouped=True)) == ["sess", "cost", "ctx", "cache"]
    assert names(choose(0, grouped=True)) == []


def calls(*contexts: int, at: float = NOW, ttl: str = "5m") -> list[Call]:
    found = []
    for i, context in enumerate(contexts):
        write = {"write_1h" if ttl == "1h" else "write_5m": 10}
        found.append(Call(time=at + i, model="claude-opus-4-1",
                          read=context - 10, output=1, **write))
    return found


@pytest.mark.parametrize(("context", "text", "style", "plain"), [
    (100_000, "100k", "", "100k"),
    (150_000, "150k", "warn", "150k▲"),
    (400_000, "400k", "alarm", "400k▲▲"),
])
def test_the_context_band_has_a_colour_and_a_glyph(
        context: int, text: str, style: str, plain: str) -> None:
    s = session(calls=calls(context))
    assert session_cell(BY_NAME["ctx"], s, NOW, color=True) == (text, style)
    assert session_cell(BY_NAME["ctx"], s, NOW, color=False) == (plain, style)


def test_the_cache_clock() -> None:
    s = session(calls=calls(1000, at=NOW - 60))
    assert session_cell(BY_NAME["cache"], s, NOW, True) == ("4m", "warm")
    assert session_cell(BY_NAME["cache"], s, NOW + 300, True) == ("cold", "")
    s = session(calls=calls(1000, at=NOW, ttl="1h"))
    assert s.cache_ends == NOW + 3600
    s.cache = CacheState(ttl="5m")
    assert s.cache_ends == NOW + 300
    s.cache = CacheState(ttl="5m", expires_at=NOW + 1000)
    assert s.cache_ends == NOW + 1000


def test_a_session_without_a_call() -> None:
    s = session()
    cells = {c.name: session_cell(c, s, NOW, True)[0] for c in COLUMNS}
    assert cells == {"sess": "", "ran": "-", "cost": "-", "req": "-",
                     "size": "1000B", "ctx": "-", "cache": "-", "model": "-"}
    assert s.cache_ends is None


def test_a_session_row() -> None:
    s = session(calls=calls(1000, 2000, at=NOW - 120))
    cells = {c.name: session_cell(c, s, NOW, True)[0] for c in COLUMNS}
    assert cells == {"sess": "", "ran": "0m", "cost": "-", "req": "2",
                     "size": "1000B", "ctx": "2k", "cache": "4m",
                     "model": "opus-4-1"}


def test_a_fold_row_sums_the_second_block_only() -> None:
    a = session(calls=calls(1000, 1000), size=2048)
    b = session(calls=calls(1000), size=2048)
    cells = {c.name: group_cell(c, [a, b])[0] for c in COLUMNS}
    assert cells == {"sess": "2", "ran": "0m", "cost": "-", "req": "3",
                     "size": "4K", "ctx": "-", "cache": "-", "model": "-"}
    assert group_cell(BY_NAME["sess"], [a]) == ("", "")
