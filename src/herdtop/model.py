"""The records that a reader gives, whatever the kind of agent."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

# Two calls further apart than this are two sittings, not time worked.
WORK_GAP = 15 * 60


@dataclass
class ModelCounts:
    calls: int = 0
    input: int = 0
    output: int = 0
    thinking: int = 0
    write_5m: int = 0
    write_1h: int = 0
    read: int = 0


@dataclass
class Call:
    """One request to the model, counted once."""

    time: float
    model: str
    input: int = 0
    output: int = 0
    thinking: int = 0
    write_5m: int = 0
    write_1h: int = 0
    read: int = 0

    @property
    def context(self) -> int:
        return self.input + self.write_5m + self.write_1h + self.read

    @property
    def empty(self) -> bool:
        return not (self.input or self.output or self.write_5m
                    or self.write_1h or self.read)

    @property
    def restart(self) -> bool:
        # A warm call reads back more than the turn adds. Only a call
        # after the cache expired writes more than it reads.
        return self.write_5m + self.write_1h > self.read


@dataclass
class Tally:
    """The counts of the conversation of one transcript, never dollars."""

    models: dict[str, ModelCounts] = field(default_factory=dict)
    calls: int = 0
    restarts: int = 0
    worked: float = 0.0
    last_call: float | None = None
    last_context: int = 0
    # The TTL of the last call that wrote to the cache: "5m" or "1h".
    last_ttl: str | None = None

    @classmethod
    def of(cls, calls: list[Call]) -> Tally:
        tally = cls()
        previous = None
        for call in sorted(calls, key=lambda c: c.time):
            if call.empty:
                continue
            counts = tally.models.setdefault(call.model, ModelCounts())
            counts.calls += 1
            counts.input += call.input
            counts.output += call.output
            counts.thinking += call.thinking
            counts.write_5m += call.write_5m
            counts.write_1h += call.write_1h
            counts.read += call.read
            tally.calls += 1
            tally.restarts += call.restart
            if previous is not None and call.time - previous < WORK_GAP:
                tally.worked += call.time - previous
            previous = call.time
            tally.last_call = call.time
            tally.last_context = call.context
            if call.write_1h:
                tally.last_ttl = "1h"
            elif call.write_5m:
                tally.last_ttl = "5m"
        return tally

    @property
    def model(self) -> str | None:
        """The model that wrote the most output."""
        if not self.models:
            return None
        return max(self.models.items(), key=lambda kv: kv[1].output)[0]

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict) -> Tally:
        models = {k: ModelCounts(**v) for k, v in data["models"].items()}
        return cls(**{**data, "models": models})


@dataclass
class Digest:
    """What one read of a transcript gives."""

    id: str
    cwd: str | None = None
    title: str | None = None
    # True if a person named the session; False for a generated title.
    title_set: bool = False
    first_prompt: str | None = None
    last_answer: float | None = None
    continued_in: str | None = None
    last_record: str | None = None
    tally: Tally = field(default_factory=Tally)

    def to_json(self) -> dict:
        return {**asdict(self), "tally": self.tally.to_json()}

    @classmethod
    def from_json(cls, data: dict) -> Digest:
        return cls(**{**data, "tally": Tally.from_json(data["tally"])})


@dataclass
class Live:
    """A process that holds a session."""

    pid: int
    kind: str
    entrypoint: str | None = None
    status: str | None = None
    name: str | None = None
    parked_job: str | None = None


@dataclass
class Liveness:
    """The live sessions by id. If the registry cannot be read, as from a
    sandbox that hides the pids, `readable` is False and the map is empty."""

    readable: bool = False
    sessions: dict[str, Live] = field(default_factory=dict)


@dataclass
class CacheState:
    """The cache of one session, as its status line last saw it."""

    ttl: str | None = None
    expires_at: float | None = None
    recache_tokens: int | None = None


@dataclass
class Window:
    used: int
    resets_at: float


@dataclass
class Gauges:
    """The rate-limit windows of the account; a window that has reset is None."""

    five_hour: Window | None = None
    seven_day: Window | None = None


@dataclass
class Exchange:
    """A prompt and the last answer before the next prompt."""

    time: float | None
    prompt: str
    answer: str = ""


@dataclass
class Session:
    """One row of the sessions tab. A session is keyed on its path, never on
    its id: one id can sit in two project directories."""

    kind: str
    path: Path
    project: str
    mtime: float
    size: int
    digest: Digest
    cache: CacheState | None = None
    live: Live | None = None
    maybe_open: bool = False
    twin: bool = False
    parked: list[Path] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.digest.id

    @property
    def cwd(self) -> str | None:
        return self.digest.cwd

    @property
    def title(self) -> str:
        return self.digest.title or self.digest.first_prompt or "(no prompt)"

    @property
    def title_set(self) -> bool:
        return self.digest.title_set

    @property
    def tally(self) -> Tally:
        return self.digest.tally

    @property
    def answered(self) -> float:
        """The time of the last answer. A rename or a hook also writes the
        file, so the file time stands in only when nothing was answered."""
        return self.digest.last_answer or self.mtime

    @property
    def open(self) -> bool:
        return self.live is not None or self.maybe_open


class Reader(Protocol):
    """The sources of one kind of agent."""

    kind: str

    def transcripts(self) -> list[Path]: ...

    def project(self, path: Path) -> str: ...

    def digest(self, path: Path) -> Digest: ...

    def sidecar_size(self, path: Path) -> int: ...

    def live(self) -> Liveness: ...

    def cache(self, session_id: str) -> CacheState | None: ...

    def gauges(self, now: float) -> Gauges | None: ...

    def exchanges(self, path: Path) -> list[Exchange]: ...

    def matches(self, path: Path, words: list[str]) -> bool: ...
