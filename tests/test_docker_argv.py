"""Unit tests for hector.docker command construction. We assert on the argv that
*would* run — never invoking Docker or Renode. build_renode_argv is the seam the
`export` command prints verbatim."""

import pytest

from hector import core, docker
from hector.core import RuntimeOptions


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(core, "WORKSPACE_MOUNT", str(tmp_path))
    monkeypatch.setattr(core, "EXTRA_MOUNTS", [])
    monkeypatch.setattr(core, "NO_DOCKER", False)
    # Neutralise X11 forwarding so argv is deterministic across hosts.
    monkeypatch.delenv("XAUTHORITY", raising=False)
    monkeypatch.delenv("HOME", raising=False)


# ---- build_renode_argv ----

def test_no_docker_is_bare_renode(monkeypatch):
    monkeypatch.setattr(core, "NO_DOCKER", True)
    assert docker.build_renode_argv("job.resc", "img", extra_args=["--console"]) == [
        "renode", "job.resc", "--console"]


def test_docker_argv_core_tokens():
    argv = docker.build_renode_argv("job.resc", "antmicro/renode:1.16.1")
    assert argv[:3] == ["docker", "run", "-it"]
    assert "--net=host" in argv
    assert "antmicro/renode:1.16.1" in argv
    # The image must be immediately followed by the renode invocation.
    i = argv.index("antmicro/renode:1.16.1")
    assert argv[i + 1:i + 3] == ["renode", "job.resc"]


def test_docker_argv_does_not_publish_ports():
    # Host networking exposes GDB ports directly; -p would be ignored by Docker.
    argv = docker.build_renode_argv("j.resc", "img")
    assert "-p" not in argv


def test_every_container_uses_host_network(monkeypatch):
    calls = []

    class _Proc:
        returncode, stdout = 0, ""

    monkeypatch.setattr(docker.subprocess, "run",
                        lambda cmd, **kw: calls.append(cmd) or _Proc())
    monkeypatch.setattr(docker.os, "makedirs", lambda *a, **kw: None)
    docker.run_build("true", "img")
    docker.run_in_container("true", "img")
    docker.run_renode_test("t.robot", "img", "res")
    docker.run_renode("j.resc", "img")
    assert len(calls) == 4
    assert all("--net=host" in cmd for cmd in calls)


def test_docker_argv_appends_extra_args_after_resc():
    argv = docker.build_renode_argv("j.resc", "img", extra_args=["--console", "--hide-log"])
    assert argv[-3:] == ["j.resc", "--console", "--hide-log"]


# ---- _runtime_flags ----

def test_runtime_flags_none():
    assert docker._runtime_flags(None) == []


def test_runtime_flags_root_and_caps():
    flags = docker._runtime_flags(RuntimeOptions(root=True, capabilities={"NET_ADMIN"}))
    assert "-u" in flags and "0:0" in flags
    assert flags[flags.index("--cap-add") + 1] == "NET_ADMIN"


def test_runtime_flags_device_present(monkeypatch):
    monkeypatch.setattr(docker.os.path, "exists", lambda p: p == "/dev/net/tun")
    flags = docker._runtime_flags(RuntimeOptions(devices={"/dev/net/tun"}))
    assert flags[flags.index("--device") + 1] == "/dev/net/tun"


def test_runtime_flags_all_devices_absent_yields_nothing(monkeypatch):
    # A requested device missing on the host must not fail the run, and (per the
    # docstring) no flags at all are applied so it drops to unprivileged dummy mode.
    monkeypatch.setattr(docker.os.path, "exists", lambda p: False)
    assert docker._runtime_flags(
        RuntimeOptions(devices={"/dev/net/tun"}, root=True)) == []


# ---- _user_flags ----

def test_user_flags_maps_host_uid(monkeypatch):
    monkeypatch.setattr(core, "host_uid_gid", lambda: (1000, 1000))
    assert docker._user_flags() == ["-u", "1000:1000"]


def test_user_flags_empty_without_uid(monkeypatch):
    monkeypatch.setattr(core, "host_uid_gid", lambda: None)
    assert docker._user_flags() == []


# ---- resolve_shell_image ----

def test_shell_image_explicit_wins():
    assert docker.resolve_shell_image({"image": "alpine"}, "default:img") == "alpine"


def test_shell_image_falls_back_to_default():
    assert docker.resolve_shell_image({}, "default:img") == "default:img"


def test_shell_image_no_docker_uses_default(monkeypatch):
    monkeypatch.setattr(core, "NO_DOCKER", True)
    assert docker.resolve_shell_image({"image": "alpine"}, "default:img") == "alpine"
