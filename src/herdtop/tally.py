"""The tally cache: the digest of each transcript, keyed on the size and the
modification time of the file. A transcript only grows, so a run reads
again only the transcripts that changed."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from herdtop import paths
from herdtop.model import Digest, Reader

# Bump it when the shape of a digest changes: the cache is then rebuilt.
SHAPE = 1


class TallyCache:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or paths.cache_dir() / "tally.json"
        self.entries: dict[str, dict] = {}
        self.seen: set[str] = set()
        self.changed = False
        try:
            data = json.loads(self.path.read_bytes())
        except (OSError, ValueError):
            return
        if isinstance(data, dict) and data.get("shape") == SHAPE:
            entries = data.get("entries")
            if isinstance(entries, dict):
                self.entries = entries

    def digest(self, reader: Reader, path: Path, stat: os.stat_result) -> Digest:
        """The digest of a transcript. `stat` is taken before the read, so a
        file that grows during the read is read again at the next run."""
        key = f"{reader.kind}:{path}"
        self.seen.add(key)
        entry = self.entries.get(key)
        if (isinstance(entry, dict) and entry.get("size") == stat.st_size
                and entry.get("mtime") == stat.st_mtime_ns):
            try:
                return Digest.from_json(entry["digest"])
            except (KeyError, TypeError, AttributeError):
                pass
        digest = reader.digest(path)
        self.entries[key] = {"size": stat.st_size, "mtime": stat.st_mtime_ns,
                             "digest": digest.to_json()}
        self.changed = True
        return digest

    def save(self) -> None:
        """Write the cache, without the transcripts that this run did not
        see. A cache that cannot be written only costs time."""
        stale = set(self.entries) - self.seen
        if not self.changed and not stale:
            return
        for key in stale:
            del self.entries[key]
        data = json.dumps({"shape": SHAPE, "entries": self.entries},
                          separators=(",", ":"))
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".tally-")
            with os.fdopen(fd, "w") as f:
                f.write(data)
            os.replace(tmp, self.path)
        except OSError:
            return
        self.changed = False
