"""The reader of Claude Code: the transcripts and their sidecars, the
process registry, and the payload that a status line command saves."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

from herdtop import paths
from herdtop.model import (
    CacheState,
    Call,
    Digest,
    Exchange,
    Gauges,
    Live,
    Liveness,
    Tally,
    Window,
)

# A line that holds none of these bytes cannot change the digest once the
# head of the file is read, so it is not parsed.
_MARKERS = (b'"usage"', b'-title"', b'"continued-in"')
_UUID = re.compile(rb'"uuid":\s*"([0-9a-f-]{36})"')

# What the client wraps around the typing of a person.
_DROPPED = re.compile(
    r"<(system-reminder|ide_[a-z_]+|local-command-[a-z]+|bash-stdout"
    r"|bash-stderr|task-notification|user-prompt-submit-hook)\b[^>]*>"
    r".*?</\1>",
    re.DOTALL)
_MARKS = re.compile(
    r"</?pasted_content\b[^>]*>|\[Image #\d+\]|\[Image: source: [^\]]*\]"
    r"|^\[Request interrupted by user[^\]\n]*\]$",
    re.MULTILINE)
_COMMAND = re.compile(r"<command-name>\s*(.*?)\s*</command-name>", re.DOTALL)
_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.DOTALL)
_BASH = re.compile(r"<bash-input>(.*?)</bash-input>", re.DOTALL)


def _time(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def _load(line: bytes) -> dict | None:
    try:
        record = json.loads(line)
    except ValueError:
        return None
    return record if isinstance(record, dict) else None


def _load_file(path: Path) -> dict | None:
    try:
        return _load(path.read_bytes())
    except OSError:
        return None


def _int(value: object) -> int:
    return value if isinstance(value, int) else 0


def clean(text: str) -> str:
    """The typing of a person, without what the client adds around it."""
    command = _COMMAND.search(text)
    if command:
        name = command.group(1)
        if not name.startswith("/"):
            name = "/" + name
        args = _ARGS.search(text)
        return f"{name} {args.group(1).strip() if args else ''}".strip()
    bash = _BASH.search(text)
    if bash:
        return f"! {bash.group(1).strip()}"
    text = _DROPPED.sub("", text)
    return _MARKS.sub("", text).strip()


def prompt_of(record: dict) -> str | None:
    """The prompt that a `user` record holds, or None for a record that a
    tool, a hook, a compaction or the client wrote."""
    if record.get("type") != "user" or record.get("isMeta"):
        return None
    if record.get("isCompactSummary"):
        return None
    origin = record.get("origin")
    if isinstance(origin, dict) and origin.get("kind") not in (None, "human"):
        return None
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        texts = [content]
    elif isinstance(content, list):
        texts = [block.get("text", "") for block in content
                 if isinstance(block, dict) and block.get("type") == "text"]
    else:
        return None
    return clean("\n".join(t for t in texts if isinstance(t, str))) or None


def _blocks(record: dict) -> list[dict]:
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, list):
        return [block for block in content if isinstance(block, dict)]
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return []


def answer_of(record: dict) -> str | None:
    if record.get("type") != "assistant":
        return None
    texts = [block.get("text") for block in _blocks(record)
             if block.get("type") == "text"]
    text = "\n".join(t for t in texts if isinstance(t, str)).strip()
    return text or None


def call_of(record: dict, time: float) -> tuple[tuple, Call] | None:
    """The call of an `assistant` record, with the key that counts it once:
    a resume or a compaction writes the same records again, and one answer
    spans one record per content block."""
    message = record.get("message")
    if record.get("type") != "assistant" or not isinstance(message, dict):
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    # The total is the authority, and the detail only splits it: an
    # interrupted turn can carry a detail with a total of zero.
    write = _int(usage.get("cache_creation_input_tokens"))
    detail = usage.get("cache_creation")
    write_1h = 0
    if isinstance(detail, dict):
        write_1h = min(write, _int(detail.get("ephemeral_1h_input_tokens")))
    write_5m = write - write_1h
    output_detail = usage.get("output_tokens_details")
    thinking = (_int(output_detail.get("thinking_tokens"))
                if isinstance(output_detail, dict) else 0)
    call = Call(
        time=time,
        model=str(message.get("model") or "unknown"),
        input=_int(usage.get("input_tokens")),
        output=_int(usage.get("output_tokens")),
        thinking=thinking,
        write_5m=write_5m,
        write_1h=write_1h,
        read=_int(usage.get("cache_read_input_tokens")),
    )
    key = (record.get("requestId"), message.get("id"))
    if key == (None, None):
        key = ("uuid", record.get("uuid"))
    return key, call


def own_pid_domain() -> str | None:
    """The pid namespace of this process, in the form of `pidDomain`."""
    try:
        machine = Path("/etc/machine-id").read_text().strip()
        namespace = os.readlink("/proc/self/ns/pid")
    except OSError:
        return None
    return f"linux:{machine}:{namespace}"


def start_time(pid: int) -> str | None:
    """Field 22 of /proc/<pid>/stat, the start time of the process in clock
    ticks, which `procStart` records."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    fields = stat.rsplit(")", 1)[-1].split()
    return fields[19] if len(fields) > 19 else None


