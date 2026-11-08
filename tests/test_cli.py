import os
import subprocess
import sys
from pathlib import Path

import pytest

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
