"""Argparse-level smoke tests: the parser wires every subcommand and its flags
correctly. No command is executed (parse_args only)."""

import pytest

from hector.commands import build_parser


def _parse(argv):
    return build_parser().parse_args(argv)


def test_all_subcommands_registered():
    parser = build_parser()
    # Each known subcommand must parse and bind an executable _command.
    for cmd in ("run", "test", "export", "validate", "init", "clean"):
        args = parser.parse_args([cmd])
        assert hasattr(args, "_command")
        assert args._command.name == cmd


def test_clean_flags():
    args = _parse(["clean", "--all", "--dry-run"])
    assert args.all is True and args.dry_run is True
    assert args.output == "results"
    assert _parse(["clean", "--output", "out", "-n"]).output == "out"


def test_unknown_subcommand_rejected():
    with pytest.raises(SystemExit):
        _parse(["frobnicate"])


def test_missing_subcommand_rejected():
    with pytest.raises(SystemExit):
        _parse([])


def test_run_no_start_flag():
    assert _parse(["run", "--no-start"]).no_start is True
    assert _parse(["run"]).no_start is False


def test_run_file_flag_default_and_override():
    assert _parse(["run"]).file == ".hector.yaml"
    assert _parse(["run", "-f", "board.yaml"]).file == "board.yaml"
    assert _parse(["run", "--file", "ci.yml"]).file == "ci.yml"


def test_run_debug_is_repeatable():
    args = _parse(["run", "--debug", "a:3333", "--debug", "b:3334"])
    assert args.debug == ["a:3333", "b:3334"]


def test_run_set_is_repeatable():
    args = _parse(["run", "--set", "BIN=fw.elf", "--set", "BOARD=nucleo"])
    assert args.set_args == ["BIN=fw.elf", "BOARD=nucleo"]


def test_no_docker_and_workspace_mount_mutually_exclusive():
    # Both target the docker-mode group; supplying both must be rejected.
    with pytest.raises(SystemExit):
        _parse(["run", "--no-docker", "--workspace-mount", "/mnt"])


def test_export_has_no_start_but_test_does_not():
    assert _parse(["export", "--no-start"]).no_start is True
    # `test` must always start the simulation, so it has no --no-start flag.
    with pytest.raises(SystemExit):
        _parse(["test", "--no-start"])


def test_validate_accepts_file_flag():
    assert _parse(["validate", "-f", "board.yml"]).file == "board.yml"
