"""The screen: the sessions tab in a terminal, and its keys.

`App` holds the state and takes key names, with no terminal, so that the
tests drive it. The curses part only draws and reads keys. It asks for no
mouse report, so the terminal keeps its own selection."""

from __future__ import annotations

import curses
import os
import sys
import time
from collections.abc import Callable

from herdtop import helptext, render, view
from herdtop.store import Store
from herdtop.text import cut, pad, width

PAGE = 10
FOOTER = 1

LIST_KEYS = ("?:help  /:filter  F:search  b:group  t:sort  u:unnamed  "
             "z:folds  r:reload  q:quit")


class App:
    def __init__(self, load: Callable[[], Store], state: view.ViewState) -> None:
        self.load = load
        self.state = state
        self.store = load()
        self.mode = "list"
        self.typed = ""
        self.message = ""
        self.cursor = 0
        self.top = 0
        self.done = False
        self.rows: list[view.Row] = []
        self.refresh()

    def refresh(self) -> None:
        self.rows = view.rows(self.store.sessions, self.state)
        self.cursor = max(0, min(self.cursor, len(self.rows) - 1))

    @property
    def current(self) -> view.Row | None:
        return self.rows[self.cursor] if self.rows else None

    def footer(self) -> str:
        if self.mode == "filter":
            return f"/{self.state.filter}▏  ⏎ keep  Esc clear"
        if self.mode == "search":
            return f"F {self.typed}▏  ⏎ search the prompts  Esc cancel"
        if self.mode == "help":
            return "any key closes the help"
        return f"{self.message}  │  {LIST_KEYS}" if self.message else LIST_KEYS

    def key(self, name: str) -> None:
        if self.mode == "help":
            self.mode = "list"
            return
        if self.mode in ("filter", "search"):
            self._typing(name)
            return
        self.message = ""
        action = {
            "j": lambda: self._move(1), "down": lambda: self._move(1),
            "k": lambda: self._move(-1), "up": lambda: self._move(-1),
            "pgdn": lambda: self._move(PAGE), "pgup": lambda: self._move(-PAGE),
            "g": lambda: self._move(-len(self.rows)),
            "G": lambda: self._move(len(self.rows)),
            "l": lambda: self._fold(True), "right": lambda: self._fold(True),
            "h": lambda: self._fold(False), "left": lambda: self._fold(False),
            "enter": self._enter,
            "z": self._fold_all,
            "b": lambda: self._cycle("group", view.GROUPS),
            "t": lambda: self._cycle("sort", view.SORTS),
            "u": self._unnamed,
            "/": self._start_filter,
            "F": self._start_search,
            "r": self._reload,
            "?": self._help, "f1": self._help,
            "esc": self._escape,
            "q": self._quit,
        }.get(name)
        if action:
            action()

    def _move(self, step: int) -> None:
        self.cursor = max(0, min(self.cursor + step, len(self.rows) - 1))

    def _group_of_cursor(self) -> int | None:
        for index in range(self.cursor, -1, -1):
            if self.rows[index].group:
                return index
        return None

    def _fold(self, opened: bool) -> None:
        row = self.current
        if row is None or self.state.group == "flat":
            return
        index = self.cursor if row.group else self._group_of_cursor()
        if index is None:
            return
        label = self.rows[index].label
        if opened:
            self.state.opened.add(label)
        else:
            self.state.opened.discard(label)
            self.cursor = index
        self.refresh()

    def _enter(self) -> None:
        row = self.current
        if row is None:
            return
        if row.group:
            self._fold(not row.opened)
        else:
            self.message = "the exchanges screen is not in this version"

    def _fold_all(self) -> None:
        groups = [r for r in self.rows if r.group]
        if any(not r.opened for r in groups):
            self.state.opened = {r.label for r in groups}
        else:
            self.state.opened = set()
        self.cursor = 0
        self.refresh()

    def _cycle(self, field: str, values: tuple[str, ...]) -> None:
        current = getattr(self.state, field)
        setattr(self.state, field, values[(values.index(current) + 1) % len(values)])
        self.cursor = 0
        self.refresh()

    def _unnamed(self) -> None:
        self.state.unnamed = not self.state.unnamed
        self.cursor = 0
        self.refresh()

    def _start_filter(self) -> None:
        self.mode = "filter"

    def _start_search(self) -> None:
        self.mode = "search"
        self.typed = " ".join(self.state.search)

    def _typing(self, name: str) -> None:
        filtering = self.mode == "filter"
        text = self.state.filter if filtering else self.typed
        if name == "esc":
            text = ""
            self.mode = "list"
            if not filtering:
                self.typed = ""
                return
        elif name == "enter":
            self.mode = "list"
            if not filtering:
                self._search(text)
                return
        elif name == "backspace":
            text = text[:-1]
        elif len(name) == 1 and name.isprintable():
            text += name
        else:
            return
        if filtering:
            self.state.filter = text
            self.cursor = 0
            self.refresh()
        else:
            self.typed = text

    def _search(self, text: str) -> None:
        words = text.split()
        if not words:
            self.state.search, self.state.matches = [], None
        else:
            self.state.search = words
            self.state.matches = self.store.search(words)
            self.message = f"{len(self.state.matches)} sessions match"
        self.cursor = 0
        self.refresh()

    def _reload(self) -> None:
        self.store = self.load()
        self.refresh()
        self.message = f"read {len(self.store.sessions)} sessions"

    def _help(self) -> None:
        self.mode = "help"

    def _escape(self) -> None:
        if self.state.filter or self.state.search:
            self.state.filter = ""
            self.state.search, self.state.matches = [], None
            self.refresh()
        else:
            self.done = True

    def _quit(self) -> None:
        self.done = True


