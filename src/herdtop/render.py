"""The lines of the sessions tab, as styled segments. The terminal draws
them with colours; `--once` prints them as text with the glyphs."""

from __future__ import annotations

import time
from dataclasses import dataclass

from herdtop import __version__
from herdtop.columns import Column, age, choose, group_cell, session_cell
from herdtop.model import Session
from herdtop.store import Store
from herdtop.text import cut, cut_left, pad, rpad, width
from herdtop.view import Row, ViewState, home_path

Segment = tuple[str, str]
Line = list[Segment]

TITLE_MAX = 58
REPO_MAX = 24
# The mark, a gap, the age and a gap.
FIXED = 7


@dataclass
class Layout:
    width: int
    title: int
    repo: int
    columns: list[Column]
    grouped: bool


def text_of(line: Line) -> str:
    return "".join(text for text, _ in line)


def mark(session: Session) -> str:
    if session.twin:
        return "!"
    if session.live:
        return "●"
    if session.maybe_open:
        return "○"
    return " "


def name_style(session: Session) -> str:
    if session.twin:
        return "twin"
    return "open" if session.open else ""


def title_text(row: Row, grouped: bool) -> str:
    if row.group:
        opened = sum(s.open for s in row.sessions)
        count = f" ({opened})" if opened else ""
        return f"{'▾' if row.opened else '▸'} {row.label}{count}"
    return ("  " if grouped else "") + " ".join(row.session.title.split())


def layout(rows: list[Row], state: ViewState, size: int) -> Layout:
    grouped = state.group != "flat"
    # One more column for the `*` of a generated title.
    title = min(TITLE_MAX, max((width(title_text(r, grouped)) + 1 for r in rows),
                               default=10))
    repo = 0
    if not grouped:
        repo = min(REPO_MAX, max((width(home_path(r.session.cwd)) for r in rows),
                                 default=4))
    room = size - FIXED - title - (repo + 1 if repo else 0)
    # Narrow the names before the context, the column of rank 1, goes.
    need = 7
    if room < need and repo > 8:
        give = min(repo - 8, need - room)
        repo, room = repo - give, room + give
    if room < need and title > 16:
        give = min(title - 16, need - room)
        title, room = title - give, room + give
    return Layout(size, title, repo, choose(max(room, 0), grouped), grouped)


def heading(lay: Layout) -> Line:
    text = " " + rpad("age", 5) + " " + pad("title", lay.title)
    if lay.repo:
        text += " " + pad("repo", lay.repo)
    for column in lay.columns:
        text += " " + rpad(column.name, column.width)
    return [(pad(text, lay.width), "head")]


def row_line(row: Row, lay: Layout, now: float, color: bool) -> Line:
    if row.group:
        newest = max(s.answered for s in row.sessions)
        line: Line = [(" " + rpad(age(now - newest), 5) + " ", ""),
                      (pad(title_text(row, True), lay.title), "group")]
        if lay.repo:
            line.append((" " * (lay.repo + 1), ""))
        for column in lay.columns:
            text, style = group_cell(column, row.sessions)
            line += [(" ", ""), (rpad(text, column.width), style)]
    else:
        session = row.session
        star = " " if session.title_set else "*"
        name = cut(title_text(row, lay.grouped), lay.title - 1)
        line = [(mark(session) + rpad(age(now - session.answered), 5) + " ", ""),
                (name, name_style(session)),
                (star + " " * (lay.title - 1 - width(name)), "")]
        if lay.repo:
            line.append((" " + pad(cut_left(home_path(session.cwd), lay.repo),
                                   lay.repo), ""))
        for column in lay.columns:
            text, style = session_cell(column, session, now, color)
            line += [(" ", ""), (rpad(text, column.width), style)]
    used = sum(width(text) for text, _ in line)
    if used < lay.width:
        line.append((" " * (lay.width - used), ""))
    return line


def header(store: Store, state: ViewState, shown: int, size: int,
           now: float) -> Line:
    left = (f"herdtop {__version__}  {shown}/{len(store.sessions)} sessions  "
            f"{store.size / 2**20:.0f} MiB")
    if state.filter:
        left += f"  /{state.filter}"
    if state.search:
        left += f"  F:{' '.join(state.search)}"
    gauges = store.gauges
    if gauges:
        for label, window in (("7d", gauges.seven_day), ("5h", gauges.five_hour)):
            if window:
                left += f"  {label} {window.used}% $-"
    left += "  ~$ -"
    if not store.registry_readable:
        left += "  registry unreadable"
    clock = time.strftime("%H:%M", time.localtime(now))
    parts = (["unnamed"] if state.unnamed else []) + [
        f"group: {state.group}", f"sort: {state.sort}", clock]
    right = clock if size < 60 else "  ".join(parts)
    left = cut(left, max(0, size - width(right) - 1))
    return [(pad(left, size - width(right)) + right, "head")]


def tab_bar(store: Store, size: int) -> Line:
    count = len(store.sessions)
    text = f"1.{count}" if size < 70 else f"1.sessions ({count})"
    return [(pad(text, size), "tabs")]


def frame(store: Store, state: ViewState, rows: list[Row], size: int, now: float,
          color: bool) -> tuple[list[Line], list[Line]]:
    """The fixed lines on top, and one line per row."""
    lay = layout(rows, state, size)
    shown = sum(len(r.sessions) for r in rows if r.group) if lay.grouped else len(rows)
    top = [header(store, state, shown, size, now), tab_bar(store, size),
           heading(lay)]
    return top, [row_line(r, lay, now, color) for r in rows]


def once(store: Store, state: ViewState, rows: list[Row], size: int,
         now: float) -> str:
    top, lines = frame(store, state, rows, size, now, color=False)
    return "\n".join(cut(text_of(line), size).rstrip() for line in top + lines)
