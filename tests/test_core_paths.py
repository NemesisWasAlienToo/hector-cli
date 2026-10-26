"""Unit tests for host<->container path translation in hector.core.

These are the functions that keep every runtime path inside the bind-mounted project
root and translate host paths to the container's POSIX mount point (critical on
Windows, where the host path C:\\... is not a valid Linux path)."""

import os

import pytest

from hector import core


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A throwaway project root: cwd and WORKSPACE_MOUNT both point at tmp, so paths
    look identical in and out (the POSIX-host case), and EXTRA_MOUNTS starts empty."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(core, "WORKSPACE_MOUNT", str(tmp_path))
    monkeypatch.setattr(core, "EXTRA_MOUNTS", [])
    return tmp_path


def test_to_container_path_under_root(project):
    (project / "sub").mkdir()
    f = project / "sub" / "fw.elf"
    f.write_text("x")
    assert core.to_container_path("sub/fw.elf") == str(project / "sub" / "fw.elf")


def test_to_container_path_outside_root_raises(project, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "evil.elf"
    outside.write_text("x")
    with pytest.raises(ValueError, match="outside the project root"):
        core.to_container_path(str(outside))


def test_windows_style_mount_translates_to_posix(project, monkeypatch):
    # Simulate Windows: the container mounts the project at a fixed POSIX point,
    # and host paths must be rewritten under it.
    monkeypatch.setattr(core, "WORKSPACE_MOUNT", "/workspace")
    (project / "platforms").mkdir()
    (project / "platforms" / "b.repl").write_text("x")
    assert core.to_container_path("platforms/b.repl") == "/workspace/platforms/b.repl"


def test_container_to_host_round_trips(project):
    (project / "a").mkdir()
    (project / "a" / "f").write_text("x")
    cpath = core.to_container_path("a/f")
    assert core.container_to_host(cpath) == str(project / "a" / "f")


def test_container_to_host_rejects_outside_mount(project):
    with pytest.raises(ValueError, match="not under"):
        core.container_to_host("/etc/passwd")


def test_split_host_container_accepts_both_forms(project):
    (project / "f").write_text("x")
    host, cont = core.split_host_container("f")
    assert host == str(project / "f")
    # Feeding the container path back yields the same pair.
    assert core.split_host_container(cont) == (host, cont)


def test_register_dependency_mount_in_tree_uses_workspace(project):
    (project / "dep").mkdir()
    assert core.register_dependency_mount("dep") == str(project / "dep")
    assert core.EXTRA_MOUNTS == []            # in-tree dirs need no extra mount


def test_register_dependency_mount_out_of_tree_records_extra(project, tmp_path_factory):
    cache = tmp_path_factory.mktemp("renode-cache")
    ret = core.register_dependency_mount(str(cache))
    assert ret == str(cache.resolve())        # out-of-tree: used at its own abs path
    assert str(cache.resolve()) in core.EXTRA_MOUNTS


def test_container_path_for_prefers_extra_mount(project, tmp_path_factory):
    cache = tmp_path_factory.mktemp("cache")
    core.register_dependency_mount(str(cache))
    inner = cache / "renode" / "x.so"
    assert core.container_path_for(str(inner)) == str((cache / "renode" / "x.so").resolve())


def test_from_config_resolves_against_config_dir(project, monkeypatch):
    monkeypatch.setattr(core, "CONFIG_DIR", str(project / "board"))
    assert core.from_config("fw/app.elf") == str(project / "board" / "fw" / "app.elf")
    assert core.from_config("../shared/x.repl") == str(project / "shared" / "x.repl")


def test_from_config_leaves_absolute_and_urls(project, monkeypatch):
    monkeypatch.setattr(core, "CONFIG_DIR", str(project / "board"))
    for p in ("/opt/renode/x.repl", "https://example.com/fw.elf", "", None):
        assert core.from_config(p) == p


def test_from_config_defaults_to_cwd(project, monkeypatch):
    monkeypatch.setattr(core, "CONFIG_DIR", None)
    assert core.from_config("fw.elf") == str(project / "fw.elf")


def test_execution_dir_is_container_path_of_config_dir(project, monkeypatch):
    (project / "board").mkdir()
    monkeypatch.setattr(core, "NO_DOCKER", False)
    monkeypatch.setattr(core, "WORKSPACE_MOUNT", "/workspace")
    monkeypatch.setattr(core, "CONFIG_DIR", str(project / "board"))
    assert core.execution_dir() == "/workspace/board"
    monkeypatch.setattr(core, "NO_DOCKER", True)
    assert core.execution_dir() == str(project / "board")


def test_host_uid_gid_on_posix():
    ids = core.host_uid_gid()
    if hasattr(os, "getuid"):
        assert ids == (os.getuid(), os.getgid())
    else:  # pragma: no cover - only on Windows CI
        assert ids is None


def test_host_uid_gid_none_without_getuid(monkeypatch):
    # Emulate Windows, where os has no getuid: callers must get None and omit -u.
    monkeypatch.delattr(os, "getuid", raising=False)
    assert core.host_uid_gid() is None
