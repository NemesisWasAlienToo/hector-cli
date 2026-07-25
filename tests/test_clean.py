"""Unit tests for `hector clean` — the target selection, the cwd safety guard, and the
actual removal/preservation behaviour. No Renode/Docker involved."""

import os

from hector.pipeline import _is_within_cwd, clean_targets, run_clean


def _make_workspace(root):
    for sub in ("resc", "repl", "tests", "renode", "renode-verilator-integration"):
        (root / ".hector" / sub).mkdir(parents=True)
    (root / "results").mkdir()


# ---- clean_targets ----

def test_targets_default_keeps_renode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_workspace(tmp_path)
    targets = clean_targets()
    assert set(targets) == {
        os.path.join(".hector", "resc"),
        os.path.join(".hector", "repl"),
        os.path.join(".hector", "tests"),
        "results",
    }
    # The expensive checkouts are NOT in the default target list.
    assert not any("renode" in t for t in targets)


def test_targets_all_takes_whole_hector_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_workspace(tmp_path)
    assert set(clean_targets(include_renode=True)) == {".hector", "results"}


def test_targets_only_existing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".hector" / "resc").mkdir(parents=True)   # only resc exists
    assert clean_targets() == [os.path.join(".hector", "resc")]


def test_targets_custom_output_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "out").mkdir()
    assert clean_targets(output_dir="out") == ["out"]


# ---- _is_within_cwd ----

def test_is_within_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".hector").mkdir()
    assert _is_within_cwd(".hector") is True
    assert _is_within_cwd("/tmp") is False
    assert _is_within_cwd("..") is False


# ---- run_clean ----

def test_run_clean_default_removes_build_keeps_renode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_workspace(tmp_path)
    assert run_clean() == 0
    hector = tmp_path / ".hector"
    assert not (hector / "resc").exists()
    assert not (tmp_path / "results").exists()
    # Renode checkouts survive a default clean.
    assert (hector / "renode").is_dir()
    assert (hector / "renode-verilator-integration").is_dir()


def test_run_clean_all_removes_everything(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_workspace(tmp_path)
    assert run_clean(include_renode=True) == 0
    assert not (tmp_path / ".hector").exists()
    assert not (tmp_path / "results").exists()


def test_run_clean_dry_run_deletes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _make_workspace(tmp_path)
    run_clean(dry_run=True)
    assert (tmp_path / ".hector" / "resc").exists()   # untouched
    assert (tmp_path / "results").exists()
    assert "would remove" in capsys.readouterr().out


def test_run_clean_nothing_to_do(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert run_clean() == 0
    assert "already clean" in capsys.readouterr().out


def test_run_clean_refuses_outside_cwd(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    outside = tmp_path.parent / "sibling"
    outside.mkdir(exist_ok=True)
    run_clean(output_dir=str(outside))
    # The sibling dir is outside the project root and must be left alone.
    assert outside.exists()
    assert "refusing to remove" in capsys.readouterr().out
