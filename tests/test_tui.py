import curses
import fcntl
import os
import pty
import select
import struct
import sys
import termios
import time
from pathlib import Path

import pytest
from builder import NOW, Transcript, session

from herdtop import tui
from herdtop.store import Store
from herdtop.view import ViewState


@pytest.fixture
def app() -> tui.App:
    sessions = [
        session("parser fix", "/work/a", answered=NOW),
        session("docs", "/work/a", answered=NOW - 10, named=False),
        session("[ops] deploy", "/work/b", answered=NOW - 20),
    ]
    loads = []

    def load() -> Store:
        loads.append(1)
        return Store(sessions=sessions)

    found = tui.App(load, ViewState())
    found.loads = loads  # type: ignore[attr-defined]
    return found


def keys(app: tui.App, *names: str) -> None:
    for name in names:
        app.key(name)


def labels(app: tui.App) -> list[str]:
    return [r.label if r.group else r.session.title for r in app.rows]


def test_moving_stays_in_the_list(app: tui.App) -> None:
    keys(app, "k")
    assert app.cursor == 0
    keys(app, "G")
    assert app.cursor == 1
    keys(app, "pgup", "j", "down")
    assert app.cursor == 1
    keys(app, "g")
    assert app.cursor == 0


def test_folds(app: tui.App) -> None:
    assert labels(app) == ["/work/a", "/work/b"]
    keys(app, "l")
    assert labels(app) == ["/work/a", "parser fix", "docs", "/work/b"]
    keys(app, "j", "j", "h")
    assert (app.cursor, labels(app)) == (0, ["/work/a", "/work/b"])
    keys(app, "enter")
    assert len(app.rows) == 4
    keys(app, "enter")
    assert len(app.rows) == 2
    keys(app, "z")
    assert len(app.rows) == 5
    keys(app, "z")
    assert len(app.rows) == 2


def test_enter_on_a_session_says_what_is_missing(app: tui.App) -> None:
    keys(app, "b", "b")
    assert app.state.group == "flat"
    keys(app, "enter")
    assert "not in this version" in app.message
    keys(app, "l", "h")
    assert len(app.rows) == 3


def test_group_sort_and_unnamed_cycle(app: tui.App) -> None:
    keys(app, "b")
    assert labels(app)[0] == "(untagged)"
    keys(app, "b", "t")
    assert labels(app) == ["[ops] deploy", "docs", "parser fix"]
    keys(app, "t", "u")
    assert labels(app) == ["docs"]
    keys(app, "b")
    assert app.state.group == "repo"


def test_the_filter_follows_the_typing(app: tui.App) -> None:
    keys(app, "/", "d", "e", "p", "x", "backspace")
    assert app.mode == "filter"
    assert labels(app) == ["/work/b", "[ops] deploy"]
    assert app.footer().startswith("/dep")
    keys(app, "f2", "enter")
    assert (app.mode, app.state.filter) == ("list", "dep")
    keys(app, "/", "esc")
    assert (app.mode, app.state.filter) == ("list", "")


def test_the_search(app: tui.App) -> None:
    store = app.store
    store.readers = {"claude": type("R", (), {
        "matches": staticmethod(lambda path, words: path == store.sessions[1].path)})()}
    keys(app, "F", "d", "o", "c", "enter")
    assert app.state.search == ["doc"]
    assert app.message == "1 sessions match"
    assert labels(app) == ["/work/a", "docs"]
    keys(app, "F", "esc")
    assert app.state.search == ["doc"]
    keys(app, "F", "backspace", "backspace", "backspace", "enter")
    assert (app.state.search, app.state.matches) == ([], None)


def test_escape_clears_then_quits(app: tui.App) -> None:
    app.state.filter = "x"
    keys(app, "esc")
    assert app.state.filter == "" and not app.done
    keys(app, "esc")
    assert app.done


def test_reload_help_and_quit(app: tui.App) -> None:
    keys(app, "r")
    assert app.message == "read 3 sessions"
    assert len(app.loads) == 2  # type: ignore[attr-defined]
    assert app.footer().startswith("read 3 sessions  │  ?:help")
    keys(app, "?")
    assert app.footer() == "any key closes the help"
    keys(app, "x")
    assert app.mode == "list"
    keys(app, "f1", "q")
    assert not app.done
    keys(app, "q")
    assert app.done


def test_an_empty_list(app: tui.App) -> None:
    app.store = Store()
    app.refresh()
    keys(app, "j", "l", "enter", "z")
    assert app.rows == []


def test_key_names() -> None:
    assert tui.key_name("\n") == "enter"
    assert tui.key_name("\x1b") == "esc"
    assert tui.key_name("\x7f") == "backspace"
    assert tui.key_name("x") == "x"
    assert tui.key_name(curses.KEY_DOWN) == "down"
    assert tui.key_name(curses.KEY_RESIZE) is None


MOUSE = (b"\x1b[?1000h", b"\x1b[?1002h", b"\x1b[?1003h", b"\x1b[?1006h")


def read_until(fd: int, wanted: bytes, seen: bytearray, limit: float = 10) -> None:
    end = time.monotonic() + limit
    while wanted not in seen:
        ready, _, _ = select.select([fd], [], [], max(0, end - time.monotonic()))
        if not ready:
            raise AssertionError(f"no {wanted!r} on the screen")
        try:
            seen += os.read(fd, 65536)
        except OSError:
            raise AssertionError(f"the screen closed before {wanted!r}") from None


def test_the_screen_runs_in_a_terminal_without_mouse_reports(home: Path) -> None:
    Transcript(home, "/work/a").user("go").custom_title("first session").write()
    src = str(Path(tui.__file__).parents[1])
    pid, fd = pty.fork()
    if pid == 0:  # pragma: no cover
        fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 120, 0, 0))
        os.environ.update(TERM="xterm-256color", PYTHONPATH=src)
        os.execv(sys.executable, [sys.executable, "-m", "herdtop"])
    seen = bytearray()
    try:
        read_until(fd, b"herdtop 0.1.0", seen)
        os.write(fd, b"?")
        read_until(fd, b"Keys", seen)
        os.write(fd, b" ")
        os.write(fd, b"l")
        read_until(fd, b"first session", seen)
        os.write(fd, b"q")
        _, status = os.waitpid(pid, 0)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
    assert os.waitstatus_to_exitcode(status) == 0
    assert not any(code in seen for code in MOUSE)
