import time

import pytest
from builder import NOW, session

from herdtop import render
from herdtop.columns import COLUMNS, DECIDE, HAND_OFF
from herdtop.model import Call, Gauges, Live, Window
from herdtop.store import Store
from herdtop.text import width
from herdtop.view import ViewState, rows


def call(context: int, at: float = NOW - 60) -> list[Call]:
    return [Call(time=at, model="claude-opus-4-1", read=context - 10,
                 write_5m=10, output=1)]


@pytest.fixture
def store() -> Store:
    return Store(sessions=[
        session("[herdr] a long title " + "x" * 80, "/work/herdr",
                calls=call(HAND_OFF)),
        session("generated title", "/work/herdr", named=False,
                answered=NOW - 7200, calls=call(DECIDE, at=NOW - 7200)),
        session("open one", "/work/top", live=Live(pid=1, kind="interactive"),
                answered=NOW - 30, calls=call(5000)),
    ], gauges=Gauges(five_hour=Window(3, NOW + 100), seven_day=Window(74, NOW + 9)))


def dump(store: Store, size: int, **state) -> list[str]:
    view = ViewState(all_open=True, **state)
    return render.once(store, view, rows(store.sessions, view), size,
                       NOW).splitlines()


def heading(lines: list[str]) -> list[str]:
    return lines[2].split()[2:]


def test_the_header() -> None:
    store = Store(sessions=[session()], gauges=Gauges(
        five_hour=Window(3, NOW + 100), seven_day=Window(74, NOW + 9)))
    clock = time.strftime("%H:%M", time.localtime(NOW))
    lines = dump(store, 160, filter="a title", unnamed=False)
    assert lines[0].startswith("herdtop 0.1.0  1/1 sessions  0 MiB  /a title"
                               "  7d 74% $-  5h 3% $-  ~$ -")
    assert lines[0].endswith(f"group: repo  sort: answer  {clock}")
    assert lines[1] == "1.sessions (1)"
    narrow = dump(store, 59)[0]
    assert narrow.endswith(clock) and "group:" not in narrow
    assert width(narrow) == 59
    assert dump(store, 69)[1] == "1.1"
    assert "unnamed  group" in dump(store, 160, unnamed=True, search=["x"])[0]


def test_the_header_says_when_the_registry_is_unreadable() -> None:
    store = Store(sessions=[session()], registry_readable=False)
    assert "registry unreadable" in dump(store, 160)[0]


def test_every_column_fits_a_wide_terminal(store: Store) -> None:
    assert heading(dump(store, 200)) == [c.name for c in COLUMNS]
    flat = dump(store, 200, group="flat")
    assert flat[2].split()[:3] == ["age", "title", "repo"]
    assert flat[2].split()[3:] == [c.name for c in COLUMNS if c.name != "sess"]


@pytest.mark.parametrize(("size", "kept"), [
    (120, ["sess", "ran", "cost", "req", "ctx", "cache", "model"]),
    (80, ["ctx", "cache"]),
    (60, ["ctx"]),
])
def test_the_columns_drop_as_the_terminal_narrows(
        store: Store, size: int, kept: list[str]) -> None:
    lines = dump(store, size)
    assert heading(lines) == kept
    assert all(width(line) <= size for line in lines)


def test_the_flat_view_narrows_the_names_before_the_context(store: Store) -> None:
    lines = dump(store, 80, group="flat")
    assert lines[2].split()[-1] == "ctx"
    assert all(width(line) <= 80 for line in lines)


def test_the_rows(store: Store) -> None:
    lines = dump(store, 200)
    assert lines[3].startswith("   now ▾ /work/herdr ")
    long_title = lines[4]
    assert long_title.index("…") == render.FIXED + render.TITLE_MAX - 2
    assert lines[5].startswith("    2h   generated title*")
    assert lines[6].startswith("   now ▾ /work/top (1) ")
    assert lines[7].startswith("●  now   open one ")


def test_each_colour_has_a_glyph(store: Store) -> None:
    lines = "\n".join(dump(store, 200))
    assert "400k▲▲" in lines and "150k▲ " in lines
    assert "●" in lines
    twin = session("twin", twin=True)
    maybe = session("maybe", maybe_open=True)
    marks = dump(Store(sessions=[twin, maybe]), 120, group="flat")
    assert [line[0] for line in marks[3:]] == ["!", "○"]


def test_colours_mark_the_name_and_the_figures(store: Store) -> None:
    view = ViewState(all_open=True)
    found = rows(store.sessions, view)
    _, lines = render.frame(store, view, found, 200, NOW, color=True)
    styles = {style for line in lines for _, style in line}
    assert {"open", "alarm", "warn", "warm", "group"} <= styles
    assert "▲" not in "".join(render.text_of(line) for line in lines)


def test_an_empty_store() -> None:
    lines = dump(Store(), 80)
    assert lines[0].startswith("herdtop 0.1.0  0/0 sessions")
    assert len(lines) == 3
