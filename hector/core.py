# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Core plumbing: the extension Registry, shared constants, host<->container path
translation, YAML/interpolation/matrix helpers, repl emitters, and the endpoint parser.

You rarely need to touch this file. The interesting, extensible parts live in:
  hubs.py       - add a cross-machine connection medium (uart, can, gpio, ...)
  runners.py    - add a test runner (bash, robot, renode-test, ...)
  mappings.py   - add a peripheral->host backend (file, ...)
  modules.py    - add a module build kind (renode-verilator, ...)
"""

import itertools
import os
import posixpath
import re
import subprocess
from dataclasses import dataclass, field

import yaml


# ==========================================================================
# REGISTRY  (the extension mechanism used across the codebase)
# ==========================================================================
class Registry:
    """A named lookup table you extend with a decorator.

        WIDGETS = Registry("widget")

        @WIDGETS.register("foo")
        class Foo: ...

        WIDGETS.get("foo")          # -> Foo
        "foo" in WIDGETS            # -> True
        list(WIDGETS.keys())        # -> ["foo", ...]

    Unknown keys raise a helpful error listing what *is* available, so a typo in
    the YAML produces a clear message instead of a KeyError.
    """
    def __init__(self, name):
        self.name = name
        self._items = {}

    def register(self, key):
        def deco(obj):
            if key in self._items:
                raise ValueError(f"{self.name} '{key}' is already registered.")
            self._items[key] = obj
            return obj
        return deco

    def get(self, key):
        if key not in self._items:
            raise KeyError(
                f"Unknown {self.name} '{key}'. Available: {', '.join(sorted(self._items)) or '(none)'}."
            )
        return self._items[key]

    def __contains__(self, key):
        return key in self._items

    def keys(self):
        return self._items.keys()


# ==========================================================================
# CONSTANTS
# ==========================================================================
TOOL_VERSION = "0.9.0"
SUPPORTED_SCHEMA_VERSIONS = {"0.1"}

RENODE_REPO_URL = "https://github.com/renode/renode.git"
INTEGRATION_REPO_URL = "https://github.com/antmicro/renode-verilator-integration.git"

ARTIFACTS_DIR = ".hector"          # everything we generate/clone lives here (gitignore it)
# Path the project is bind-mounted at INSIDE the (always-Linux) container. On POSIX
# hosts we mirror the host cwd, so paths look identical in and out; on Windows the host
# path (C:\...) is not a valid Linux path, so use a fixed POSIX mount point and translate.
WORKSPACE_MOUNT = "/workspace" if os.name == "nt" else os.getcwd()
# Host directory bind-mounted at WORKSPACE_MOUNT. None = the cwd; --workspace-mount
# sets it to the config's directory, so the mount point is where execution happens.
WORKSPACE_ROOT = None
NO_DOCKER = False                 # when True, call renode/renode-test directly on host
EXTRA_MOUNTS = []                  # dep dirs outside the workspace, bind-mounted 1:1 into every container
DOCKER_ARGS = []                   # user flags (docker_args: + --docker-args) added to every `docker run`
# Host directory of the config file being executed. Paths written in the config resolve
# against it, and scripts / Renode run with it as their working directory. None = cwd
# (no config loaded, e.g. `run --snapshot` without one).
CONFIG_DIR = None
LIBOPENLIBM_NAME = "libopenlibm-Linux-x86_64.a"

DEFAULT_QUANTUM = "0.00001"        # 10 us; applied when any hub is present


# ==========================================================================
# RUNTIME OPTIONS  (execution-environment needs declared by components)
# ==========================================================================
@dataclass
class RuntimeOptions:
    """Execution-environment requirements a component (mapping / hub / module) needs
    from the Renode run. Components declare these at parse time; the pipeline merges
    them across all components and the docker layer maps them to `docker run` flags at
    execution time. Add fields here as new needs arise (ports, mounts, ...)."""
    capabilities: set = field(default_factory=set)   # -> docker --cap-add
    devices: set = field(default_factory=set)         # -> docker --device
    root: bool = False                                # -> docker -u 0:0 (run as root)

    def merge(self, other):
        """Fold another RuntimeOptions (or None) into this one."""
        if other:
            self.capabilities |= other.capabilities
            self.devices |= other.devices
            self.root = self.root or other.root
        return self


# ==========================================================================
# PATH TRANSLATION  (host <-> container)
# ==========================================================================
def host_uid_gid():
    """(uid, gid) of the invoking user, for `docker -u`, or None where the OS has no
    POSIX uid (Windows). On Windows there is nothing to pass — Docker Desktop maps
    bind-mount file ownership itself — so callers omit the flag / the chown."""
    if hasattr(os, "getuid"):
        return os.getuid(), os.getgid()
    return None


def workspace_root():
    """Host directory mounted at WORKSPACE_MOUNT (see WORKSPACE_ROOT)."""
    return os.path.realpath(WORKSPACE_ROOT or os.getcwd())


def to_container_path(host_path):
    abs_path = os.path.realpath(host_path)
    root = workspace_root()
    if os.path.commonpath([abs_path, root]) != root:
        # Dirs outside the workspace registered in EXTRA_MOUNTS (the config's dir or the
        # cwd, a shared Renode cache) are mounted 1:1, so their paths are valid as-is.
        for m in EXTRA_MOUNTS:
            if os.path.commonpath([abs_path, m]) == m:
                return abs_path
        raise ValueError(
            f"Path '{host_path}' resolves outside the project root '{root}'. Everything used "
            f"at runtime must live under the project folder (mounted at '{WORKSPACE_MOUNT}')."
        )
    # The container is always Linux: build a POSIX path under WORKSPACE_MOUNT (this is a
    # no-op on Linux, where WORKSPACE_MOUNT is the cwd and os.sep is already '/').
    rel = os.path.relpath(abs_path, root).replace(os.sep, "/")
    return WORKSPACE_MOUNT if rel == "." else posixpath.join(WORKSPACE_MOUNT, rel)


def register_dependency_mount(host_dir):
    """Return the container path for a dependency checkout (Renode source / integration),
    bind-mounting it 1:1 into every container if it lives OUTSIDE the workspace.

    Dirs under the workspace are already covered by the workspace mount, so they map via
    to_container_path. An out-of-tree dir (e.g. a shared cache) is registered in
    EXTRA_MOUNTS and used at its own absolute path inside the container."""
    try:
        return to_container_path(host_dir)    # already reachable through some mount
    except ValueError:
        abs_dir = os.path.realpath(host_dir)
        EXTRA_MOUNTS.append(abs_dir)
        return abs_dir


def container_path_for(host_path):
    """Container path for a host path that may live under an out-of-tree dependency mount
    (EXTRA_MOUNTS, bind-mounted 1:1); otherwise the normal workspace mapping."""
    abs_p = os.path.realpath(host_path)
    for m in EXTRA_MOUNTS:
        m_abs = os.path.realpath(m)
        if abs_p == m_abs or abs_p.startswith(m_abs + os.sep):
            return abs_p
    return to_container_path(host_path)


def container_to_host(container_path):
    # WORKSPACE_MOUNT and container paths are POSIX (the container is Linux), so compare
    # and split with '/' and posixpath, then map back onto the host's native separators.
    if container_path != WORKSPACE_MOUNT and not container_path.startswith(WORKSPACE_MOUNT + "/"):
        raise ValueError(f"'{container_path}' is not under {WORKSPACE_MOUNT}.")
    rel = posixpath.relpath(container_path, WORKSPACE_MOUNT).replace("/", os.sep)
    root = workspace_root()
    host = os.path.realpath(os.path.join(root, rel))
    if os.path.commonpath([host, root]) != root:
        raise ValueError(f"'{container_path}' maps outside the project root.")
    return host


def config_dir():
    """Host directory config-relative paths resolve against (see CONFIG_DIR)."""
    return CONFIG_DIR or os.getcwd()


def from_config(path):
    """Resolve a path written in the config against the config file's directory.
    Absolute paths (host or container, e.g. an interpolated ${RENODE_DIR}) and URLs
    are returned unchanged."""
    if not path or os.path.isabs(path) or path.startswith("/") or "://" in path:
        return path
    return os.path.normpath(os.path.join(config_dir(), path))


def execution_dir():
    """Working directory for everything hector executes (build/shell steps, Renode,
    renode-test): the config's directory — as a container path under Docker, a host
    path under --no-docker."""
    return config_dir() if NO_DOCKER else to_container_path(config_dir())


def split_host_container(path):
    if path == WORKSPACE_MOUNT or path.startswith(WORKSPACE_MOUNT + "/"):
        return container_to_host(path), path
    host = os.path.realpath(path)
    return host, to_container_path(host)


# ==========================================================================
# YAML / TEXT HELPERS
# ==========================================================================
def load_yaml(filepath):
    with open(filepath, "r") as f:
        return yaml.safe_load(f)


def run_shell(cmd, cwd=None, shell="/bin/bash"):
    subprocess.run(cmd, shell=True, check=True, executable=shell, cwd=cwd)


def as_lines(section):
    """Normalize a YAML block-string or list into meaningful lines (drop blanks and
    full-line '#' comments)."""
    if not section:
        return []
    raw = section.splitlines() if isinstance(section, str) else list(section)
    return [s.strip() for s in (str(x) for x in raw)
            if s.strip() and not s.strip().startswith("#")]


# ==========================================================================
# MATRIX & INTERPOLATION
# ==========================================================================
def expand_matrix(matrix_block):
    if not matrix_block or "variables" not in matrix_block:
        return [{}]
    variables = matrix_block["variables"]
    excludes = matrix_block.get("exclude", [])
    all_jobs = [dict(zip(variables.keys(), combo))
                for combo in itertools.product(*variables.values())]
    return [job for job in all_jobs
            if not any(all(job.get(k) == v for k, v in rule.items()) for rule in excludes)]


def resolve_arguments(arguments, overrides=None):
    """name -> value.  Precedence: --set flag > env var > config default."""
    overrides = overrides or {}
    resolved = {}
    for name, default in (arguments or {}).items():
        if name in overrides:
            resolved[name] = overrides[name]
            source = "cli"
        elif name in os.environ:
            resolved[name] = os.environ[name]
            source = "env"
        else:
            resolved[name] = default
            source = "default"
        print(f"[ARG] {name} = {resolved[name]}  ({source})")
    # --set can also introduce keys not declared in arguments:
    for name, value in overrides.items():
        if name not in resolved:
            resolved[name] = value
            print(f"[ARG] {name} = {value}  (cli, undeclared)")
    return resolved


def interpolate(data, context):
    if isinstance(data, str):
        return re.sub(r"\$\{([^}]+)\}",
                      lambda m: str(context.get(m.group(1), m.group(0))), data)
    if isinstance(data, dict):
        return {k: interpolate(v, context) for k, v in data.items()}
    if isinstance(data, list):
        return [interpolate(item, context) for item in data]
    return data


# ==========================================================================
# ENDPOINT PARSER  (connections + mappings)
#   node.name        -> kind='plain'
#   node.name@pin    -> kind='pin', pin=N   (Renode-style '@' pin / line number)
#   name             -> kind='self'         (bare; typically a hub reference)
# ==========================================================================
def parse_endpoint(token):
    token = token.strip()
    if "." not in token:
        return {"node": token, "name": token, "kind": "self", "raw": token}
    node, rest = token.split(".", 1)
    ep = {"node": node, "raw": rest}
    m = re.match(r"^([A-Za-z0-9_]+)@(0x[0-9A-Fa-f]+|\d+)$", rest)
    if m:
        ep.update(kind="pin", name=m.group(1), pin=int(m.group(2), 0))
        return ep
    if re.match(r"^[A-Za-z0-9_]+$", rest):
        ep.update(kind="plain", name=rest)
        return ep
    # node.periph.signal  (e.g. mcu.nvic.IRQ)
    m2 = re.match(r"^([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)$", rest)
    if m2:
        ep.update(kind="signal", periph=m2.group(1), name=m2.group(1), signal=m2.group(2))
        return ep
    raise ValueError(f"Could not parse endpoint '{token}'")