def key_name(code: int | str) -> str | None:
    """The name of a key, as `App.key` takes it."""
    if isinstance(code, str):
        return {"\n": "enter", "\r": "enter", "\x1b": "esc", "\x7f": "backspace",
                "\b": "backspace"}.get(code, code)
    return {
        curses.KEY_UP: "up", curses.KEY_DOWN: "down",
        curses.KEY_PPAGE: "pgup", curses.KEY_NPAGE: "pgdn",
        curses.KEY_LEFT: "left", curses.KEY_RIGHT: "right",
        curses.KEY_HOME: "g", curses.KEY_END: "G",
        curses.KEY_ENTER: "enter", curses.KEY_BACKSPACE: "backspace",
        curses.KEY_F1: "f1",
    }.get(code)


def _styles(color: bool) -> dict[str, int]:
    styles = {"head": curses.A_BOLD, "tabs": curses.A_BOLD,
              "group": curses.A_BOLD}
    if not color:
        return styles
    curses.use_default_colors()
    for number, (name, fg) in enumerate((("green", curses.COLOR_GREEN),
                                         ("yellow", curses.COLOR_YELLOW),
                                         ("red", curses.COLOR_RED)), start=1):
        curses.init_pair(number, fg, -1)
        styles[name] = curses.color_pair(number)
    styles.update(open=styles["green"], warm=styles["green"],
                  warn=styles["yellow"], alarm=styles["red"], twin=styles["red"])
    return styles


def _put(screen: curses.window, y: int, x: int, text: str, attr: int) -> int:
    height, size = screen.getmaxyx()
    room = size - x - (1 if y == height - 1 else 0)
    text = cut(text, room)
    try:
        screen.addstr(y, x, text, attr)
    except curses.error:
        pass
    return x + width(text)


def _resize(screen: curses.window) -> None:
    """A Herdr pane grows after the program starts, and curses does not see
    it before a key, so the size is read at each tick."""
    try:
        size = os.get_terminal_size(sys.__stdout__.fileno())
    except OSError:
        return
    if (size.lines, size.columns) != screen.getmaxyx():
        curses.resizeterm(size.lines, size.columns)


def draw(screen: curses.window, app: App, styles: dict[str, int],
         color: bool, now: float) -> None:
    screen.erase()
    height, size = screen.getmaxyx()
    if app.mode == "help":
        for y, line in enumerate(helptext.lines()[:height - 1]):
            _put(screen, y, 0, line, 0)
        _put(screen, height - 1, 0, pad(app.footer(), size), curses.A_REVERSE)
        screen.refresh()
        return
    top, lines = render.frame(app.store, app.state, app.rows, size, now, color)
    room = max(1, height - len(top) - FOOTER)
    if app.cursor < app.top:
        app.top = app.cursor
    elif app.cursor >= app.top + room:
        app.top = app.cursor - room + 1
    app.top = max(0, min(app.top, max(0, len(lines) - room)))
    y = 0
    for line in top:
        x = 0
        for text, style in line:
            x = _put(screen, y, x, text, styles.get(style, 0))
        y += 1
    for index in range(app.top, min(len(lines), app.top + room)):
        x = 0
        cursor = curses.A_REVERSE if index == app.cursor else 0
        for text, style in lines[index]:
            x = _put(screen, y, x, text, styles.get(style, 0) | cursor)
        y += 1
    _put(screen, height - 1, 0, pad(app.footer(), size), curses.A_DIM)
    screen.refresh()


def _loop(screen: curses.window, app: App, color: bool) -> None:
    try:
        curses.curs_set(0)
    except curses.error:
        pass
    color = color and curses.has_colors()
    styles = _styles(color)
    screen.keypad(True)
    # The screen redraws every second, for the clock and the cache countdowns.
    screen.timeout(1000)
    while not app.done:
        _resize(screen)
        draw(screen, app, styles, color, time.time())
        try:
            code = screen.get_wch()
        except curses.error:
            continue
        name = key_name(code)
        if name:
            app.key(name)


def run(app: App, color: bool) -> None:
    os.environ.setdefault("ESCDELAY", "25")
    curses.wrapper(_loop, app, color)
