import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from builder import Transcript

from herdtop import __version__, cli


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stop:
        cli.main(["--version"])
    assert stop.value.code == 0
    assert capsys.readouterr().out == f"herdtop {__version__}\n"


def test_changes_start_at_the_current_version(
        capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--changes"]) == 0
    assert capsys.readouterr().out.splitlines()[0] == __version__


def test_module_runs() -> None:
    src = Path(cli.__file__).parents[1]
    done = subprocess.run([sys.executable, "-m", "herdtop", "--version"],
                          capture_output=True, text=True, check=True,
                          env={**os.environ, "PYTHONPATH": str(src)})
    assert done.stdout.startswith("herdtop ")


def test_once_dumps_the_synthetic_store(
        home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    t = Transcript(home, "/work/a").user("fix the parser").custom_title("parser")
    t.assistant(at=time.time() - 120, write_5m=10, read=200_000, output=5)
    t.write()
    Transcript(home, "/work/b").user("docs").ai_title("write docs").write()
    assert cli.main(["--once", "--width", "200", "--group", "flat",
                     "--sort", "title"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("herdtop 0.1.0  2/2 sessions")
    # The registry is empty, so a transcript written now may be open.
    assert lines[3].split()[:4] == ["○", "2m", "parser", "/work/a"]
    assert "200k▲" in lines[3]
    assert lines[4].split()[2:4] == ["write", "docs*"]
    assert cli.main(["--once", "--unnamed", "--filter", "docs"]) == 0
    assert "1/2 sessions" in capsys.readouterr().out


def test_once_survives_a_closed_pipe(home: Path) -> None:
    for i in range(200):
        Transcript(home, f"/work/{i}").user("go").write()
    src = Path(cli.__file__).parents[1]
    done = subprocess.run(
        f"{sys.executable} -m herdtop --once | head -1", shell=True, check=False,
        capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(src)})
    assert done.stdout.startswith("herdtop ")
    assert "Error" not in done.stderr
