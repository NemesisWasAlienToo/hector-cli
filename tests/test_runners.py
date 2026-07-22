"""Unit tests for pure helpers in hector.runners: extra-arg parsing, step
normalization, results-dir slugging, output escaping, and sim-requirement logic.
The actual robot/shell execution (which needs Renode/Docker) is not exercised."""

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


def test_shell_defaults_to_needing_sim():
    assert _needs_sim({"type": "shell"}) is True


def test_shell_can_opt_out():
    assert _needs_sim({"type": "shell", "requires_sim": False}) is False


def test_renamed_bash_type_still_needs_sim_by_default():
    assert _needs_sim({"type": "bash"}) is True
