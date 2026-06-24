# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Pluggable test-result reporters.

Register a custom reporter:
    from hector.reporters import REPORTERS

    @REPORTERS.register("csv")
    def csv_reporter(results, output_dir):
        import csv, os
        with open(os.path.join(output_dir, "results.csv"), "w") as f:
            w = csv.DictWriter(f, fieldnames=["name","type","passed","duration"])
            w.writeheader()
            for r in results:
                w.writerow({"name": r.name, "type": r.type,
                            "passed": r.passed, "duration": r.duration})
"""

import json
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from .core import Registry

REPORTERS = Registry("reporter")


@dataclass
class StepResult:
    """Outcome of a single test step, passed to every reporter after the run."""
    name: str
    type: str           # "robot", "shell", "build", …
    passed: bool
    duration: float = 0.0
    commands: list = field(default_factory=list)  # script lines / commands run
    stdout: str = ""                              # captured stdout (bash) or trimmed log
    stderr: str = ""                              # captured stderr
    artifacts: dict = field(default_factory=dict) # {label: abs_path}


def emit(results, output_dir, reporter_names):
    """Call each named reporter with the full result list."""
    os.makedirs(output_dir, exist_ok=True)
    for name in reporter_names:
        fn = REPORTERS.get(name)
        fn(results, output_dir)


@REPORTERS.register("junit")
def junit_reporter(results, output_dir):
    """JUnit XML — compatible with GitLab CI, GitHub Actions, and Jenkins."""
    failures = sum(1 for r in results if not r.passed)
    suite = ET.Element(
        "testsuite",
        name="hector",
        tests=str(len(results)),
        failures=str(failures),
        time=f"{sum(r.duration for r in results):.3f}",
    )
    for r in results:
        tc = ET.SubElement(
            suite, "testcase",
            name=r.name, classname=r.type,
            time=f"{r.duration:.3f}",
        )
        out = "\n".join(filter(None, [r.stdout.strip(), r.stderr.strip()]))
        parts = []
        if r.commands:
            parts.append("Commands:\n" + "\n".join(f"  {c}" for c in r.commands))
        if out:
            parts.append("Output:\n" + out)
        if parts:
            ET.SubElement(tc, "system-out").text = "\n\n".join(parts)
        if not r.passed:
            ET.SubElement(tc, "failure", message="Test failed").text = (
                r.stderr or r.stdout or ""
            ).strip()

    tree = ET.ElementTree(suite)
    ET.indent(tree, space="  ")
    path = os.path.join(output_dir, "junit.xml")
    tree.write(path, encoding="unicode", xml_declaration=True)
    print(f"[REPORT] junit  → {path}")


@REPORTERS.register("json")
def json_reporter(results, output_dir):
    """Machine-readable manifest for a results dashboard / CI. One entry per test,
    each carrying its status, timing, commands, and links to its detail artifacts
    (report.html / log.html / robot_output.xml). Paths are relative to the cwd."""
    entries = []
    for r in results:
        entries.append({
            "name": r.name,
            "type": r.type,
            "status": "passed" if r.passed else "failed",
            "duration": round(r.duration, 3),
            "commands": r.commands,
            "artifacts": {k: os.path.relpath(v) for k, v in r.artifacts.items()},
        })
    manifest = {
        "tests": len(results),
        "failures": sum(1 for r in results if not r.passed),
        "passed": all(r.passed for r in results),
        "results": entries,
    }
    path = os.path.join(output_dir, "manifest.json")
    with open(path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"[REPORT] json  → {path}")
