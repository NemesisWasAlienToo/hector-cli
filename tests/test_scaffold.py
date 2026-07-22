"""Unit tests for hector.scaffold — `hector init`. The generated config must itself
pass validation, and init must refuse to clobber an existing file."""

import builtins

import pytest
import yaml

from hector.scaffold import scaffold_init
from hector.validator import validate_config


def test_init_writes_config_that_validates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Accept all defaults (blank input).
    monkeypatch.setattr(builtins, "input", lambda _prompt="": "")

    scaffold_init(".hector.yaml")

    target = tmp_path / ".hector.yaml"
    assert target.exists()
    cfg = yaml.safe_load(target.read_text())
    errors, _warnings = validate_config(cfg)
    assert errors == [], "; ".join(f"{e.path}: {e.message}" for e in errors)
    # Scaffolding also creates the expected working dirs.
    assert (tmp_path / "platforms" / "boards").is_dir()
    assert (tmp_path / "results").is_dir()


def test_init_honours_prompt_values(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    answers = iter(["nucleo_f767zi", "1.15.0"])
    monkeypatch.setattr(builtins, "input", lambda _prompt="": next(answers))

    scaffold_init(".hector.yaml")
    text = (tmp_path / ".hector.yaml").read_text()
    assert "1.15.0" in text and "nucleo_f767zi" in text


def test_init_refuses_to_overwrite(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".hector.yaml").write_text("existing: true\n")
    with pytest.raises(SystemExit):
        scaffold_init(".hector.yaml")
    # The existing file is left untouched.
    assert (tmp_path / ".hector.yaml").read_text() == "existing: true\n"


def test_init_custom_filename(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(builtins, "input", lambda _prompt="": "")
    scaffold_init("board.hector.yaml")
    assert (tmp_path / "board.hector.yaml").exists()