def _tree_size(root: str | Path) -> int:
    total = 0
    try:
        entries = os.scandir(root)
    except OSError:
        return 0
    with entries:
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    total += _tree_size(entry.path)
                else:
                    total += entry.stat(follow_symlinks=False).st_size
            except OSError:
                continue
    return total


class ClaudeReader:
    kind = "claude"

    def __init__(self, home: Path | None = None,
                 payload: Path | None = None) -> None:
        self.home = home or paths.claude_home()
        self.payload = payload or paths.payload_dir()

    def transcripts(self) -> list[Path]:
        return sorted(self.home.glob("projects/*/*.jsonl"))

    def project(self, path: Path) -> str:
        return path.parent.name

    def digest(self, path: Path) -> Digest:
        digest = Digest(id=path.stem)
        calls: dict[tuple, Call] = {}
        custom = generated = None
        head = True
        with path.open("rb") as f:
            for line in f:
                uuid = _UUID.search(line)
                if uuid:
                    digest.last_record = uuid.group(1).decode()
                if not head and not any(m in line for m in _MARKERS):
                    continue
                record = _load(line)
                if record is None:
                    continue
                kind = record.get("type")
                if digest.cwd is None and isinstance(record.get("cwd"), str):
                    digest.cwd = record["cwd"]
                if kind == "custom-title" and record.get("customTitle"):
                    custom = str(record["customTitle"])
                elif kind == "ai-title" and record.get("aiTitle"):
                    generated = str(record["aiTitle"])
                elif kind == "continued-in":
                    digest.continued_in = record.get("continuedInSessionId")
                elif kind == "user" and digest.first_prompt is None:
                    digest.first_prompt = prompt_of(record)
                elif kind == "assistant":
                    time = _time(record.get("timestamp"))
                    if time is None:
                        continue
                    found = call_of(record, time)
                    if found:
                        key, call = found
                        kept = calls.get(key)
                        if kept is None:
                            calls[key] = call
                        elif call.output >= kept.output:
                            # The record of the last content block holds
                            # the final output count.
                            call.time = kept.time
                            calls[key] = call
                    if answer_of(record) and time > (digest.last_answer or 0):
                        digest.last_answer = time
                head = digest.cwd is None or digest.first_prompt is None
        if digest.first_prompt:
            digest.first_prompt = digest.first_prompt.splitlines()[0][:200]
        digest.title = custom or generated
        digest.title_set = custom is not None
        digest.tally = Tally.of(list(calls.values()))
        return digest

    def sidecar_size(self, path: Path) -> int:
        return _tree_size(path.with_suffix(""))

    def live(self) -> Liveness:
        liveness = Liveness()
        domain = own_pid_domain()
        for path in (self.home / "sessions").glob("*.json"):
            entry = _load_file(path)
            if entry is None:
                continue
            pid, session = entry.get("pid"), entry.get("sessionId")
            if not isinstance(pid, int) or not isinstance(session, str):
                continue
            if entry.get("pidDomain"):
                if entry["pidDomain"] != domain:
                    continue
                liveness.readable = True
            started = start_time(pid)
            # A registry file outlives its process, and a pid is reused.
            if started is None or started != str(entry.get("procStart")):
                continue
            liveness.readable = True
            liveness.sessions[session] = Live(
                pid=pid,
                kind=str(entry.get("kind") or ""),
                entrypoint=entry.get("entrypoint"),
                status=entry.get("status"),
                name=entry.get("name"),
                parked_job=entry.get("parkedJobId"),
            )
        return liveness

    def cache(self, session_id: str) -> CacheState | None:
        data = _load_file(self.payload / f"{session_id}.raw.json")
        cache = data.get("prompt_cache") if data else None
        if not isinstance(cache, dict):
            return None
        ttl = cache.get("ttl")
        expires = cache.get("expires_at")
        recache = cache.get("recache_tokens_if_cold")
        return CacheState(
            ttl=ttl if ttl in ("5m", "1h") else None,
            expires_at=float(expires) if isinstance(expires, int | float)
            else None,
            recache_tokens=recache if isinstance(recache, int) else None,
        )

    def gauges(self, now: float) -> Gauges | None:
        """The windows of the account. They belong to the account, so the
        newest payload answers for every session."""
        try:
            files = sorted(self.payload.glob("*.raw.json"),
                           key=lambda p: p.stat().st_mtime, reverse=True)
        except OSError:
            return None
        for path in files:
            data = _load_file(path)
            limits = data.get("rate_limits") if data else None
            if isinstance(limits, dict):
                return Gauges(
                    five_hour=_window(limits.get("five_hour"), now),
                    seven_day=_window(limits.get("seven_day"), now),
                )
        return None

    def _records(self, path: Path):
        seen = set()
        with path.open("rb") as f:
            for line in f:
                record = _load(line)
                if record is None:
                    continue
                uuid = record.get("uuid")
                if uuid:
                    if uuid in seen:
                        continue
                    seen.add(uuid)
                yield record

    def exchanges(self, path: Path) -> list[Exchange]:
        exchanges: list[Exchange] = []
        for record in self._records(path):
            prompt = prompt_of(record)
            if prompt:
                exchanges.append(
                    Exchange(_time(record.get("timestamp")), prompt))
                continue
            answer = answer_of(record)
            if answer and exchanges:
                exchanges[-1].answer = answer
        return exchanges

    def matches(self, path: Path, words: list[str]) -> bool:
        """True if the prompts hold every word, without case. The prompts
        that the session gave its agents count too. The answers do not,
        because an answer repeats the words of its question."""
        words = [w.casefold() for w in words if w]
        try:
            data = path.read_bytes().lower()
        except OSError:
            return False
        for word in words:
            if word.isascii() and word.encode() not in data:
                return False
        texts = []
        for record in self._records(path):
            prompt = prompt_of(record)
            if prompt:
                texts.append(prompt)
            elif record.get("type") == "assistant":
                for block in _blocks(record):
                    given = block.get("input")
                    if block.get("type") == "tool_use" and isinstance(
                            given, dict) and isinstance(given.get("prompt"), str):
                        texts.append(given["prompt"])
        text = "\n".join(texts).casefold()
        return all(word in text for word in words)


def _window(data: object, now: float) -> Window | None:
    if not isinstance(data, dict):
        return None
    used, resets = data.get("used_percentage"), data.get("resets_at")
    if not isinstance(used, int | float) or not isinstance(resets, int | float):
        return None
    if resets <= now:
        return None
    return Window(used=round(used), resets_at=float(resets))
