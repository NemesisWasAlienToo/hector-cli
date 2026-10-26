# SPDX-License-Identifier: AGPL-3.0-or-later
"""
TEST_RUNNERS — per-type test execution, dispatched by run_tests().

Each runner has the signature:
    (test: dict, steps: list, ctx: RunnerContext, index: int) -> list[StepResult]

Register a custom type:
    @TEST_RUNNERS.register("pytest")
    def run_pytest(test, steps, ctx, index):
        ...
        return [StepResult(name=..., type="pytest", passed=..., stdout=...)]
"""

import html as _html
import os
import re
import shlex
import time
from dataclasses import dataclass, field

from . import core as _core
from .core import ARTIFACTS_DIR, Registry, from_config, to_container_path
from .docker import resolve_shell_image, run_in_container, run_renode_test
from .reporters import StepResult

TEST_RUNNERS = Registry("test runner")


@dataclass
class RunnerContext:
    resc_host_path: str                            # generated emulation resc
    job_index: int                                 # 1-based
    image: str                                     # antmicro/renode:<version>
    reporters: list = field(default_factory=lambda: ["junit"])
    results_dir: str = "results"
    renode_test_args: list = field(default_factory=list)
    live: bool = False
    snapshot: str = ""
    runtime: object = None      # RuntimeOptions: docker caps/devices/root for the run


# ── helpers ───────────────────────────────────────────────────────────────────

def _parse_extra_args(obj):
    raw = obj.get("args")
    if not raw:
        return []
    return raw if isinstance(raw, list) else shlex.split(str(raw))


def _normalize_steps(test):
    """Backward compat: test with top-level script:/file: treated as a single step."""
    if "steps" in test:
        return test["steps"]
    return [{"name": test.get("name", ""), "script": test.get("script", ""), "file": test.get("file")}]


def _test_results_dir(base, test_index, name):
    slug = re.sub(r"[^\w-]", "_", name)[:40]
    return os.path.join(base, f"test_{test_index}_{slug}")


def _render_output_pre(output):
    """Escape captured output; highlight `set -x` command-trace lines (starting '+')."""
    out_lines = []
    for line in output.splitlines():
        esc = _html.escape(line)
        out_lines.append(f'<span class="cmd-trace">{esc}</span>'
                         if line.startswith("+") else esc)
    return "<br>".join(out_lines) or "(no output)"


def _write_shell_html(test_dir, test_name, step_records, passed, duration):
    """Write results/test_N_<name>/report.html for a whole shell test.

    Mirrors robot's per-test layout (one report at the test directory level), with
    one section per step. `step_records` is a list of
    {name, passed, duration, output} dicts.
    """
    os.makedirs(test_dir, exist_ok=True)
    status_cls = "pass" if passed else "fail"
    status_text = "PASS" if passed else "FAIL"

    sections = []
    for rec in step_records:
        s_cls = "pass" if rec["passed"] else "fail"
        s_txt = "PASS" if rec["passed"] else "FAIL"
        sections.append(
            f'<h2>{_html.escape(rec["name"])} '
            f'<span class="badge {s_cls}">{s_txt}</span> '
            f'<span class="dur">{rec["duration"]:.2f}s</span></h2>\n'
            f'<pre>{_render_output_pre(rec["output"])}</pre>'
        )

    content = (
        '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        f'<title>{_html.escape(test_name)}</title>\n'
        '<style>\n'
        '*{box-sizing:border-box;margin:0;padding:0}\n'
        'body{font-family:"Consolas","Courier New",monospace;background:#1e1e1e;'
        'color:#d4d4d4;padding:24px;font-size:13px;line-height:1.5}\n'
        'h1{color:#9cdcfe;font-size:18px;margin-bottom:6px}\n'
        'h2{color:#c586c0;font-size:14px;margin:20px 0 6px}\n'
        '.meta{color:#808080;margin-bottom:24px;font-size:12px}\n'
        '.dur{color:#808080;font-weight:400;font-size:12px}\n'
        '.badge{font-weight:700;padding:2px 8px;border-radius:3px}\n'
        '.pass{color:#4ec9b0}.fail{color:#f44747}\n'
        'pre{background:#252526;border-left:3px solid #555;padding:12px;'
        'overflow-x:auto;white-space:pre-wrap;word-break:break-all}\n'
        '.cmd-trace{color:#dcdcaa}\n'
        '</style>\n</head>\n<body>\n'
        f'<h1>{_html.escape(test_name)}</h1>\n'
        '<div class="meta">'
        f'Status: <span class="badge {status_cls}">{status_text}</span>'
        f'&nbsp;&nbsp;Duration: {duration:.2f}s'
        '</div>\n'
        + "\n".join(sections) +
        '\n</body>\n</html>'
    )
    path = os.path.join(test_dir, "report.html")
    with open(path, "w") as f:
        f.write(content)
    return path


