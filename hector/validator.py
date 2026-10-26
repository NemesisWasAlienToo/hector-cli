# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Config validation. Collects all errors in one pass so the user sees everything at once
rather than fixing one typo at a time.

Usage:
    from .validator import validate_config
    errors, warnings = validate_config(raw_yaml_dict)
    for e in errors:   print(f"  ERROR   {e.path}: {e.message}")
    for w in warnings: print(f"  WARNING {w.path}: {w.message}")
"""

from dataclasses import dataclass
from typing import List, Tuple

from .core import SUPPORTED_SCHEMA_VERSIONS, as_lines
from .hubs import HUBS
from .mappings import MAPPING_BACKENDS
from .modules import MODULE_KINDS
from .runners import TEST_RUNNERS

# CI trigger / run-control keys. The whole .hector.yaml is a single pipeline (there is
# no nested `ci:` block). These belong entirely to the CI server — the CLI's run/test/
# export never read them and it must not act on them. They are listed here only so the
# CLI accepts them silently instead of flagging them; the CI backend is their sole
# validator (see ci/backend/hectorci/config.py).
_TRIGGER_TOP_KEYS = {"when", "cron", "reporters", "jobs", "fail_fast", "timeout"}

# Top-level keys defined by this schema version; anything else is flagged.
_KNOWN_TOP_KEYS = {
    "version", "renode_version", "renode_image", "arguments", "matrix",
    "modules", "hubs", "machines", "connections", "mappings", "build", "tests", "quantum",
    "artifacts",
} | _TRIGGER_TOP_KEYS

# Keys renamed in this schema version → new name (for a helpful migration hint).
_RENAMED_TOP_KEYS = {"nodes": "machines", "setup": "build", "prepare": "build"}

# Test types renamed this schema version → current name (old configs still run).
_RENAMED_TEST_TYPES = {"bash": "shell", "docker": "shell"}

_KNOWN_NODE_KEYS = {
    "backend", "platform", "repl", "resc", "firmware",
    "peripherals", "init", "connections", "mappings", "commands",
    # deprecated at machine level (now global); kept here to emit a targeted warning
    # instead of a generic "unknown key" one.
    "artifacts", "prepare", "build",
}

_KNOWN_MODULE_KEYS = {"kind", "type", "source", "cmake_flags"}


@dataclass
class Issue:
    path: str
    message: str


def validate_config(config) -> Tuple[List[Issue], List[Issue]]:
    """Return (errors, warnings).  errors are blockers; warnings are advisory."""
    if not isinstance(config, dict):
        return [Issue("(root)", "Config must be a YAML mapping, got "
                      f"{type(config).__name__}.")], []

    errors: List[Issue] = []
    warnings: List[Issue] = []

    def err(path, msg):
        errors.append(Issue(path, msg))

    def warn(path, msg):
        warnings.append(Issue(path, msg))

    # ---- version ----
    schema_ver = config.get("version")
    if schema_ver is not None:
        sv = str(schema_ver)
        if sv not in SUPPORTED_SCHEMA_VERSIONS:
            warn("version", f"'{sv}' is not in supported schema versions "
                 f"({', '.join(sorted(SUPPORTED_SCHEMA_VERSIONS))}). "
                 "Some fields may not be recognised.")

    # ---- renode_version / renode_image (one of them required) ----
    rv = config.get("renode_version")
    ri = config.get("renode_image")
    if not rv and not ri:
        err("renode_version", "Required field missing (e.g. '1.16.1') — or set "
            "'renode_image' to use a specific Docker image.")
    if rv and not isinstance(rv, (str, int, float)):
        err("renode_version", f"Must be a string like '1.16.1', got {type(rv).__name__}.")
    if ri and not isinstance(ri, str):
        err("renode_image", f"Must be a string like 'my-renode:dev', got {type(ri).__name__}.")

    # ---- unknown / renamed top-level keys ----
    for k in config:
        if k in _RENAMED_TOP_KEYS:
            warn(k, f"'{k}:' was renamed to '{_RENAMED_TOP_KEYS[k]}:' — rename the "
                 "top-level key. This entry is ignored.")
        elif k not in _KNOWN_TOP_KEYS:
            warn(k, f"Unknown top-level key '{k}' — check for a typo. "
                 f"Known keys: {', '.join(sorted(_KNOWN_TOP_KEYS))}.")

    # ---- arguments ----
    args_cfg = config.get("arguments")
    if args_cfg is not None:
        if not isinstance(args_cfg, dict):
            err("arguments", f"Must be a mapping of name: default, got {type(args_cfg).__name__}.")
        else:
            for k, v in args_cfg.items():
                if not isinstance(v, (str, int, float, bool)):
                    err(f"arguments.{k}", f"Argument default must be a scalar, got {type(v).__name__}.")

    # ---- matrix ----
    matrix_cfg = config.get("matrix")
    if matrix_cfg is not None:
        if not isinstance(matrix_cfg, dict):
            err("matrix", f"Must be a mapping, got {type(matrix_cfg).__name__}.")
        else:
            variables = matrix_cfg.get("variables")
            if variables is None:
                err("matrix", "Missing 'variables' sub-key.")
            elif not isinstance(variables, dict):
                err("matrix.variables", f"Must be a mapping of name: [values], got {type(variables).__name__}.")
            else:
                for k, v in variables.items():
                    if not isinstance(v, list) or not v:
                        err(f"matrix.variables.{k}", "Must be a non-empty list of values.")
            excludes = matrix_cfg.get("exclude", [])
            if not isinstance(excludes, list):
                err("matrix.exclude", f"Must be a list of dicts, got {type(excludes).__name__}.")

    # ---- modules ----
    modules_cfg = config.get("modules") or {}
    if not isinstance(modules_cfg, dict):
        err("modules", f"Must be a mapping, got {type(modules_cfg).__name__}.")
        modules_cfg = {}
    for mod_name, mod_spec in modules_cfg.items():
        p = f"modules.{mod_name}"
        if not isinstance(mod_spec, dict):
            err(p, f"Must be a mapping, got {type(mod_spec).__name__}."); continue
        kind = mod_spec.get("kind", "renode-verilator")
        if kind not in MODULE_KINDS:
            err(f"{p}.kind", f"Unknown module kind '{kind}'. "
                f"Available: {', '.join(sorted(MODULE_KINDS.keys()))}.")
        if not mod_spec.get("type"):
            err(f"{p}.type", "Required: the Renode class this module exposes "
                "(e.g. 'CoSimulated.CoSimulatedUART').")
        if kind != "csharp" and not mod_spec.get("source"):
            err(f"{p}.source", f"Required for kind '{kind}': path to the CMake/C# project.")
        elif kind == "csharp" and not mod_spec.get("source"):
            err(f"{p}.source", "Required: path to a .csproj directory or a pre-built .dll.")
        for k in mod_spec:
            if k not in _KNOWN_MODULE_KEYS:
                warn(f"{p}.{k}", f"Unknown module key '{k}'.")

    # ---- hubs ----
    hubs_cfg = config.get("hubs") or {}
    if not isinstance(hubs_cfg, dict):
        err("hubs", f"Must be a mapping, got {type(hubs_cfg).__name__}.")
        hubs_cfg = {}
    for hub_name, hub_spec in hubs_cfg.items():
        p = f"hubs.{hub_name}"
        hub_spec = hub_spec or {}
        if not isinstance(hub_spec, dict):
            err(p, f"Must be a mapping, got {type(hub_spec).__name__}."); continue
        htype = hub_spec.get("type")
        if not htype:
            err(f"{p}.type", f"Required. Available types: {', '.join(sorted(HUBS.keys()))}.")
        elif htype not in HUBS:
            err(f"{p}.type", f"Unknown hub type '{htype}'. "
                f"Available: {', '.join(sorted(HUBS.keys()))}.")

    # ---- machines (optional: a config may be build-only or run sim-independent
    #      shell tests; `run`/`export` and sim-backed tests check for one at runtime) ----
    nodes_cfg = config.get("machines")
    if nodes_cfg is None:
        nodes_cfg = {}
    elif not isinstance(nodes_cfg, dict):
        err("machines", f"Must be a mapping, got {type(nodes_cfg).__name__}.")
        nodes_cfg = {}
    for node_name, node_spec in nodes_cfg.items():
        p = f"machines.{node_name}"
        if not isinstance(node_spec, dict):
            err(p, f"Must be a mapping, got {type(node_spec).__name__}."); continue
        backend = node_spec.get("backend", "renode")
        if backend != "renode":
            err(f"{p}.backend", f"Unknown backend '{backend}'. Only 'renode' is supported.")
        hw = node_spec.get("platform")
        if hw is not None and not isinstance(hw, list):
            err(f"{p}.platform", f"Must be a list of .repl paths, got {type(hw).__name__}.")
        # Inline platform/script text lifted straight out of an upstream .repl/.resc
        # (e.g. a board that only exists on Renode's master branch, not in the release).
        for key, what in (("repl", ".repl platform description"),
                          ("resc", ".resc monitor script")):
            val = node_spec.get(key)
            if val is not None and not isinstance(val, (str, list)):
                err(f"{p}.{key}", f"Must be inline {what} text (a block scalar) or a "
                                  f"list of lines, got {type(val).__name__}.")
        fw = node_spec.get("firmware")
        if fw is not None and not isinstance(fw, str):
            err(f"{p}.firmware", f"Must be a string path or URL, got {type(fw).__name__}.")
        for k in node_spec:
            if k not in _KNOWN_NODE_KEYS:
                warn(f"{p}.{k}", f"Unknown machine key '{k}'.")
        # peripherals
        perifs = node_spec.get("peripherals") or {}
        if not isinstance(perifs, dict):
            err(f"{p}.peripherals", f"Must be a mapping, got {type(perifs).__name__}.")
        else:
            for inst_name, inst_spec in perifs.items():
                inst_spec = inst_spec or {}
                pp = f"{p}.peripherals.{inst_name}"
                if not isinstance(inst_spec, dict):
                    err(pp, f"Must be a mapping, got {type(inst_spec).__name__}."); continue
                if not inst_spec.get("type"):
                    err(f"{pp}.type", "Required: either a module name or a Renode class "
                        "(e.g. 'Miscellaneous.Button').")
        # artifacts is a top-level (global) key; per-machine entries are ignored.
        if node_spec.get("artifacts") is not None:
            warn(f"{p}.artifacts", "Machine-level 'artifacts:' is not supported; "
                 "move it to the top-level 'artifacts:' section. This entry is ignored.")
        # build is a top-level (global) key; per-machine entries are ignored.
        if node_spec.get("prepare") is not None or node_spec.get("build") is not None:
            key = "build" if node_spec.get("build") is not None else "prepare"
            warn(f"{p}.{key}", "Machine-level build/prepare is not supported; "
                 "move it to the top-level 'build:' section. This entry is ignored.")

    # ---- connections / mappings: parse each line for obvious errors ----
    _validate_connection_lines(config.get("connections", ""), "connections", err, warn)
    for node_name, node_spec in nodes_cfg.items():
        if isinstance(node_spec, dict):
            _validate_connection_lines(
                node_spec.get("connections", ""), f"machines.{node_name}.connections", err, warn)
    _validate_mapping_lines(config.get("mappings", ""), "mappings", nodes_cfg, err)
    for node_name, node_spec in nodes_cfg.items():
        if isinstance(node_spec, dict):
            _validate_mapping_lines(
                node_spec.get("mappings", ""), f"machines.{node_name}.mappings", nodes_cfg, err)

    # ---- artifacts (top-level, global) ----
    artifacts_cfg = config.get("artifacts")
    if artifacts_cfg is not None and not isinstance(artifacts_cfg, (list, str)):
        err("artifacts", "Must be a list of glob patterns or a block string, got "
            f"{type(artifacts_cfg).__name__}.")

    # ---- build (top-level, global): pre-sim shell steps, same shape as shell tests ----
    build_cfg = config.get("build")
    if build_cfg is not None:
        if not isinstance(build_cfg, list):
            err("build", "Must be a list of build steps "
                f"(each a mapping with image:/script:/steps:), got {type(build_cfg).__name__}.")
        else:
            for idx, block in enumerate(build_cfg):
                bp = f"build[{idx}]"
                if not isinstance(block, dict):
                    err(bp, f"Each build step must be a mapping, got {type(block).__name__}.")
                    continue
                if block.get("image") is not None and not isinstance(block.get("image"), str):
                    err(f"{bp}.image", "If set, 'image' must be a string (e.g. 'arm-gcc:13').")
                _validate_shell_steps(block, bp, err, warn)

    # ---- tests ----
    tests_cfg = config.get("tests") or []
    if not isinstance(tests_cfg, list):
        err("tests", f"Must be a list of test dicts, got {type(tests_cfg).__name__}.")
    else:
        for idx, test in enumerate(tests_cfg):
            p = f"tests[{idx}]"
            if not isinstance(test, dict):
                err(p, f"Each test must be a mapping, got {type(test).__name__}."); continue
            if not test.get("name"):
                warn(p, "Test has no 'name' — consider adding one for readable output.")
            rtype = test.get("type", "robot")
            if rtype in _RENAMED_TEST_TYPES:
                warn(f"{p}.type", f"Test type '{rtype}' was renamed to "
                     f"'{_RENAMED_TEST_TYPES[rtype]}' — update 'type:'.")
                rtype = _RENAMED_TEST_TYPES[rtype]
            if rtype not in TEST_RUNNERS:
                err(f"{p}.type", f"Unknown test type '{rtype}'. "
                    f"Available: {', '.join(sorted(TEST_RUNNERS.keys()))}.")
            if "requires_sim" in test and not isinstance(test["requires_sim"], bool):
                err(f"{p}.requires_sim", "Must be true or false.")
            if rtype == "robot" and test.get("requires_sim") is False:
                warn(f"{p}.requires_sim", "robot tests always need the simulation; "
                     "'requires_sim: false' is ignored.")
            _validate_shell_steps(test, p, err, warn)

    # ---- quantum ----
    quantum = config.get("quantum")
    if quantum is not None:
        try:
            q = float(quantum)
            if q <= 0:
                err("quantum", f"Must be a positive number, got {quantum}.")
        except (TypeError, ValueError):
            err("quantum", f"Must be a positive number (seconds), got '{quantum}'.")

    # ---- CI triggers (when/cron/…) are accepted but never validated or acted on
    #      here; they belong to the CI server. See _TRIGGER_TOP_KEYS. ----

    return errors, warnings


# ---- helpers ----

def _validate_shell_steps(item, p, err, warn):
    """Validate the step structure shared by tests and build blocks: either a `steps:`
    list, or a single-step `script:`/`file:` shorthand at the item level."""
    if "steps" in item:
        steps = item["steps"]
        if not isinstance(steps, list):
            err(f"{p}.steps", f"Must be a list, got {type(steps).__name__}.")
        elif not steps:
            warn(p, "Empty 'steps' list — it will do nothing.")
        else:
            for sidx, step in enumerate(steps):
                sp = f"{p}.steps[{sidx}]"
                if not isinstance(step, dict):
                    err(sp, f"Each step must be a mapping, got {type(step).__name__}.")
                    continue
                if not step.get("name"):
                    warn(sp, "Step has no 'name' — consider adding one.")
                if not step.get("script") and not step.get("file"):
                    warn(sp, "Step has no 'script' or 'file' — it will do nothing.")
                if step.get("file") and step.get("script"):
                    warn(sp, "Step has both 'file' and 'script' — 'file' takes precedence.")
    else:
        # Backward compat: script/file at the item level (single-step shorthand).
        if not item.get("script") and not item.get("file"):
            warn(p, "No 'steps', 'script', or 'file' — it will do nothing.")
        if item.get("file") and item.get("script"):
            warn(p, "Both 'file' and 'script' — 'file' takes precedence.")


def _validate_connection_lines(section, path, err, warn):
    for line in as_lines(section):
        if "->" not in line and "<->" not in line:
            err(path, f"Line '{line}' has no '->' or '<->' operator.")


def _validate_mapping_lines(section, path, nodes_cfg, err):
    for line in as_lines(section):
        if "->" not in line:
            err(path, f"Mapping '{line}' has no '->' operator.")
            continue
        _, rhs = line.split("->", 1)
        backend = rhs.strip().split(":", 1)[0].strip()
        if backend not in MAPPING_BACKENDS:
            err(path, f"Mapping '{line}': unknown backend '{backend}'. "
                f"Available: {', '.join(sorted(MAPPING_BACKENDS.keys()))}.")


def print_issues(errors, warnings):
    """Pretty-print validation results. Returns True if there are errors."""
    if warnings:
        for w in warnings:
            print(f"  WARN   {w.path}: {w.message}")
    if errors:
        for e in errors:
            print(f"  ERROR  {e.path}: {e.message}")
    return bool(errors)
