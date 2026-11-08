"""What the sessions tab shows: the filter, the sort, the groups and their
folds. No terminal here, so the tests and `--once` use the same rows."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from herdtop.model import Session

GROUPS = ("repo", "tag", "flat")
SORTS = ("answer", "title")
UNTAGGED = "(untagged)"
UNKNOWN = "(unknown directory)"

_TAG = re.compile(r"\s*(\[[^\]\n]{1,28}\]|\([^)\n]{1,28}\))")


@dataclass
class ViewState:
    group: str = "repo"
    sort: str = "answer"
    filter: str = ""
    search: list[str] = field(default_factory=list)
    matches: set[Path] | None = None
    unnamed: bool = False
    opened: set[str] = field(default_factory=set)
    all_open: bool = False


@dataclass
class Row:
    sessions: list[Session]
    label: str = ""
    group: bool = False
    opened: bool = False

    @property
    def session(self) -> Session:
        return self.sessions[0]


def home_path(path: str | None) -> str:
    if path is None:
        return UNKNOWN
    home = os.path.expanduser("~")
    if path == home or path.startswith(home + "/"):
        return "~" + path[len(home):]
    return path


def tag(title: str) -> str:
    """The text in brackets or parentheses at the head of a title, up to
    30 characters with its brackets."""
    found = _TAG.match(title)
    return found.group(1) if found else UNTAGGED


def _subsequence(word: str, text: str) -> bool:
    letters = iter(text)
    return all(c in letters for c in word)


def _filter(sessions: list[Session], text: str) -> list[Session]:
    """Each word must match the title or the directory. A substring match
    comes first; a subsequence match comes second, as it matches too much."""
    words = text.casefold().split()
    if not words:
        return sessions

    def keep(test) -> list[Session]:
        kept = []
        for s in sessions:
            fields = (s.title.casefold(), (s.cwd or "").casefold())
            if all(any(test(w, f) for f in fields) for w in words):
                kept.append(s)
        return kept

    return keep(lambda w, f: w in f) or keep(_subsequence)


def shown(sessions: list[Session], state: ViewState) -> list[Session]:
    if state.unnamed:
        sessions = [s for s in sessions if not s.title_set]
    if state.matches is not None:
        sessions = [s for s in sessions if s.path in state.matches]
    return _filter(sessions, state.filter)


def _sorted(sessions: list[Session], sort: str) -> list[Session]:
    if sort == "title":
        return sorted(sessions, key=lambda s: (s.title.casefold(), -s.answered))
    return sorted(sessions, key=lambda s: -s.answered)


def group_key(session: Session, mode: str) -> str:
    if mode == "tag":
        return tag(session.title)
    return home_path(session.cwd)


def rows(sessions: list[Session], state: ViewState) -> list[Row]:
    sessions = _sorted(shown(sessions, state), state.sort)
    if state.group == "flat":
        return [Row([s]) for s in sessions]
    groups: dict[str, list[Session]] = {}
    for session in sessions:
        groups.setdefault(group_key(session, state.group), []).append(session)
    if state.sort == "title":
        order = sorted(groups, key=str.casefold)
    else:
        # The sessions are already newest first, so is the first of each group.
        order = list(groups)
    everything_open = state.all_open or bool(state.filter) or bool(state.search)
    found = []
    for label in order:
        opened = everything_open or label in state.opened
        found.append(Row(groups[label], label, group=True, opened=opened))
        if opened:
            found += [Row([s]) for s in groups[label]]
    return found
