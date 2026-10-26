# SPDX-License-Identifier: AGPL-3.0-or-later
"""
The conductor: CLI parsing and the per-job pipeline that ties the modules together.

Phases per job:
  1   build module types (modules.py)  +  run the global build steps
  1.5 instantiate peripherals, resolve mappings + connections, finalize repl/commands
  2   generate one emulation resc; then simulate / debug / test
  3   sweep artifacts
"""

import copy
import os
import re
import shlex
import sys
from dataclasses import dataclass, field

from . import connections as conn
from . import core as _core
from . import mappings as maps
from . import peripherals as periph
from .core import (ARTIFACTS_DIR, DEFAULT_QUANTUM, SUPPORTED_SCHEMA_VERSIONS,
                   RuntimeOptions, as_lines, expand_matrix, interpolate, load_yaml,
                   resolve_arguments, to_container_path)
from .dependencies import framework_vars, prepare_dependencies
from .docker import build_renode_argv, run_renode
from . import generator as gen
from .generator import (collect_artifacts, finalize_commands, generate_emulation_resc,
                        snapshot_resc)
from .hubs import HUBS
from .modules import BuildContext, build_modules
from .reporters import emit
from .runners import RunnerContext, run_build_steps, run_tests
from .validator import print_issues, validate_config


# ---------------------------------------------------------------------------
# Shared engine
#
# The CLI surface (argparse subcommands) lives in hector.commands; each command
# is a small module that parses its own flags and then calls the helpers below to
# load the config, assemble a JobConfig, and run the matrix. Adding a command is
# adding one module — no changes here.
# ---------------------------------------------------------------------------

# The config file every command reads/writes. Overridable with -f/--file; set by
# apply_global_flags before any config is loaded.
CONFIG_PATH = ".hector.yaml"


def apply_global_flags(args):
    """Honour --file / --workspace-mount / --no-docker before anything touches paths.

    --no-docker can also be turned on with the HECTOR_NO_DOCKER env var, which is how
    the Renode-based Docker image runs hector in-process (renode is already present
    there, so there is nothing to launch in a sibling container)."""
    path = getattr(args, "file", None)
    if path:
        global CONFIG_PATH
        CONFIG_PATH = path
    if getattr(args, "workspace_mount", None):
        _core.WORKSPACE_MOUNT = args.workspace_mount
    if getattr(args, "no_docker", False) or os.environ.get("HECTOR_NO_DOCKER"):
        _core.NO_DOCKER = True
        _core.WORKSPACE_MOUNT = os.getcwd()


def resolve_config_path(path=None):
    """The config file to actually read, accepting either YAML extension.

    `.yaml` and `.yml` are interchangeable: if the requested name isn't there but its
    counterpart is, use that instead — so a project may keep `.hector.yml` and every
    command still finds it. Returns the requested path unchanged when neither exists,
    so callers report the error against the name the user asked for."""
    path = path or CONFIG_PATH
    if os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    counterpart = {".yaml": ".yml", ".yml": ".yaml"}.get(ext.lower())
    if counterpart and os.path.exists(base + counterpart):
        return base + counterpart
    return path


