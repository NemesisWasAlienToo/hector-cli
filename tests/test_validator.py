"""Unit tests for hector.validator.validate_config.

The strongest, least-brittle contract: every shipped example must validate with **no errors**
(warnings are allowed). This catches schema drift the moment an example or the validator changes.
Plus a few targeted checks on unambiguous validator rules.
"""

import glob
from pathlib import Path

import pytest
import yaml

from hector.validator import validate_config

EXAMPLES = sorted(glob.glob(str(Path(__file__).resolve().parents[1] / "examples" / "*" / ".hector.yaml")))


@pytest.mark.parametrize("path", EXAMPLES, ids=[Path(p).parent.name for p in EXAMPLES])
def test_shipped_examples_have_no_errors(path):
    cfg = yaml.safe_load(Path(path).read_text())
    errors, _warnings = validate_config(cfg)
    assert errors == [], f"{path}: " + "; ".join(f"{i.path}: {i.message}" for i in errors)


def test_examples_were_discovered():
    # Guard against the glob silently matching nothing (which would make the suite vacuous).
    assert EXAMPLES, "no example .hector.yaml files found"


def test_non_mapping_config_is_error():
    errors, _ = validate_config(["not", "a", "map"])
    assert len(errors) == 1
    assert errors[0].path == "(root)"


def test_missing_renode_is_error():
    errors, _ = validate_config({"machines": {"m": {}}})
    assert any(i.path == "renode" for i in errors)


@pytest.mark.parametrize("value", ["1.16.1", "my-renode:dev", "ghcr.io/me/renode:1.16.1"])
def test_renode_image_accepts_a_version_or_an_image(value):
    errors, _ = validate_config({"renode": {"image": value}})
    assert errors == []


def test_renode_short_form_is_error():
    errors, _ = validate_config({"renode": "1.16.1"})
    assert [e.path for e in errors] == ["renode"]
    assert 'image: "1.16.1"' in errors[0].message


def test_renode_needs_an_image():
    errors, _ = validate_config({"renode": {"docker-flags": "-e X=1"}})
    assert [e.path for e in errors] == ["renode.image"]


@pytest.mark.parametrize("key", ["renode_version", "renode_image"])
def test_old_renode_keys_are_errors(key):
    errors, _ = validate_config({key: "1.16.1"})
    assert [e.path for e in errors] == [key]
    assert "renode.image" in errors[0].message


def test_prepare_steps_validate_like_shell_steps():
    errors, warnings = validate_config({"renode": {"image": "1.16.1"}, "prepare": [
        {"name": "img", "script": "docker build -t r:1 ."},
        {"name": "fw", "image": "alpine:3.19", "steps": [{"name": "s", "script": "true"}]},
    ]})
    assert errors == [] and warnings == []


@pytest.mark.parametrize("key", ["requires-machine", "type"])
def test_prepare_steps_cannot_start_the_sim(key):
    errors, _ = validate_config({"renode": {"image": "1.16.1"},
                                 "prepare": [{"name": "x", "script": "true", key: True}]})
    assert [e.path for e in errors] == [f"prepare[0].{key}"]


@pytest.mark.parametrize("value", ["-v /a:/a", ["-v /a:/a", "-e X=1"]])
def test_docker_flags_accept_string_or_list(value):
    errors, warnings = validate_config({
        "renode": {"image": "1.16.1", "docker-flags": value},
        "prepare": [{"name": "p", "image": "alpine", "script": "true", "docker-flags": value}],
        "tests": [{"name": "t", "type": "shell", "script": "true", "docker-flags": value}]})
    assert errors == [] and warnings == []


def test_docker_flags_wrong_type_is_error():
    errors, _ = validate_config({"renode": {"image": "1.16.1", "docker-flags": {"v": "/a"}}})
    assert [e.path for e in errors] == ["renode.docker-flags"]


def test_global_docker_args_is_error():
    errors, _ = validate_config({"renode": {"image": "1.16.1"}, "docker_args": "-v /a:/a"})
    assert [e.path for e in errors] == ["docker_args"]
    assert "renode.docker-flags" in errors[0].message


def test_docker_flags_need_a_container():
    errors, _ = validate_config({
        "renode": {"image": "1.16.1"},
        "prepare": [{"name": "host", "script": "true", "docker-flags": "-e X=1"}],
        "tests": [{"name": "r", "type": "robot", "script": "x", "docker-flags": "-e X=1"}]})
    assert [e.path for e in errors] == ["prepare[0].docker-flags", "tests[0].docker-flags"]


