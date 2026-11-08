"""The directories that herdtop reads and writes. Each one moves by an
environment variable, so that the tests build a store of their own."""

import os
from pathlib import Path


def _env_dir(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else default


def _xdg(name: str, default: str) -> Path:
    return _env_dir(name, Path.home() / default)


def claude_home() -> Path:
    return _env_dir("HERDTOP_CLAUDE_HOME",
                    _env_dir("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))


def payload_dir() -> Path:
    """Where a status line command saves the payload of each session."""
    return _env_dir("HERDTOP_PAYLOAD_DIR",
                    _xdg("XDG_STATE_HOME", ".local/state") / "claude-tmux")


def cache_dir() -> Path:
    return _env_dir("HERDTOP_CACHE_DIR",
                    _xdg("XDG_CACHE_HOME", ".cache") / "herdtop")
