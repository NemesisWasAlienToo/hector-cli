"""Unit tests for pure decision helpers in hector.pipeline: config-file discovery,
image pinning, --set/--reporters/--job/--debug parsing, and hub-registry building."""

from types import SimpleNamespace

import pytest

from hector.pipeline import (build_hubs_registry, filter_jobs, parse_debug_flag,
                             resolve_config_path, resolve_renode_image,
                             _resolve_reporters, _resolve_set_overrides)


# ---- resolve_config_path (.yaml <-> .yml) ----

def test_config_path_exact_match(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".hector.yaml").write_text("x")
    assert resolve_config_path(".hector.yaml") == ".hector.yaml"


def test_config_path_falls_back_to_yml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".hector.yml").write_text("x")
    # Asked for .yaml, only .yml exists -> use it.
    assert resolve_config_path(".hector.yaml") == ".hector.yml"


def test_config_path_falls_back_to_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "board.yaml").write_text("x")
    assert resolve_config_path("board.yml") == "board.yaml"


def test_config_path_returns_requested_when_neither_exists(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert resolve_config_path("missing.yaml") == "missing.yaml"


# ---- load_config_or_exit: the config's directory ----

@pytest.fixture
def config_in_subdir(tmp_path, monkeypatch):
    from hector import core, pipeline
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(core, "WORKSPACE_MOUNT", str(tmp_path))
    monkeypatch.setattr(core, "NO_DOCKER", False)
    monkeypatch.setattr(core, "CONFIG_DIR", None)
    monkeypatch.setattr(core, "EXTRA_MOUNTS", [])
    monkeypatch.setattr(core, "WORKSPACE_ROOT", None)
    monkeypatch.setattr(pipeline, "MOUNT_CONFIG_DIR", False)
    (tmp_path / "board").mkdir()
    (tmp_path / "board" / ".hector.yaml").write_text("renode:\n  image: '1.16.1'\n")
    return pipeline, core, tmp_path


def test_load_config_sets_config_dir(config_in_subdir, monkeypatch):
    pipeline, core, root = config_in_subdir
    monkeypatch.setattr(pipeline, "CONFIG_PATH", "board/.hector.yaml")
    pipeline.load_config_or_exit()
    assert core.CONFIG_DIR == str(root / "board")
    assert core.execution_dir() == str(root / "board")
    assert core.EXTRA_MOUNTS == []            # inside the cwd mount already


def test_load_config_rejects_removed_build_section(config_in_subdir, monkeypatch, capsys):
    pipeline, core, root = config_in_subdir
    (root / "board" / ".hector.yaml").write_text(
        "renode:\n  image: '1.16.1'\nbuild:\n  - script: 'true'\n")
    monkeypatch.setattr(pipeline, "CONFIG_PATH", "board/.hector.yaml")
    with pytest.raises(SystemExit):
        pipeline.load_config_or_exit()
    assert "renamed to 'prepare:'" in capsys.readouterr().err


def test_load_config_outside_cwd_is_mounted_too(config_in_subdir, monkeypatch):
    # Run from a sibling dir: the cwd stays the workspace mount, and ../board is
    # bind-mounted 1:1 so the config's paths and working dir are reachable.
    pipeline, core, root = config_in_subdir
    (root / "elsewhere").mkdir()
    monkeypatch.setattr(core, "WORKSPACE_MOUNT", str(root / "elsewhere"))
    monkeypatch.chdir(root / "elsewhere")
    monkeypatch.setattr(pipeline, "CONFIG_PATH", "../board/.hector.yaml")
    pipeline.load_config_or_exit()
    board = str((root / "board").resolve())
    assert core.EXTRA_MOUNTS == [board]
    assert core.execution_dir() == board
    assert core.to_container_path(core.from_config("fw.elf")) == f"{board}/fw.elf"


def test_workspace_mount_mounts_config_dir_there(config_in_subdir, monkeypatch):
    # Run from the parent with --workspace-mount /workspace: the config's dir is what's
    # mounted there and where execution happens; the cwd (.hector/, --output) is 1:1.
    pipeline, core, root = config_in_subdir
    monkeypatch.setattr(core, "WORKSPACE_MOUNT", "/workspace")
    monkeypatch.setattr(pipeline, "MOUNT_CONFIG_DIR", True)
    monkeypatch.setattr(pipeline, "CONFIG_PATH", "board/.hector.yaml")
    pipeline.load_config_or_exit()
    board, cwd = str((root / "board").resolve()), str(root.resolve())
    assert core.workspace_root() == board
    assert core.execution_dir() == "/workspace"
    assert core.to_container_path(core.from_config("fw/app.elf")) == "/workspace/fw/app.elf"
    assert core.EXTRA_MOUNTS == [cwd]
    assert core.to_container_path(".hector/resc/job_1.resc") == f"{cwd}/.hector/resc/job_1.resc"


def test_workspace_mount_from_config_dir_needs_no_extra_mount(config_in_subdir, monkeypatch):
    pipeline, core, root = config_in_subdir
    monkeypatch.chdir(root / "board")
    monkeypatch.setattr(core, "WORKSPACE_MOUNT", "/workspace")
    monkeypatch.setattr(pipeline, "MOUNT_CONFIG_DIR", True)
    monkeypatch.setattr(pipeline, "CONFIG_PATH", ".hector.yaml")
    pipeline.load_config_or_exit()
    assert core.execution_dir() == "/workspace"
    assert core.EXTRA_MOUNTS == []


# ---- apply_renode_docker_flags ----

def _renode(flags):
    return {"renode": {"image": "1.16.1", "docker-flags": flags}}


@pytest.mark.parametrize("cfg,flag,expected", [
    ({}, "", []),
    (_renode("-v /a:/a -e X=1"), "", ["-v", "/a:/a", "-e", "X=1"]),
    (_renode(["-v /a:/a", "--env 'Y=two words'"]), "",
     ["-v", "/a:/a", "--env", "Y=two words"]),
    (_renode("-v /a:/a"), "-v /b:/b", ["-v", "/a:/a", "-v", "/b:/b"]),  # flag appends
])
def test_apply_renode_docker_flags(monkeypatch, cfg, flag, expected):
    from hector import core, pipeline
    monkeypatch.setattr(core, "RENODE_DOCKER_FLAGS", [])
    monkeypatch.setattr(core, "NO_DOCKER", False)
    pipeline.apply_renode_docker_flags(cfg, SimpleNamespace(renode_docker_flags=flag))
    assert core.RENODE_DOCKER_FLAGS == expected


@pytest.mark.parametrize("cfg,warns", [(_renode("-v /a:/a"), True), ({}, False)])
def test_renode_docker_flags_warn_under_no_docker(monkeypatch, capsys, cfg, warns):
    from hector import core, pipeline
    monkeypatch.setattr(core, "RENODE_DOCKER_FLAGS", [])
    monkeypatch.setattr(core, "NO_DOCKER", True)
    pipeline.apply_renode_docker_flags(cfg, SimpleNamespace(renode_docker_flags=""))
    assert ("[WARN] --no-docker: renode docker flags '-v /a:/a' are ignored"
            in capsys.readouterr().out) == warns


# ---- resolve_renode_image ----

def test_image_from_config():
    args = SimpleNamespace(renode_image=None)
    tag, image = resolve_renode_image({"renode": {"image": "1.16.1"}}, args)
    assert tag == "v1.16.1" and image == "antmicro/renode:1.16.1"


def test_image_cli_overrides_config_and_strips_v():
    args = SimpleNamespace(renode_image="v1.15.0")
    tag, image = resolve_renode_image({"renode": {"image": "1.16.1"}}, args)
    assert tag == "v1.15.0" and image == "antmicro/renode:1.15.0"


@pytest.mark.parametrize("value,tag", [
    ("my-renode:1.16.1", "v1.16.1"),           # the source tag comes from the image tag
    ("ghcr.io/me/renode:v1.15.0", "v1.15.0"),
    ("my-renode:patched", None),               # unknown; only matters if source is needed
    ("localhost:5000/renode", None),           # a registry port isn't an image tag
])
def test_image_reference_is_used_as_is(value, tag):
    assert resolve_renode_image({"renode": {"image": value}},
                                SimpleNamespace(renode_image=None)) == (tag, value)


def test_image_missing_renode_raises():
    with pytest.raises(ValueError, match="renode.image"):
        resolve_renode_image({}, SimpleNamespace(renode_image=None))


# ---- _resolve_set_overrides ----

def test_set_overrides_basic_and_value_with_equals():
    args = SimpleNamespace(set_args=["BIN=fw.elf", "URL=a=b=c"])
    assert _resolve_set_overrides(args) == {"BIN": "fw.elf", "URL": "a=b=c"}


def test_set_overrides_empty():
    assert _resolve_set_overrides(SimpleNamespace(set_args=None)) == {}


def test_set_overrides_missing_equals_exits():
    with pytest.raises(SystemExit):
        _resolve_set_overrides(SimpleNamespace(set_args=["NOTAKEYVALUE"]))


# ---- _resolve_reporters ----

def test_reporters_default_is_junit():
    assert _resolve_reporters(None) == ["junit"]


def test_reporters_split_commas_and_dedupe_preserving_order():
    assert _resolve_reporters(["junit,json", "json", "html"]) == ["junit", "json", "html"]


# ---- build_hubs_registry ----

def test_hubs_registry_maps_name_to_type():
    assert build_hubs_registry({"link": {"type": "uart"}}) == {"link": "uart"}


def test_hubs_registry_missing_type_raises():
    with pytest.raises(ValueError, match="missing required 'type'"):
        build_hubs_registry({"link": {}})


def test_hubs_registry_unknown_type_raises():
    with pytest.raises(ValueError, match="unknown type"):
        build_hubs_registry({"link": {"type": "quantum-entangler"}})


# ---- parse_debug_flag ----

def test_debug_flag_valid():
    assert parse_debug_flag(["mcu:3333"], {"mcu": {}}, 1) == {"mcu": 3333}


def test_debug_flag_missing_colon_raises():
    with pytest.raises(ValueError, match="NODE:PORT"):
        parse_debug_flag(["mcu3333"], {"mcu": {}}, 1)


def test_debug_flag_non_numeric_port_raises():
    with pytest.raises(ValueError, match="must be a number"):
        parse_debug_flag(["mcu:abc"], {"mcu": {}}, 1)


def test_debug_flag_unknown_node_skipped_when_validating():
    assert parse_debug_flag(["ghost:3333"], {"mcu": {}}, 1) == {}


def test_debug_flag_skips_node_check_in_snapshot_mode():
    assert parse_debug_flag(["anything:3333"], {}, 1, validate_nodes=False) == {
        "anything": 3333}


# ---- filter_jobs ----

JOBS = [{"BOARD": "a", "N": 1}, {"BOARD": "b", "N": 1}, {"BOARD": "b", "N": 2}]


def test_filter_single_key():
    assert filter_jobs(JOBS, "BOARD=b") == [{"BOARD": "b", "N": 1}, {"BOARD": "b", "N": 2}]


def test_filter_numeric_compares_as_string():
    assert filter_jobs(JOBS, "N=2") == [{"BOARD": "b", "N": 2}]


def test_filter_multi_key():
    assert filter_jobs(JOBS, "BOARD=b,N=1") == [{"BOARD": "b", "N": 1}]


def test_filter_no_match_raises():
    with pytest.raises(ValueError, match="no matrix combination matches"):
        filter_jobs(JOBS, "BOARD=zzz")


def test_filter_bad_spec_raises():
    with pytest.raises(ValueError, match="not KEY=VALUE"):
        filter_jobs(JOBS, "BOARD")


def test_load_config_rejects_the_renode_short_form(config_in_subdir, monkeypatch, capsys):
    pipeline, core, root = config_in_subdir
    (root / "board" / ".hector.yaml").write_text("renode: '1.16.1'\n")
    monkeypatch.setattr(pipeline, "CONFIG_PATH", "board/.hector.yaml")
    with pytest.raises(SystemExit):
        pipeline.load_config_or_exit()
    assert 'image: "1.16.1"' in capsys.readouterr().err
