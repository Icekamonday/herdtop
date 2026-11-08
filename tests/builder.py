"""Synthetic Claude Code stores, written record by record."""

from __future__ import annotations

import json
import os
import time as clock
import uuid as uuidlib
from datetime import UTC, datetime
from pathlib import Path

from herdtop.readers.claude import own_pid_domain, start_time

NOW = 1_800_000_000.0


def iso(t: float) -> str:
    return datetime.fromtimestamp(t, UTC).isoformat().replace("+00:00", "Z")


def slug(cwd: str) -> str:
    return cwd.replace("/", "-").replace(".", "-")


def usage(input: int = 0, write_5m: int = 0, write_1h: int = 0, read: int = 0,
          output: int = 0, thinking: int = 0) -> dict:
    return {
        "input_tokens": input,
        "cache_creation_input_tokens": write_5m + write_1h,
        "cache_read_input_tokens": read,
        "output_tokens": output,
        "output_tokens_details": {"thinking_tokens": thinking},
        "cache_creation": {"ephemeral_5m_input_tokens": write_5m,
                           "ephemeral_1h_input_tokens": write_1h},
    }


class Transcript:
    def __init__(self, home: Path, cwd: str, sid: str | None = None,
                 project: str | None = None) -> None:
        self.home = home
        self.cwd = cwd
        self.sid = sid or str(uuidlib.uuid4())
        self.project = project or slug(cwd)
        self.records: list[dict] = []
        self.calls = 0

    @property
    def path(self) -> Path:
        return self.home / ".claude" / "projects" / self.project / f"{self.sid}.jsonl"

    def raw(self, record: dict) -> Transcript:
        self.records.append(record)
        return self

    def _base(self, kind: str, at: float) -> dict:
        return {"type": kind, "uuid": str(uuidlib.uuid4()), "timestamp": iso(at),
                "sessionId": self.sid, "cwd": self.cwd}

    def user(self, text: str | list, at: float = NOW, **extra) -> Transcript:
        record = self._base("user", at)
        record["message"] = {"role": "user", "content": text}
        return self.raw({**record, **extra})

    def assistant(self, text: str | None = "ok", at: float = NOW,
                  model: str = "claude-opus-4-1-20250805",
                  request: str | None = None, message: str | None = None,
                  tool_prompt: str | None = None, **counts) -> Transcript:
        self.calls += 1
        content: list[dict] = []
        if text is not None:
            content.append({"type": "text", "text": text})
        if tool_prompt is not None:
            content.append({"type": "tool_use", "name": "Agent",
                            "input": {"prompt": tool_prompt}})
        record = self._base("assistant", at)
        record["requestId"] = request or f"req_{self.sid[:8]}_{self.calls}"
        record["message"] = {"id": message or f"msg_{self.sid[:8]}_{self.calls}",
                             "role": "assistant", "model": model,
                             "content": content,
                             "usage": usage(**counts)}
        return self.raw(record)

    def custom_title(self, title: str) -> Transcript:
        return self.raw({"type": "custom-title", "customTitle": title,
                         "sessionId": self.sid})

    def ai_title(self, title: str) -> Transcript:
        return self.raw({"type": "ai-title", "aiTitle": title,
                         "sessionId": self.sid})

    def continued_in(self, job: str, at: float = NOW) -> Transcript:
        return self.raw({"type": "continued-in", "continuedInSessionId": job,
                         "sessionId": self.sid, "timestamp": iso(at)})

    def write(self, mtime: float | None = None) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w") as f:
            for record in self.records:
                f.write(json.dumps(record, separators=(",", ":")) + "\n")
        if mtime is not None:
            os.utime(self.path, (mtime, mtime))
        return self.path


def register(home: Path, sid: str, pid: int | None = None, *,
             proc_start: str | None = None, domain: str | None = "own",
             kind: str = "interactive", **extra) -> Path:
    """A registry file. By default it names this test process, so it is live."""
    pid = os.getpid() if pid is None else pid
    entry = {"pid": pid, "sessionId": sid, "cwd": "/", "kind": kind,
             "entrypoint": "cli", "status": "idle",
             "procStart": start_time(pid) if proc_start is None else proc_start,
             "startedAt": int(clock.time() * 1000), **extra}
    if domain == "own":
        entry["pidDomain"] = own_pid_domain()
    elif domain is not None:
        entry["pidDomain"] = domain
    path = home / ".claude" / "sessions" / f"{pid}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entry))
    return path


def payload(home: Path, sid: str, *, ttl: str = "5m", expires_at: float = NOW,
            recache: int | None = None, five_hour: tuple | None = None,
            seven_day: tuple | None = None, mtime: float | None = None) -> Path:
    data: dict = {"session_id": sid,
                  "prompt_cache": {"ttl": ttl, "expires_at": int(expires_at)}}
    if recache is not None:
        data["prompt_cache"]["recache_tokens_if_cold"] = recache
    limits = {}
    for name, window in (("five_hour", five_hour), ("seven_day", seven_day)):
        if window:
            limits[name] = {"used_percentage": window[0], "resets_at": window[1]}
    if limits:
        data["rate_limits"] = limits
    path = home / "payload" / f"{sid}.raw.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def session(title: str | None = "a title", cwd: str | None = "/work/a", *,
            named: bool = True, answered: float = NOW, sid: str | None = None,
            calls: list | None = None, **fields):
    """A session built in memory, for the tests of what shows it."""
    from herdtop.model import Digest, Session, Tally

    sid = sid or str(uuidlib.uuid4())
    digest = Digest(id=sid, cwd=cwd, title=title, title_set=named,
                    first_prompt="the first prompt", last_answer=answered,
                    tally=Tally.of(calls or []))
    path = Path("/store") / slug(cwd or "/x") / f"{sid}.jsonl"
    return Session(kind="claude", path=path, project=path.parent.name,
                   mtime=answered, size=fields.pop("size", 1000), digest=digest,
                   **fields)
