"""Unit tests for hector.reporters — JUnit XML and JSON manifest emission. Output is
parsed back and asserted structurally; no runner is executed."""

import json
import xml.etree.ElementTree as ET

from hector.reporters import REPORTERS, StepResult, emit, json_reporter, junit_reporter


def _results():
    return [
        StepResult(name="boots", type="robot", passed=True, duration=1.5,
                   commands=["Execute Command x"], stdout="ok"),
        StepResult(name="echo", type="shell", passed=False, duration=0.2,
                   stderr="boom", artifacts={"log": "results/echo/log.html"}),
    ]


def test_registry_has_default_reporters():
    assert "junit" in REPORTERS and "json" in REPORTERS


def test_junit_structure(tmp_path):
    junit_reporter(_results(), str(tmp_path))
    root = ET.parse(tmp_path / "junit.xml").getroot()
    assert root.tag == "testsuite"
    assert root.get("tests") == "2" and root.get("failures") == "1"
    cases = root.findall("testcase")
    assert [c.get("name") for c in cases] == ["boots", "echo"]
    assert cases[0].get("classname") == "robot"
    # Only the failing case carries a <failure> element, with its stderr as the body.
    assert cases[0].find("failure") is None
    fail = cases[1].find("failure")
    assert fail is not None and fail.text == "boom"


def test_junit_system_out_includes_commands(tmp_path):
    junit_reporter(_results(), str(tmp_path))
    root = ET.parse(tmp_path / "junit.xml").getroot()
    sysout = root.findall("testcase")[0].find("system-out").text
    assert "Commands:" in sysout and "Execute Command x" in sysout


def test_json_manifest(tmp_path):
    json_reporter(_results(), str(tmp_path))
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["tests"] == 2
    assert manifest["failures"] == 1
    assert manifest["passed"] is False
    first, second = manifest["results"]
    assert first["status"] == "passed" and first["duration"] == 1.5
    assert second["status"] == "failed"
    assert second["artifacts"] == {"log": "results/echo/log.html"}


def test_json_all_passed_true(tmp_path):
    json_reporter([StepResult(name="a", type="robot", passed=True)], str(tmp_path))
    assert json.loads((tmp_path / "manifest.json").read_text())["passed"] is True


def test_emit_runs_multiple_reporters(tmp_path):
    emit(_results(), str(tmp_path), ["junit", "json"])
    assert (tmp_path / "junit.xml").exists()
    assert (tmp_path / "manifest.json").exists()


def test_emit_creates_output_dir(tmp_path):
    target = tmp_path / "nested" / "out"
    emit([StepResult(name="a", type="robot", passed=True)], str(target), ["junit"])
    assert (target / "junit.xml").exists()
