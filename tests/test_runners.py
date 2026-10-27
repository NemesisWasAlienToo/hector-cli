"""Unit tests for pure helpers in hector.runners: extra-arg parsing, step
normalization, results-dir slugging, output escaping, and sim-requirement logic, plus
the shell runner's background-sim flow with Renode/Docker faked out."""

import pytest

from hector.runners import (TEST_RUNNERS, _needs_sim, _normalize_steps,
                            _parse_extra_args, _render_output_pre, _test_results_dir)


def test_registry_has_runners():
    assert "robot" in TEST_RUNNERS and "shell" in TEST_RUNNERS


# ---- _parse_extra_args ----

def test_extra_args_list_passthrough():
    assert _parse_extra_args({"args": ["--a", "--b"]}) == ["--a", "--b"]


def test_extra_args_string_is_shlex_split():
    assert _parse_extra_args({"args": "--loglevel DEBUG --x"}) == [
        "--loglevel", "DEBUG", "--x"]


def test_extra_args_absent():
    assert _parse_extra_args({}) == []


# ---- _normalize_steps ----

def test_normalize_returns_steps_when_present():
    steps = [{"name": "s1", "script": "echo hi"}]
    assert _normalize_steps({"steps": steps}) is steps


def test_normalize_wraps_legacy_top_level_script():
    test = {"name": "legacy", "script": "echo hi"}
    out = _normalize_steps(test)
    assert out == [{"name": "legacy", "script": "echo hi", "file": None}]


# ---- _test_results_dir ----

def test_results_dir_slugs_and_truncates():
    out = _test_results_dir("results", 0, "Button press: triggers UART!")
    assert out.startswith("results/test_0_")
    tail = out.rsplit("test_0_", 1)[1]
    assert "/" not in tail and " " not in tail and "!" not in tail
    assert len(tail) <= 40


# ---- _render_output_pre ----

def test_render_escapes_html():
    assert "&lt;script&gt;" in _render_output_pre("<script>")


def test_render_highlights_command_trace_lines():
    html = _render_output_pre("+ echo hi\nregular")
    assert 'class="cmd-trace"' in html
    # Only the '+'-prefixed trace line is wrapped.
    assert html.count("cmd-trace") == 1


def test_render_empty_output():
    assert _render_output_pre("") == "(no output)"


# ---- _needs_sim ----

def test_robot_always_needs_sim():
    assert _needs_sim({"type": "robot"}) is True


def test_shell_defaults_to_no_sim():
    # A shell test (fetch/compile/check) runs without a sim unless it asks for one.
    assert _needs_sim({"type": "shell"}) is False


def test_shell_can_opt_in():
    assert _needs_sim({"type": "shell", "requires_sim": True}) is True


def test_renamed_bash_type_defaults_to_no_sim():
    assert _needs_sim({"type": "bash"}) is False


# ---- shell test with requires_sim: true ----

class _FakeSim:
    """Stands in for BackgroundRenode; records what the runner asks of it."""
    calls = []

    def __init__(self, image, log_path, runtime=None):
        self.port = 4567
        _FakeSim.calls.append(("start", image, log_path))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        _FakeSim.calls.append(("stop",))

    def include(self, resc):
        _FakeSim.calls.append(("include", resc))

    def command(self, line):
        _FakeSim.calls.append(("command", line))

    def release(self):
        _FakeSim.calls.append(("release",))


@pytest.fixture
def shell_env(monkeypatch, tmp_path):
    from hector import runners
    monkeypatch.chdir(tmp_path)
    _FakeSim.calls = []
    steps_seen = []
    monkeypatch.setattr(runners, "BackgroundRenode", _FakeSim)
    monkeypatch.setattr(runners, "run_in_container",
                        lambda script, image, live, env=None:
                        steps_seen.append(env) or ("ok", True))
    ctx = runners.RunnerContext(resc_host_path="job.resc", job_index=1, image="img")
    return runners, ctx, steps_seen


def test_requires_sim_runs_steps_inside_a_background_sim(shell_env):
    runners, ctx, steps_seen = shell_env
    test = {"name": "t", "type": "shell", "requires_sim": True}
    [res] = runners._run_shell_test(test, [{"script": "true"}], ctx, 0)
    assert res.passed
    kinds = [c[0] for c in _FakeSim.calls]
    assert kinds == ["start", "include", "release", "stop"]
    assert steps_seen == [{"HECTOR_MONITOR_PORT": 4567}]
    assert res.artifacts["renode_log"].endswith("renode.log")


def test_shell_without_requires_sim_starts_nothing(shell_env):
    runners, ctx, steps_seen = shell_env
    [res] = runners._run_shell_test({"name": "t", "type": "shell"}, [{"script": "true"}], ctx, 0)
    assert res.passed and _FakeSim.calls == [] and steps_seen == [None]


def test_sim_start_failure_fails_the_test(shell_env, monkeypatch):
    runners, ctx, steps_seen = shell_env

    def boom(self, resc):
        raise RuntimeError("'include @job.resc' failed")
    monkeypatch.setattr(_FakeSim, "include", boom)
    [res] = runners._run_shell_test({"name": "t", "type": "shell", "requires_sim": True},
                                    [{"script": "true"}], ctx, 0)
    assert not res.passed and steps_seen == []
    assert ("stop",) in _FakeSim.calls               # the sim is still torn down