def generate_robot_file(test_name, steps, resc_host_path, job_index, test_index, snapshot=""):
    """Generate a .robot suite: one keyword per step, one test case that calls them in order.

    One test case means Renode's per-test lifecycle fires exactly once — no inter-step teardowns.
    run_tests.py injects Suite Setup Setup (since we define none), which establishes the
    Remote library connection. The test case boots the emulation, then calls each keyword.
    """
    test_dir = os.path.join(ARTIFACTS_DIR, "tests")
    os.makedirs(test_dir, exist_ok=True)

    keywords = []
    for step_idx, step in enumerate(steps):
        kw_name = step.get("name") or f"Step {step_idx + 1}"
        body = [f"    {l.strip()}" for l in (step.get("script") or "").splitlines() if l.strip()]
        if not body:
            body = ["    No Operation"]
        keywords.append(kw_name + "\n" + "\n".join(body))

    if snapshot:
        boot = [f"    Execute Command    Load @{to_container_path(snapshot)}",
                "    Execute Command    start"]
    else:
        boot = [f"    Execute Command    include @{to_container_path(resc_host_path)}"]

    kw_calls = [f"    {step.get('name') or f'Step {i + 1}'}" for i, step in enumerate(steps)]
    test_case = test_name + "\n" + "\n".join(boot + kw_calls)

    content = (
        "*** Keywords ***\n"
        + "\n\n".join(keywords) + "\n\n"
        + "*** Test Cases ***\n"
        + test_case + "\n"
    )

    path = os.path.join(test_dir, f"job_{job_index}_test_{test_index}.robot")
    with open(path, "w") as f:
        f.write(content)
    return path


# ── test runners ──────────────────────────────────────────────────────────────

def _run_robot_test(test, steps, ctx, test_index):
    """Run a robot test. Returns a single StepResult for the whole test."""
    test_name = test.get("name", f"test_{test_index}")
    effective_snapshot = ctx.snapshot or from_config(test.get("snapshot", ""))
    if effective_snapshot and not os.path.isfile(effective_snapshot):
        raise FileNotFoundError(f"Snapshot not found: {effective_snapshot}")

    extra_args = _parse_extra_args(test) + ctx.renode_test_args
    if ctx.live:
        extra_args += ["--verbose"]
    interactive = test.get("interactive", False)

    print(f"\n[TEST] {test_name}")
    if effective_snapshot:
        print(f"  [SNAP] {effective_snapshot}")
    for step in steps:
        print(f"  {step.get('name', '?')}")

    test_dir = _test_results_dir(ctx.results_dir, test_index, test_name)

    if len(steps) == 1 and steps[0].get("file"):
        if effective_snapshot:
            print("  [WARN] snapshot ignored for file-based robot tests.")
        robot_file = from_config(steps[0]["file"])
    else:
        if any(s.get("file") for s in steps):
            raise ValueError(f"Test '{test_name}': mixing file: and script: steps is not supported.")
        robot_file = generate_robot_file(
            test_name, steps, ctx.resc_host_path, ctx.job_index, test_index,
            snapshot=effective_snapshot,
        )

    t0 = time.monotonic()
    passed = run_renode_test(robot_file, ctx.image, test_dir,
                             resc_host_path=ctx.resc_host_path,
                             extra_args=extra_args, interactive=interactive,
                             runtime=ctx.runtime)
    duration = time.monotonic() - t0
    # Register renode-test's own per-test reports so the manifest can deep-link them.
    # 'report_html' is the same key bash uses, so a dashboard finds it uniformly.
    artifacts = {}
    for label, fname in (("report_html", "report.html"),
                         ("log_html", "log.html"),
                         ("robot_xml", "robot_output.xml")):
        fpath = os.path.join(test_dir, fname)
        if os.path.exists(fpath):
            artifacts[label] = fpath
    return [StepResult(
        name=test_name, type="robot", passed=passed, duration=duration,
        artifacts=artifacts,
    )]


def _run_shell_test(test, steps, ctx, test_index):
    """Run all steps of a shell test, each in a one-off container of the resolved image
    (or on the host under --no-docker). One StepResult per test, one report.html —
    mirrors the robot layout (a multi-step test is a single row named after the test).
    """
    test_name = test.get("name", f"test_{test_index}")
    image = resolve_shell_image(test, ctx.image, label=test_name)
    test_dir = _test_results_dir(ctx.results_dir, test_index, test_name)
    where = "host" if _core.NO_DOCKER else f"image: {image}"
    print(f"\n[TEST] {test_name}  (shell, {where})")

    step_records = []
    all_commands = []
    combined_stdout = []
    total_duration = 0.0
    all_passed = True

    for step_idx, step in enumerate(steps):
        step_name = step.get("name", f"step_{step_idx}")
        script = step.get("script", "")
        print(f"  {step_name}")

        t0 = time.monotonic()
        stdout, passed = run_in_container(script, image, ctx.live)
        duration = time.monotonic() - t0

        total_duration += duration
        all_passed = all_passed and passed
        all_commands.extend(l for l in script.splitlines() if l.strip())
        combined_stdout.append(f"# {step_name}\n{stdout}".rstrip())
        step_records.append({"name": step_name, "passed": passed,
                             "duration": duration, "output": stdout})

    html_path = _write_shell_html(test_dir, test_name, step_records,
                                  all_passed, total_duration)
    return [StepResult(
        name=test_name, type="shell", passed=all_passed, duration=total_duration,
        commands=all_commands, stdout="\n\n".join(combined_stdout), stderr="",
        artifacts={"report_html": html_path},
    )]


