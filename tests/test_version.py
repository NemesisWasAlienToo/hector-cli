"""Guards the version single-source contract: setup.py, hector.core.TOOL_VERSION, and
`hector --version` must never drift (a real bug we hit: 0.2.0 vs 0.1.0)."""

import re
from pathlib import Path

import pytest

from hector.core import TOOL_VERSION

CLI_ROOT = Path(__file__).resolve().parents[1]


def test_tool_version_is_semver():
    assert re.fullmatch(r"\d+\.\d+\.\d+", TOOL_VERSION), TOOL_VERSION


def test_setup_py_reads_the_same_version(monkeypatch):
    """setup.py must derive its version from core.TOOL_VERSION (it reads it textually).
    We run setup.py with setuptools.setup stubbed to capture the kwargs it would pass."""
    import setuptools

    captured = {}
    monkeypatch.setattr(setuptools, "setup", lambda **kw: captured.update(kw))
    # runpy executes setup.py top-to-bottom; the stub captures instead of building.
    import runpy
    runpy.run_path(str(CLI_ROOT / "setup.py"), run_name="__main__")

    assert captured.get("version") == TOOL_VERSION


def test_cli_version_flag_prints_tool_version(capsys):
    from hector.commands import build_parser
    parser = build_parser()
    # argparse's version action prints and exits 0.
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"hector {TOOL_VERSION}"
