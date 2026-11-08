"""The figure columns of the list: their widths, their ranks, and the cells.

Three blocks never mix: what only a group has, what both kinds of row sum,
and what belongs to one session. A lower rank stays longer as the terminal
narrows."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from herdtop.model import Session

# The bands of the context: keep going, decide, hand off.
DECIDE = 150_000
HAND_OFF = 400_000

# The cell of a figure that needs the cost model, which this version lacks.
NO_COST = "-"


@dataclass(frozen=True)
class Column:
    name: str
    width: int
    rank: int
    block: int


COLUMNS = (
    Column("sess", 5, 3, 1),
    Column("ran", 5, 5, 2),
    Column("cost", 11, 2, 2),
    Column("req", 5, 6, 2),
    Column("size", 8, 7, 2),
    Column("ctx", 6, 1, 3),
    Column("cache", 5, 2, 3),
    Column("model", 11, 6, 3),
)


def choose(room: int, grouped: bool) -> list[Column]:
    """The columns that fit in `room`, taken by rank. A column that does not
    fit is skipped, and a narrower column of a lower rank can still fit."""
    candidates = [c for c in COLUMNS if grouped or c.name != "sess"]
    taken = set()
    for column in sorted(candidates, key=lambda c: c.rank):
        if column.width + 1 <= room:
            taken.add(column)
            room -= column.width + 1
    return [c for c in COLUMNS if c in taken]


def age(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 60:
        return "now"
    if s < 3600:
        return f"{s // 60}m"
    if s < 86400:
        return f"{s // 3600}h"
    if s < 30 * 86400:
        return f"{s // 86400}d"
    if s < 365 * 86400:
        return f"{s // (7 * 86400)}w"
    return f"{s // (365 * 86400)}y"


def duration(seconds: float) -> str:
    minutes = int(seconds) // 60
    if minutes < 60:
        return f"{minutes}m"
    hours, rest = divmod(minutes, 60)
    if hours < 10:
        return f"{hours}h{rest:02d}"
    if hours < 100:
        return f"{hours}h"
    return f"{hours // 24}d"


def size(n: int) -> str:
    if n < 1024:
        return f"{n}B"
    value, unit = n / 1024, 0
    while value >= 1024 and unit < 3:
        value /= 1024
        unit += 1
    letter = "KMGT"[unit]
    if value < 10 and letter != "K":
        return f"{value:.1f}{letter}"
    return f"{value:.0f}{letter}"


def tokens(n: int) -> str:
    if n < 1000:
        return str(n)
    if n < 999_500:
        return f"{n / 1000:.0f}k"
    return f"{n / 1_000_000:.1f}M"


def short_model(model: str | None) -> str:
    if not model:
        return "-"
    return re.sub(r"-\d{8}$", "", model.removeprefix("claude-"))


def band(context: int) -> str:
    if context >= HAND_OFF:
        return "alarm"
    if context >= DECIDE:
        return "warn"
    return ""


def session_cell(column: Column, session: Session, now: float,
                 color: bool) -> tuple[str, str]:
    """The text and the style of a cell of a session row."""
    tally = session.tally
    name = column.name
    if name == "sess":
        return "", ""
    if name == "cost":
        return NO_COST, ""
    if name == "size":
        return size(session.size), ""
    if not tally.calls:
        return "-", ""
    if name == "ran":
        return duration(tally.worked), ""
    if name == "req":
        return str(tally.calls), ""
    if name == "ctx":
        context = session.context
        style = band(context)
        glyph = {"warn": "▲", "alarm": "▲▲"}.get(style, "")
        return tokens(context) + ("" if color else glyph), style
    if name == "cache":
        ends = session.cache_ends
        if ends is None or ends <= now:
            return "cold", ""
        return f"{math.ceil((ends - now) / 60)}m", "warm"
    return short_model(tally.model), ""


def group_cell(column: Column, sessions: list[Session]) -> tuple[str, str]:
    """A fold row sums the second block, and shows a dash in the third,
    because states do not add up."""
    name = column.name
    if name == "sess":
        return (str(len(sessions)) if len(sessions) > 1 else ""), ""
    if name == "cost":
        return NO_COST, ""
    if name == "ran":
        return duration(sum(s.tally.worked for s in sessions)), ""
    if name == "req":
        return str(sum(s.tally.calls for s in sessions)), ""
    if name == "size":
        return size(sum(s.size for s in sessions)), ""
    return "-", ""
