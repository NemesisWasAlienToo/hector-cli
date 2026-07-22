"""Unit tests for hector.core.resolve_arguments — precedence: --set > env > default."""

from hector.core import resolve_arguments


def test_default_when_no_override(monkeypatch):
    monkeypatch.delenv("BIN", raising=False)
    assert resolve_arguments({"BIN": "default.elf"}) == {"BIN": "default.elf"}


def test_cli_override_wins_over_default():
    assert resolve_arguments({"BIN": "default.elf"}, {"BIN": "cli.elf"}) == {"BIN": "cli.elf"}


def test_env_used_when_no_cli(monkeypatch):
    monkeypatch.setenv("BIN", "env.elf")
    assert resolve_arguments({"BIN": "default.elf"}) == {"BIN": "env.elf"}


def test_cli_override_wins_over_env(monkeypatch):
    monkeypatch.setenv("BIN", "env.elf")
    assert resolve_arguments({"BIN": "default.elf"}, {"BIN": "cli.elf"}) == {"BIN": "cli.elf"}


def test_undeclared_override_is_added():
    out = resolve_arguments({"A": "1"}, {"B": "2"})
    assert out == {"A": "1", "B": "2"}


def test_empty_arguments():
    assert resolve_arguments(None) == {}
    assert resolve_arguments({}) == {}
