"""Every test runs in a home of its own, so that no test reads the real store."""

import os
import stat
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    (home / ".claude" / "projects").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    for name in ("CLAUDE_CONFIG_DIR", "XDG_STATE_HOME", "XDG_CACHE_HOME",
                 "HERDR_ENV", "NO_COLOR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HERDTOP_CLAUDE_HOME", str(home / ".claude"))
    monkeypatch.setenv("HERDTOP_PAYLOAD_DIR", str(home / "payload"))
    monkeypatch.setenv("HERDTOP_CACHE_DIR", str(home / "cache"))
    # A `herdr` that answers nothing: the tool must work without Herdr.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    herdr = bin_dir / "herdr"
    herdr.write_text("#!/bin/sh\nexit 1\n")
    herdr.chmod(herdr.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return home