def test_unknown_module_kind_is_error():
    cfg = {"renode": {"image": "1.16.1"},
           "modules": {"u": {"kind": "bogus", "type": "X", "source": "s"}}}
    errors, _ = validate_config(cfg)
    assert any(i.path == "modules.u.kind" for i in errors)


def test_module_missing_type_is_error():
    cfg = {"renode": {"image": "1.16.1"}, "modules": {"u": {"kind": "csharp", "source": "s.dll"}}}
    errors, _ = validate_config(cfg)
    assert any(i.path == "modules.u.type" for i in errors)


# ---- top-level keys ----

def _base(**extra):
    cfg = {"renode": {"image": "1.16.1"}}
    cfg.update(extra)
    return cfg


def test_unknown_top_level_key_warns():
    _errors, warnings = validate_config(_base(mahcines={}))
    assert any(w.path == "mahcines" for w in warnings)


def test_renamed_top_level_key_warns():
    _errors, warnings = validate_config(_base(nodes={}))
    assert any("machines" in w.message for w in warnings if w.path == "nodes")


@pytest.mark.parametrize("key", ["build", "setup"])
def test_old_build_section_is_error(key):
    # Silently skipping it (e.g. a firmware fetch) would break every later test.
    errors, _ = validate_config(_base(**{key: [{"name": "x", "script": "true"}]}))
    assert any(i.path == key and "'prepare:'" in i.message for i in errors)


# ---- machine schema: platform / repl / resc ----

def test_platform_must_be_a_list():
    errors, _ = validate_config(_base(machines={"m": {"platform": "board.repl"}}))
    assert any(i.path == "machines.m.platform" for i in errors)


def test_inline_repl_wrong_type_is_error():
    errors, _ = validate_config(_base(machines={"m": {"repl": 123}}))
    assert any(i.path == "machines.m.repl" for i in errors)


def test_inline_resc_wrong_type_is_error():
    errors, _ = validate_config(_base(machines={"m": {"resc": {"not": "text"}}}))
    assert any(i.path == "machines.m.resc" for i in errors)


def test_inline_repl_and_resc_accept_block_and_list():
    errors, _ = validate_config(_base(machines={
        "m": {"repl": "cpu: CPU.CortexM @ sysbus", "resc": ["sysbus Tag x"]}}))
    assert errors == []


# ---- hubs ----

def test_hub_missing_type_is_error():
    errors, _ = validate_config(_base(hubs={"link": {}}))
    assert any(i.path == "hubs.link.type" for i in errors)


def test_unknown_hub_type_is_error():
    errors, _ = validate_config(_base(hubs={"link": {"type": "warp-drive"}}))
    assert any(i.path == "hubs.link.type" for i in errors)


# ---- tests ----

def test_unknown_test_type_is_error():
    errors, _ = validate_config(_base(tests=[{"name": "t", "type": "quantum"}]))
    assert any(i.path == "tests[0].type" for i in errors)


def test_renamed_test_type_warns_not_errors():
    errors, warnings = validate_config(_base(tests=[{"name": "t", "type": "bash",
                                                     "steps": []}]))
    assert not any(i.path == "tests[0].type" for i in errors)
    assert any(w.path == "tests[0].type" for w in warnings)


# ---- CI trigger keys are accepted silently (owned by the CI server) ----

def test_trigger_keys_produce_no_warnings():
    cfg = _base(
        when={"branch": ["main", "release/*"],
              "event": ["push", "pull_request", "manual", "cron"],
              "path": ["cli/**"]},
        cron="0 3 * * *", reporters=["json", "junit"],
        jobs=1, fail_fast=True, timeout="30m",
    )
    errors, warnings = validate_config(cfg)
    assert errors == []
    trigger_keys = {"when", "cron", "reporters", "jobs", "fail_fast", "timeout"}
    assert not any(w.path.split(".")[0] in trigger_keys for w in warnings)


def test_obsolete_ci_block_now_warns_as_unknown():
    # The nested `ci:` schema was removed; it must now read as an unknown top-level key.
    _errors, warnings = validate_config(_base(ci={"hil": {"when": {}}}))
    assert any(w.path == "ci" for w in warnings)


def test_schema_0_1_is_error_with_the_changes():
    errors, _ = validate_config({"version": "0.1", "renode": {"image": "1.16.1"}})
    assert [e.path for e in errors] == ["version"]
    assert "renode:" in errors[0].message and "requires-machine" in errors[0].message


def test_requires_sim_is_renamed():
    errors, _ = validate_config({"renode": {"image": "1.16.1"}, "tests": [
        {"name": "t", "type": "shell", "script": "true", "requires_sim": True}]})
    assert [e.path for e in errors] == ["tests[0].requires_sim"]