# ── registry entries for built-in types ──────────────────────────────────────

@TEST_RUNNERS.register("robot")
def robot_runner(test, steps, ctx, index):
    return _run_robot_test(test, steps, ctx, index)


@TEST_RUNNERS.register("shell")
def shell_runner(test, steps, ctx, index):
    return _run_shell_test(test, steps, ctx, index)


# Test types renamed in this schema version → current name. Old configs still run;
# the validator emits a matching migration warning.
_RENAMED_TEST_TYPES = {"bash": "shell", "docker": "shell"}


# ── pre-sim build steps ───────────────────────────────────────────────────────

def run_build_steps(blocks, default_image, results_dir, live=False):
    """Run the pre-sim `build:` steps (compile firmware, generate/fetch files, ...).

    Each block is a shell step run in a container of its image (or on the host under
    --no-docker), with the project bind-mounted — so anything it writes into the project
    is there for the sim and tests. Returns one StepResult per block (type "build") so
    builds are reported like tests; stops at the first failing block, because the
    simulation depends on these outputs (the caller skips the sim when one fails).
    """
    if not blocks:
        return []
    print("\n[BUILD] preparing inputs ...")
    results = []
    for b_idx, block in enumerate(blocks):
        block = block or {}
        name = block.get("name", f"build_{b_idx}")
        image = resolve_shell_image(block, default_image, label=name)
        where = "host" if _core.NO_DOCKER else f"image: {image}"
        print(f"  {name}  ({where})")

        step_records = []
        all_commands = []
        combined_stdout = []
        total_duration = 0.0
        all_passed = True

        for step_idx, step in enumerate(_normalize_steps(block)):
            script = step.get("script", "")
            if not script.strip():
                continue
            step_name = step.get("name", f"step_{step_idx}")
            t0 = time.monotonic()
            stdout, passed = run_in_container(script, image, live)
            duration = time.monotonic() - t0
            total_duration += duration
            all_passed = all_passed and passed
            all_commands.extend(l for l in script.splitlines() if l.strip())
            combined_stdout.append(f"# {step_name}\n{stdout}".rstrip())
            step_records.append({"name": step_name, "passed": passed,
                                 "duration": duration, "output": stdout})

        slug = re.sub(r"[^\w-]", "_", name)[:40]
        build_dir = os.path.join(results_dir, f"build_{b_idx}_{slug}")
        html_path = _write_shell_html(build_dir, name, step_records,
                                      all_passed, total_duration)
        results.append(StepResult(
            name=name, type="build", passed=all_passed, duration=total_duration,
            commands=all_commands, stdout="\n\n".join(combined_stdout), stderr="",
            artifacts={"report_html": html_path}))
        if not all_passed:
            print(f"[BUILD] '{name}' failed — aborting build.")
            break
    return results


# ── driver ────────────────────────────────────────────────────────────────────

def _needs_sim(test):
    """Whether a test requires the Renode simulation (the generated resc). Robot tests
    always do; others honour `requires_sim` (default True)."""
    rtype = _RENAMED_TEST_TYPES.get(test.get("type", "robot"), test.get("type", "robot"))
    if rtype == "robot":
        return True
    return bool(test.get("requires_sim", True))


def run_tests(tests, ctx, fail_fast=False):
    """Execute tests in order, returning their StepResults (the caller emits the reports,
    combined with the build steps'). Sim-backed tests get their own Renode session; a test
    that needs the sim but has no generated resc (no machines) fails with a clear note.
    With fail_fast, stop after the first failing test."""
    results = []
    for i, test in enumerate(tests):
        rtype = test.get("type", "robot")
        if rtype in _RENAMED_TEST_TYPES:
            new = _RENAMED_TEST_TYPES[rtype]
            print(f"[WARN] test type '{rtype}' was renamed to '{new}' — update 'type:'.")
            rtype = new
            test = {**test, "type": new}

        if _needs_sim(test) and not ctx.resc_host_path:
            name = test.get("name", f"test_{i}")
            print(f"\n[TEST] {name}\n  [SKIP] needs a simulation but no machine is "
                  "defined (set 'requires_sim: false' for a sim-independent test).")
            results.append(StepResult(
                name=name, type=rtype, passed=False, duration=0.0,
                stderr="requires a simulation but no machine/resc is available"))
        else:
            runner = TEST_RUNNERS.get(rtype)
            results.extend(runner(test, _normalize_steps(test), ctx, i))

        if fail_fast and not results[-1].passed:
            remaining = len(tests) - (i + 1)
            if remaining:
                print(f"\n[FAIL-FAST] Stopping after a failing test ({remaining} skipped).")
            break
    return results
