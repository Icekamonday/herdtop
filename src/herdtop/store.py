"""The sessions of every reader, as the sessions tab lists them."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from herdtop.model import CacheState, Gauges, Reader, Session, Tally
from herdtop.tally import TallyCache

# If the registry cannot be read, a transcript written this recently may
# belong to an open session.
MAYBE_OPEN = 120


@dataclass
class Store:
    sessions: list[Session] = field(default_factory=list)
    readers: dict[str, Reader] = field(default_factory=dict)
    gauges: Gauges | None = None
    registry_readable: bool = True

    @property
    def size(self) -> int:
        return sum(s.size for s in self.sessions)

    def search(self, words: list[str]) -> set[Path]:
        """The sessions whose prompts hold every word."""
        return {s.path for s in self.sessions
                if self.readers[s.kind].matches(s.path, words)}


def _cache(state: CacheState | None, tally: Tally) -> CacheState | None:
    """The payload's cache, or only its TTL if the payload predates the last
    call of the transcript."""
    if state is None:
        return None
    if (state.expires_at is not None and tally.last_call is not None
            and state.expires_at < tally.last_call):
        return CacheState(ttl=state.ttl)
    return state


def load(readers: list[Reader], now: float,
         cache: TallyCache | None = None) -> Store:
    cache = cache or TallyCache()
    store = Store(readers={r.kind: r for r in readers})
    for reader in readers:
        liveness = reader.live()
        store.registry_readable &= liveness.readable
        if store.gauges is None:
            store.gauges = reader.gauges(now)
        for path in reader.transcripts():
            # A transcript can go between the glob and the read: cleared,
            # archived from another terminal, or swept.
            try:
                stat = path.stat()
                digest = cache.digest(reader, path, stat)
            except OSError:
                continue
            session = Session(
                kind=reader.kind,
                path=path,
                project=reader.project(path),
                mtime=stat.st_mtime,
                size=stat.st_size + reader.sidecar_size(path),
                digest=digest,
                cache=_cache(reader.cache(digest.id), digest.tally),
                live=liveness.sessions.get(digest.id),
            )
            if not liveness.readable and now - stat.st_mtime < MAYBE_OPEN:
                session.maybe_open = True
            store.sessions.append(session)
    cache.save()
    _mark_twins(store.sessions)
    store.sessions = _fold_parks(store.sessions)
    return store


def _mark_twins(sessions: list[Session]) -> None:
    """One id in two project directories: the session was moved while it was
    open. Both rows stay, each keyed on its own path."""
    paths: dict[tuple[str, str], list[Session]] = {}
    for session in sessions:
        paths.setdefault((session.kind, session.id), []).append(session)
    for group in paths.values():
        if len(group) > 1:
            for session in group:
                session.twin = True


def _fold_parks(sessions: list[Session]) -> list[Session]:
    """List a parked conversation once, as its last job, which also takes
    the size of the transcripts that it continues."""
    by_id: dict[tuple[str, str], list[Session]] = {}
    for session in sessions:
        by_id.setdefault((session.kind, session.id), []).append(session)
    contents: dict[Path, bytes] = {}

    def holds(job: Session, old: Session) -> bool:
        # If parking ever writes a summary instead of a copy, the old
        # transcript holds calls that the job lacks, and hiding it would
        # hide that spending.
        if not old.digest.last_record:
            return False
        if job.path not in contents:
            try:
                contents[job.path] = job.path.read_bytes()
            except OSError:
                contents[job.path] = b""
        return old.digest.last_record.encode() in contents[job.path]

    hidden: set[int] = set()
    for session in sessions:
        job, seen = session, {session.id}
        while job.digest.continued_in:
            following = by_id.get((job.kind, job.digest.continued_in), [])
            if len(following) != 1 or following[0].id in seen:
                break
            job = following[0]
            seen.add(job.id)
        if job is not session and holds(job, session):
            hidden.add(id(session))
            job.parked.append(session.path)
            job.size += session.size
    return [s for s in sessions if id(s) not in hidden]