def load_config_or_exit():
    """Load and sanity-check the config file (CONFIG_PATH), or print an error and exit."""
    config_path = resolve_config_path()
    if not os.path.exists(config_path):
        print(f"[ERROR] No '{config_path}' in the current directory ({os.getcwd()}).\n"
              "        Run hector from a project that has a .hector.yaml (or "
              ".hector.yml), or create one with 'hector init'.", file=sys.stderr)
        sys.exit(1)
    try:
        config = load_yaml(config_path)
    except Exception as exc:
        print(f"[ERROR] Could not parse '{config_path}': {exc}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(config, dict):
        print(f"[ERROR] '{config_path}' must be a YAML mapping (got "
              f"{type(config).__name__}).", file=sys.stderr)
        sys.exit(1)
    v = config.get("version")
    if v is not None and str(v) not in SUPPORTED_SCHEMA_VERSIONS:
        print(f"[WARN] .hector.yaml 'version: {v}' is not in supported versions "
              f"({', '.join(sorted(SUPPORTED_SCHEMA_VERSIONS))}). Proceeding anyway.")
    return config


_VERSION_TAG_RE = re.compile(r"^v?\d+\.\d+\.\d+$")


def resolve_renode_image(config, args):
    """Pick the Renode Docker image and the git tag of the matching source; return
    (git_tag, docker_image).

    The image is either an explicit `renode_image` (any image, including a self-built
    one) or `antmicro/renode:<renode_version>`. CLI flags beat the config, and a flag
    of either kind replaces both config fields — so `--renode-version` still wins over
    a `renode_image:` in the file. The git tag (only used to clone the Renode source)
    comes from the version, or from the image tag when it looks like one; it is None
    when neither tells us, and only matters if the config needs the source."""
    flag_version = getattr(args, "renode_version", None)
    flag_image = getattr(args, "renode_image", None)
    if flag_version or flag_image:
        version, image = flag_version, flag_image
    else:
        version, image = config.get("renode_version"), config.get("renode_image")
    if not version and not image:
        raise ValueError("Top-level 'renode_version' (e.g. '1.16.1') or 'renode_image' "
                         "is required, or pass --renode-version / --renode-image on the "
                         "command line.")
    normalized = str(version).lstrip("v") if version else None
    image = str(image) if image else f"antmicro/renode:{normalized}"
    if not normalized:
        tag = image.rsplit("/", 1)[-1].partition(":")[2]
        normalized = tag.lstrip("v") if _VERSION_TAG_RE.match(tag) else None
    return (f"v{normalized}" if normalized else None), image


def _resolve_set_overrides(args):
    overrides = {}
    for kv in (getattr(args, "set_args", None) or []):
        if "=" not in kv:
            print(f"[ERROR] --set: '{kv}' is not KEY=VALUE", file=sys.stderr)
            sys.exit(1)
        k, _, v = kv.partition("=")
        overrides[k.strip()] = v
    return overrides


def _needs_renode_source(config):
    """The Renode source / verilator-integration checkouts are only needed to build
    `renode-verilator` modules (they compile against the Renode source) or to interpolate
    ${RENODE_DIR} / ${INTEGRATION_DIR}. The Renode binary itself comes from the Docker
    image, so plain machines, csharp modules (compiled by Renode / built against the
    image's assemblies), build/shell steps and firmware URLs need neither checkout."""
    for m in (config.get("modules") or {}).values():
        if (m.get("kind") or "renode-verilator") == "renode-verilator":
            return True
    blob = str(config)
    return "RENODE_DIR" in blob or "INTEGRATION_DIR" in blob


def build_job_config(action, config, args, *, test_mode=False):
    """Assemble a JobConfig from parsed args — the shared run / test / export path:
    pin the image, prepare the framework (lazily), resolve arguments + artifacts."""
    git_tag, docker_image = resolve_renode_image(config, args)

    # Clone Renode only when the config actually needs the source; otherwise skip it
    # entirely (a ~200 MB clone) and leave the framework vars empty.
    if _needs_renode_source(config):
        if not git_tag:
            raise ValueError(f"This config needs the Renode source, but the version of "
                             f"'{docker_image}' can't be inferred from its tag — also set "
                             "'renode_version' (or --renode-version) to pick the checkout.")
        renode_dir, integration_dir = prepare_dependencies(
            git_tag,
            renode_dir=getattr(args, "renode_dir", None),
            integration_dir=getattr(args, "renode_integration_dir", None),
        )
        fw_vars = framework_vars(renode_dir, integration_dir)
        fw_vars["_integration_dir_host"] = integration_dir
    else:
        fw_vars = {"RENODE_DIR": "", "INTEGRATION_DIR": "", "_integration_dir_host": ""}

    resolved_args = resolve_arguments(config.get("arguments", {}),
                                      overrides=_resolve_set_overrides(args))
    artifacts_cfg = (args.artifacts if getattr(args, "artifacts", None)
                     else as_lines(config.get("artifacts", [])))
    return JobConfig(
        config=config,
        fw_vars=fw_vars,
        resolved_args=resolved_args,
        docker_image=docker_image,
        action=action,
        test_mode=test_mode,
        debug_args=getattr(args, "debug", None) or [],
        test_file=getattr(args, "test_file", None),
        reporter_names=_resolve_reporters(getattr(args, "reporters", None)),
        renode_args=shlex.split(getattr(args, "renode_args", "") or ""),
        renode_test_args=shlex.split(getattr(args, "renode_test_args", "") or ""),
        test_name=getattr(args, "test_name", None),
        live=getattr(args, "live", False),
        fail_fast=getattr(args, "fail_fast", False),
        snapshot=getattr(args, "snapshot", None),
        no_start=getattr(args, "no_start", False),
        output_dir=getattr(args, "output", "results"),
        gather_metrics=getattr(args, "gather_execution_metrics", None),
        artifacts=artifacts_cfg,
    )


def execute_jobs(cfg, args):
    """Run exactly one matrix combination and return a process exit code.

    hector does NOT auto-expand the matrix — iterating combinations is the CI's job.
    A single invocation runs one combination: with no matrix there is one (empty) job;
    with a matrix, --job KEY=VALUE must pin it to exactly one combination."""
    jobs = expand_matrix(cfg.config.get("matrix"))
    if getattr(args, "job", None):
        jobs = filter_jobs(jobs, args.job)

    if len(jobs) != 1:
        listing = "\n  ".join(_job_label(j) for j in jobs)
        print(f"[ERROR] The matrix produces {len(jobs)} combinations; a run targets one. "
              "Select it with --job KEY=VALUE (e.g. --job BOARD=stm32f4).\n"
              f"  Combinations:\n  {listing}", file=sys.stderr)
        return 2

    result = run_job(0, 1, jobs[0], cfg)
    if cfg.test_mode:
        print_summary([result], cfg.test_mode)
    return 1 if not result["passed"] else 0


def snapshot_fastpath(args):
    """`run --snapshot --renode-version|--renode-image` with no .hector.yaml: write a
    snapshot loader resc and boot it directly, skipping config/dependency machinery."""
    if not os.path.isfile(args.snapshot):
        print(f"[ERROR] Snapshot not found: {args.snapshot}", file=sys.stderr)
        sys.exit(1)
    _, docker_image = resolve_renode_image({}, args)
    resc_root = os.path.join(ARTIFACTS_DIR, "resc")
    os.makedirs(resc_root, exist_ok=True)
    # No .hector.yaml here, so debug machine names come straight from --debug.
    debug_config = parse_debug_flag(getattr(args, "debug", None), {}, 1, validate_nodes=False)
    snap_resc = os.path.join(resc_root, "snapshot.resc")
    with open(snap_resc, "w") as f:
        f.write(snapshot_resc(to_container_path(args.snapshot), debug_config,
                              no_start=getattr(args, "no_start", False)))
    print(f"[SNAP] {args.snapshot}"
          + (f" (+GDB: {debug_config})" if debug_config else ""))
    run_renode(snap_resc, docker_image, ports=list(debug_config.values()) or None,
               extra_args=shlex.split(args.renode_args or ""), output_dir=args.output)


def _run_validate():
    """Load the config file (CONFIG_PATH) and report all config errors, then exit."""
    config_path = resolve_config_path()
    if not os.path.exists(config_path):
        print(f"[VALIDATE] {config_path} not found in current directory.")
        sys.exit(1)
    try:
        config = load_yaml(config_path)
    except Exception as exc:
        print(f"[VALIDATE] Could not parse {config_path}: {exc}")
        sys.exit(1)

    print(f"[VALIDATE] Checking {config_path} ...")
    errors, warnings = validate_config(config)
    has_errors = print_issues(errors, warnings)
    if has_errors:
        print(f"\n[VALIDATE] FAILED — {len(errors)} error(s), {len(warnings)} warning(s).")
        sys.exit(1)
    elif warnings:
        print(f"\n[VALIDATE] OK — 0 errors, {len(warnings)} warning(s).")
    else:
        print("[VALIDATE] OK")
    sys.exit(0)


# ---------------------------------------------------------------------------
# clean
# ---------------------------------------------------------------------------

# The Renode source / verilator-integration checkouts hector clones on demand. They
# live under .hector/ but are expensive to re-fetch (~200 MB), so `clean` keeps them
# unless --all is given.
_RENODE_CHECKOUTS = ("renode", "renode-verilator-integration")


def clean_targets(output_dir="results", include_renode=False):
    """The generated paths `hector clean` would remove, filtered to those that exist.

    Always: the cheap build artifacts (.hector/resc, .hector/repl, .hector/tests) and
    the results/output directory. Only with include_renode: the whole .hector/ (which
    also takes the expensive Renode checkouts with it). Paths are relative to the cwd."""
    if include_renode:
        targets = [ARTIFACTS_DIR, output_dir]
    else:
        targets = [os.path.join(ARTIFACTS_DIR, d) for d in ("resc", "repl", "tests")]
        targets.append(output_dir)
    # De-dupe while preserving order, keep only what's actually there.
    seen, existing = set(), []
    for p in targets:
        if p not in seen and os.path.exists(p):
            seen.add(p)
            existing.append(p)
    return existing


def _is_within_cwd(path):
    """True if `path` resolves inside the project root — the guard that stops `clean`
    from ever deleting something outside the workspace (e.g. an absolute --output)."""
    root = os.path.realpath(os.getcwd())
    real = os.path.realpath(path)
    return real == root or real.startswith(root + os.sep)


def run_clean(output_dir="results", include_renode=False, dry_run=False):
    """Remove hector's generated artifacts. Returns a process exit code."""
    import shutil

    targets = clean_targets(output_dir, include_renode)
    if not targets:
        print("[CLEAN] Nothing to remove — the workspace is already clean.")
        return 0

    removed = 0
    for path in targets:
        if not _is_within_cwd(path):
            print(f"[CLEAN] SKIP {path} — outside the project directory; refusing to remove it.")
            continue
        kind = "dir " if os.path.isdir(path) else "file"
        if dry_run:
            print(f"[CLEAN] would remove {kind} {path}")
            continue
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            os.remove(path)
        print(f"[CLEAN] removed {kind} {path}")
        removed += 1

    if dry_run:
        print("[CLEAN] dry run — nothing was deleted.")
    elif not include_renode and os.path.isdir(ARTIFACTS_DIR):
        # We kept a Renode checkout; tell the user how to drop it too.
        kept = [d for d in _RENODE_CHECKOUTS
                if os.path.isdir(os.path.join(ARTIFACTS_DIR, d))]
        if kept:
            print(f"[CLEAN] kept cached Renode checkout(s) in {ARTIFACTS_DIR}/ "
                  f"({', '.join(kept)}) — use 'hector clean --all' to remove them too.")
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_reporters(reporters):
    """Flatten the repeatable --reporters flag into an ordered, de-duplicated list.

    Defaults to ['junit'] when the flag is absent. Each value may still contain
    commas (e.g. --reporters junit,json) so older invocations keep working.
    """
    names = []
    for entry in (reporters or ["junit"]):
        for name in str(entry).split(","):
            name = name.strip()
            if name and name not in names:
                names.append(name)
    return names or ["junit"]


def build_hubs_registry(hubs_cfg):
    registry = {}
    for hub_name, hub_spec in (hubs_cfg or {}).items():
        hub_spec = hub_spec or {}
        htype = hub_spec.get("type")
        if not htype:
            raise ValueError(f"Hub '{hub_name}' is missing required 'type' "
                             f"({', '.join(sorted(HUBS.keys()))}).")
        if htype not in HUBS:
            raise ValueError(f"Hub '{hub_name}': unknown type '{htype}'. "
                             f"Available: {', '.join(sorted(HUBS.keys()))}.")
        registry[hub_name] = htype
    return registry


def parse_debug_flag(debug_args, concrete_nodes, job_index, validate_nodes=True):
    debug_config = {}
    for entry in (debug_args or []):
        if ":" not in entry:
            raise ValueError(f"--debug: '{entry}' is not NODE:PORT (e.g. boardA:3333).")
        node_name, _, port_str = entry.partition(":")
        if not port_str.isdigit():
            raise ValueError(f"--debug: port in '{entry}' must be a number.")
        # In the snapshot fast path there is no .hector.yaml to validate against; the
        # machine name is taken from the snapshot, so skip the membership check.
        if validate_nodes and node_name not in concrete_nodes:
            print(f"[WARN] --debug: '{node_name}' not in machines for job {job_index}, skipping.")
            continue
        debug_config[node_name] = int(port_str)
        print(f"[DEBUG] {node_name} -> GDB on port {port_str} (CPU will be halted)")
    return debug_config


def _job_label(job):
    """Human-readable matrix combination, e.g. 'BOARD=stm32f4 FW=debug.elf'."""
    return " ".join(f"{k}={v}" for k, v in job.items()) or "(no matrix variables)"


def filter_jobs(jobs, spec):
    """Filter the expanded jobs by --job SPEC: KEY=VALUE[,KEY=VALUE,...], matched against
    the matrix variable values. Values compare as strings, so --job RATE=2 matches a
    numeric 2 in the matrix."""
    filters = {}
    for part in spec.split(","):
        part = part.strip()
        if "=" not in part:
            raise ValueError(f"--job: '{part}' is not KEY=VALUE.")
        k, v = part.split("=", 1)
        filters[k.strip()] = v.strip()

    filtered = [j for j in jobs
                if all(str(j.get(k)) == v for k, v in filters.items())]
    if not filtered:
        available = "\n  ".join(_job_label(j) for j in jobs) if jobs else "(none)"
        raise ValueError(
            f"--job: no matrix combination matches {filters}.\n"
            f"  Combinations:\n  {available}")
    return filtered


def _apply_metrics(concrete_nodes, gather_metrics, output_dir, job_index):
    """Inject cpu EnableProfiler commands into node configs for requested machines."""
    all_machines = None in gather_metrics
    target_nodes = (list(concrete_nodes.keys()) if all_machines
                    else [n for n in gather_metrics if n is not None])
    for node_name in target_nodes:
        if node_name not in concrete_nodes:
            print(f"[WARN] --gather-execution-metrics: '{node_name}' not in "
                  f"nodes for job {job_index}, skipping.")
            continue
        node_config = concrete_nodes[node_name]
        metrics_file = os.path.join(output_dir, f"metrics_{node_name}_job_{job_index}.bin")
        os.makedirs(output_dir, exist_ok=True)
        cmd = f"cpu EnableProfiler @{to_container_path(metrics_file)}"
        existing = node_config.get("commands", "")
        if existing:
            if isinstance(existing, list):
                existing = "\n".join(str(c) for c in existing)
            node_config["commands"] = existing.strip() + f"\n{cmd}"
        else:
            node_config["commands"] = cmd
        print(f"[METRICS] {node_name} -> {metrics_file}")


# ---------------------------------------------------------------------------
# Per-job pipeline
# ---------------------------------------------------------------------------

@dataclass
class JobConfig:
    config: dict
    fw_vars: dict
    resolved_args: dict
    docker_image: str
    # PHASE-2 behaviour for this command (simulate / test / export). run_job builds
    # every job up to a generated resc, then hands a JobState to this callable.
    action: object
    debug_args: list = field(default_factory=list)
    # Only the test command lays out results test-by-test; drives the summary format.
    test_mode: bool = False
    test_file: str = None
    reporter_names: list = field(default_factory=lambda: ["junit"])
    renode_args: list = field(default_factory=list)
    renode_test_args: list = field(default_factory=list)
    test_name: list = None
    live: bool = False
    fail_fast: bool = False
    snapshot: str = None
    no_start: bool = False
    output_dir: str = "results"
    gather_metrics: list = None
    artifacts: list = field(default_factory=list)


@dataclass
class JobState:
    """Everything a command's PHASE-2 action needs once a job has been assembled
    into a generated emulation resc."""
    resc_filename: str
    runtime: RuntimeOptions
    debug_config: dict
    tests: list
    concrete_nodes: dict


# ---------------------------------------------------------------------------
# PHASE-2 actions  (one per command; selected via JobConfig.action)
# ---------------------------------------------------------------------------

def _resolve_active_resc(state, cfg):
    """The resc a simulation/export should boot: the generated one, or a snapshot
    loader written on the fly when --snapshot is given."""
    if not cfg.snapshot:
        return state.resc_filename
    if not os.path.isfile(cfg.snapshot):
        raise FileNotFoundError(f"Snapshot not found: {cfg.snapshot}")
    snap_resc = state.resc_filename.replace(".resc", "_snapshot.resc")
    with open(snap_resc, "w") as f:
        f.write(snapshot_resc(to_container_path(cfg.snapshot), state.debug_config,
                              no_start=cfg.no_start))
    print(f"[SNAP] {cfg.snapshot}"
          + (f" (+GDB: {state.debug_config})" if state.debug_config else ""))
    return snap_resc


def action_simulate(state, cfg, result):
    """`run`: boot the emulation interactively in Renode."""
    if not state.resc_filename:
        raise ValueError("`hector run` needs at least one machine in 'machines:'.")
    run_renode(_resolve_active_resc(state, cfg), cfg.docker_image,
               ports=list(state.debug_config.values()) or None,
               extra_args=cfg.renode_args, output_dir=cfg.output_dir,
               runtime=state.runtime)


def action_export(state, cfg, result):
    """`export`: generate the files, then print the command that would run instead
    of running it (a `docker run ... renode ...`, or a bare `renode ...` under
    --no-docker)."""
    if not state.resc_filename:
        raise ValueError("`hector export` needs at least one machine in 'machines:'.")
    argv = build_renode_argv(_resolve_active_resc(state, cfg), cfg.docker_image,
                             ports=list(state.debug_config.values()) or None,
                             extra_args=cfg.renode_args, runtime=state.runtime)
    line = shlex.join(argv)
    print(line)
    result.setdefault("exported", []).append(line)


def action_test(state, cfg, result):
    """`test`: run the resolved `tests:` section and record pass/fail."""
    effective_tests = state.tests
    if cfg.test_file:
        effective_tests = [{"name": os.path.basename(cfg.test_file),
                            "type": "robot", "file": cfg.test_file}]
    if cfg.test_name:
        effective_tests = [t for t in effective_tests
                           if any(n in t.get("name", "") for n in cfg.test_name)]
        if not effective_tests:
            print(f"[TEST] No tests matching {cfg.test_name}.")
    if not effective_tests:
        print("[TEST] No tests defined in 'tests:'; nothing to run.")
        return
    ctx = RunnerContext(
        resc_host_path=state.resc_filename,
        job_index=result["job_index"],
        image=cfg.docker_image,
        reporters=cfg.reporter_names,
        renode_test_args=cfg.renode_test_args,
        live=cfg.live,
        snapshot=cfg.snapshot or "",
        results_dir=cfg.output_dir,
        runtime=state.runtime,
    )
    # run_job combines these with the build results and emits the reports once.
    result["test_results"] = run_tests(effective_tests, ctx, fail_fast=cfg.fail_fast)


def run_job(i, total_jobs, job_context, cfg):
    """Execute one matrix job. Returns a result dict."""
    label = "  ".join(f"{k}={v}" for k, v in job_context.items()) if job_context else "(no matrix variables)"
    if total_jobs > 1:
        print(f"\n[JOB {i+1}/{total_jobs}]  {label}")

    context = {**cfg.fw_vars, **cfg.resolved_args, **job_context}
    modules_cfg     = interpolate(copy.deepcopy(cfg.config.get("modules",      {})), context)
    concrete_nodes  = interpolate(copy.deepcopy(cfg.config.get("machines",     {})), context)
    hubs_cfg        = interpolate(copy.deepcopy(cfg.config.get("hubs",         {})), context)
    top_connections = as_lines(interpolate(copy.deepcopy(cfg.config.get("connections", "")), context))
    mappings        = as_lines(interpolate(copy.deepcopy(cfg.config.get("mappings",    "")), context))
    tests           = interpolate(copy.deepcopy(cfg.config.get("tests",        [])), context)

    hubs_registry = build_hubs_registry(hubs_cfg)
    result = {"job_index": i + 1, "label": label, "passed": True, "test_results": None, "error": None}

    # Execution-environment needs (docker caps/devices/root) declared by components
    # (mappings, hubs, modules) during parsing; mapped to run flags at execution.
    runtime = RuntimeOptions()

    try:
        # ---- PHASE 1: build modules, run the global build steps ----
        build_ctx = BuildContext(
            renode_dir_container=cfg.fw_vars["RENODE_DIR"],
            integration_dir_host=context.get("_integration_dir_host", ""),
            image=cfg.docker_image,
        )
        modules_registry = build_modules(modules_cfg, build_ctx)
        for mod in modules_registry.values():
            runtime.merge(mod.get("runtime"))

        # Global build steps (compile firmware, fetch/generate files, ...) — run once per
        # job, in containers, before the machines are built. Outputs land in the mounted
        # project so the sim/tests pick them up. They report like tests (one StepResult
        # each) and abort the job on the first failure. cfg.docker_image is the default.
        build_blocks = interpolate(copy.deepcopy(cfg.config.get("build", [])), context)
        build_results = run_build_steps(build_blocks, cfg.docker_image, cfg.output_dir,
                                        live=cfg.live)
        build_ok = all(r.passed for r in build_results)

        for node_name, node_config in concrete_nodes.items():
            if node_config.get("backend", "renode") != "renode":
                raise ValueError(
                    f"Node '{node_name}': unknown backend '{node_config.get('backend')}'. "
                    "Only 'renode' is supported."
                )

        # ---- PHASE 1.5: collect ----
        # Pre-pass: classify ALL connections as intra-machine or hub connections.
        # Intra-machine lines (neither side is a hub) are injected directly into
        # each node's _repl_signals so the generator sees them inline on the peripheral
        # definition — no separate merge step needed.
        # Hub connections are collected for resolve_connections (cross-machine wiring).
        known_nodes = set(concrete_nodes)
        hub_connections = []

        for node_name, _nc in concrete_nodes.items():
            intra, hub = [], []
            for line in as_lines(_nc.get("connections", "")):
                (hub if conn.is_hub_line(line, hubs_registry) else intra).append(line)
            if intra:
                existing = _nc.get("_repl_signals", "")
                _nc["_repl_signals"] = ("\n".join([existing] + intra) if existing
                                        else "\n".join(intra))
            hub_connections.extend(
                conn.qualify_node_connection(l, node_name, hubs_registry, known_nodes)
                for l in hub)

        # Top-level connections: hub lines go to resolve_connections; intra-machine
        # top-level lines are stripped of their 'node.' prefix and injected into the
        # owning node's _repl_signals.
        for line in top_connections:
            if conn.is_hub_line(line, hubs_registry):
                hub_connections.append(line)
            else:
                if "->" not in line:
                    raise ValueError(
                        f"Top-level non-hub connection '{line}' must use '->'.")
                src_tok = line.split("->", 1)[0].strip()
                node = src_tok.split(".")[0] if "." in src_tok else None
                if node not in concrete_nodes:
                    raise ValueError(
                        f"Top-level connection '{line}': cross-machine links require "
                        "a hub declared under 'hubs:'.")
                pfx = node + "."
                a, b = (t.strip() for t in line.split("->", 1))
                stripped = (f"{a[len(pfx):]if a.startswith(pfx)else a} -> "
                            f"{b[len(pfx):]if b.startswith(pfx)else b}")
                _nc = concrete_nodes[node]
                existing = _nc.get("_repl_signals", "")
                _nc["_repl_signals"] = (f"{existing}\n{stripped}" if existing else stripped)

        # Build NodeDescriptors: _repl_signals is now fully populated before this call.
        descriptors = periph.resolve_peripherals(concrete_nodes, modules_registry)

        # C# DLL imports must precede any `mach create` in the resc.
        seen_dlls = set()
        for desc in descriptors.values():
            seen_dlls.update(desc.csharp_dlls)
        emulation_setup = [f"i @{to_container_path(dll)}" for dll in seen_dlls]

        # so_commands go into _gen_commands before mappings to preserve [so, map, user] order.
        for node_name, descriptor in descriptors.items():
            for cmd in descriptor.so_commands:
                concrete_nodes[node_name].setdefault("_gen_commands", []).append(cmd)

        if mappings:
            map_lines, map_runtime = maps.resolve_mappings(mappings, concrete_nodes)
            emulation_setup += map_lines
            runtime.merge(map_runtime)

        cross_connections = (
            conn.resolve_connections(hub_connections, concrete_nodes, hubs_registry)
            if hub_connections else []
        )
        for spec in cross_connections:
            runtime.merge(HUBS.get(hubs_registry[spec["hub"]]).runtime_options(spec))

        # ---- PHASE 1.75: generate ----
        # Inline `repl:` text becomes a real .repl on disk (Renode only loads platform
        # descriptions from files). It lands after the user's own `platform:` files so it
        # can extend them, and before the generated peripherals repl below.
        for node_name, node_config in concrete_nodes.items():
            inline_repl = node_config.get("repl")
            if inline_repl:
                node_config.setdefault("platform", []).append(
                    to_container_path(gen.write_inline_repl(node_name, inline_repl, i + 1)))

        # Write one .repl per node, then append its path to node_config["platform"].
        for node_name, descriptor in descriptors.items():
            repl_path = gen.generate_node_repl(descriptor, i + 1)
            if repl_path:
                concrete_nodes[node_name].setdefault("platform", []).append(
                    to_container_path(repl_path))

        finalize_commands(concrete_nodes)

        quantum_cfg = cfg.config.get("quantum")
        if quantum_cfg is not None:
            quantum_value = str(quantum_cfg)
        elif hubs_registry:
            quantum_value = DEFAULT_QUANTUM
            print(f"[QUANTUM] hub(s) present -> SetGlobalQuantum {quantum_value}s "
                  "(default; set top-level 'quantum:' to override)")
        else:
            quantum_value = None

        debug_config = parse_debug_flag(cfg.debug_args, concrete_nodes, i + 1)
        if cfg.gather_metrics is not None:
            _apply_metrics(concrete_nodes, cfg.gather_metrics, cfg.output_dir, i + 1)

        # ---- PHASE 2: generate resc (if any machines); simulate / test ----
        # A resc is only produced when machines are defined. The action still runs
        # without one: `run`/`export` error (they need a machine), while `test` runs
        # any sim-independent tests (requires_sim: false) and skips the rest.
        resc_filename = None
        if concrete_nodes:
            resc_root = os.path.join(ARTIFACTS_DIR, "resc")
            os.makedirs(resc_root, exist_ok=True)
            resc_filename = os.path.join(resc_root, f"job_{i+1}.resc")
            generate_emulation_resc(
                list(concrete_nodes.items()), hubs_registry, cross_connections,
                quantum_value, debug_config, resc_filename,
                emulation_setup=emulation_setup, no_start=cfg.no_start,
            )

        # A failed build aborts before the sim/tests — but its results are still
        # reported, so the failure shows up in junit/manifest/html like a test.
        if build_ok:
            state = JobState(resc_filename=resc_filename, runtime=runtime,
                             debug_config=debug_config, tests=tests,
                             concrete_nodes=concrete_nodes)
            cfg.action(state, cfg, result)
        else:
            print("\n[BUILD] a build step failed — skipping simulation/tests.")

        # ---- PHASE 2.5: report (build steps + tests, together) ----
        step_results = list(build_results) + (result.get("test_results") or [])
        result["test_results"] = step_results
        if step_results:
            emit(step_results, cfg.output_dir, cfg.reporter_names)
            result["passed"] = result["passed"] and all(r.passed for r in step_results)

        # ---- PHASE 3: sweep artifacts ----
        # Global glob patterns (top-level 'artifacts:' or --artifacts), interpolated
        # with this job's context so matrix variables resolve.
        artifact_patterns = as_lines(interpolate(list(cfg.artifacts), context))
        collect_artifacts(artifact_patterns, cfg.output_dir, i + 1)

    except Exception as exc:
        result["passed"] = False
        result["error"] = str(exc)
        print(f"\n[ERROR] Job {i+1} failed: {exc}")

    return result


# ---------------------------------------------------------------------------
# Aggregate results table
# ---------------------------------------------------------------------------

def print_summary(all_results, test_mode):
    n_jobs = len(all_results)
    W = 62

    # Single job in test mode: show test-level results directly — no confusing
    # job-vs-test count mismatch.
    if n_jobs == 1 and test_mode:
        r = all_results[0]
        t = r["test_results"] or []
        n_t = len(t)
        n_tp = sum(1 for s in t if s.passed)
        print(f"\n{'═'*W}")
        if r["error"]:
            print(f"FAILED   ERROR: {r['error']}")
        else:
            print(f"RESULTS   {n_tp}/{n_t} tests passed")
        print(f"{'─'*W}")
        for s in t:
            mark = "✓" if s.passed else "✗"
            print(f"  {mark}  [{s.type}] {s.name}")
        print(f"{'═'*W}")
        return

    # Matrix / multi-job: job-level header + per-job test breakdown.
    n_pass = sum(1 for r in all_results if r["passed"])
    print(f"\n{'═'*W}")
    print(f"JOB SUMMARY   {n_pass}/{n_jobs} jobs passed")
    print(f"{'─'*W}")
    for r in all_results:
        mark = "✓" if r["passed"] else "✗"
        label = r["label"] or f"job {r['job_index']}"
        if r["error"]:
            detail = f"  ERROR: {r['error']}"
        elif test_mode and r["test_results"] is not None:
            t = r["test_results"]
            n_tp = sum(1 for s in t if s.passed)
            failed = [s.name for s in t if not s.passed]
            detail = f"  {n_tp}/{len(t)} tests"
            if failed:
                detail += "  ← " + ", ".join(failed)
        else:
            detail = ""
        print(f"  {mark}  JOB {r['job_index']}  {label}{detail}")
    print(f"{'═'*W}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)

    # Subcommands are discovered from the COMMANDS registry; each parses its own
    # flags and runs via the shared engine above.
    from .commands import build_parser

    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args._command.execute(args) or 0)
