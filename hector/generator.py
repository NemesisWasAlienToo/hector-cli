# SPDX-License-Identifier: AGPL-3.0-or-later
"""Node descriptor, .repl generation, and .resc generation.

Each upstream step (peripherals, connections) is a pure data producer that populates
a NodeDescriptor. This module is the single place that turns those descriptors into
files on disk.
"""

import fnmatch
import glob
import os
import re
import shutil
from dataclasses import dataclass, field

from .core import ARTIFACTS_DIR
from .hubs import HUBS


# ==========================================================================
# DATA STRUCTURES
# ==========================================================================

@dataclass
class PeripheralDef:
    name: str
    ptype: str
    at: str | None
    args: dict
    signals: list       # IRQ/GPIO connection lines inlined on this peripheral
    init: str | None


@dataclass
class NodeDescriptor:
    name: str
    peripheral_defs: list = field(default_factory=list)   # PeripheralDef items, declaration order
    updating_entries: list = field(default_factory=list)  # (periph_name, wire_line) from connections
    so_commands: list = field(default_factory=list)       # Verilator SimulationFilePathLinux commands
    csharp_dlls: set = field(default_factory=set)
    init: str | None = None                               # sysbus init block (node-level init:)


# ==========================================================================
# REPL VALUE FORMATTING
# ==========================================================================

_IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_.]*$')
_HEX_RE   = re.compile(r'^0[xX][0-9a-fA-F]+$')


def repl_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return "[" + ", ".join(repl_value(i) for i in v) + "]"
    if isinstance(v, str):
        # Identifiers (peripheral refs) and hex literals are emitted unquoted.
        if _IDENT_RE.match(v) or _HEX_RE.match(v):
            return v
        return f'"{v}"'
    return str(v)


def build_repl_fragment(name, ptype, args=None, at=None, irqs=None, init=None):
    """One repl entry: `name: Type [@ registration]` plus args, IRQ connections, and init commands."""
    head = f"{name}: {ptype}" + (f" @ {at}" if at else "")
    lines = [head]
    lines += [f"    {k}: {repl_value(v)}" for k, v in (args or {}).items()]
    lines += [f"    {irq}" for irq in (irqs or [])]
    if init:
        lines.append("    init:")
        for cmd in init.splitlines():
            if cmd.strip():
                lines.append(f"        {cmd.strip()}")
    return "\n".join(lines)


def queue_command(node_config, command):
    node_config.setdefault("_gen_commands", []).append(command)


# ==========================================================================
# .REPL GENERATION
# ==========================================================================

def generate_node_repl(descriptor, job_index):
    """Write a .repl for one node from its NodeDescriptor.

    Layout:
      1. Peripheral declarations (with inline signals and per-peripheral init blocks)
      2. Updating entries from connections (one per intra-machine wire)
      3. sysbus: init: block (node-level init commands)

    Returns the host path written, or None if there was nothing to emit.
    """
    parts = []

    for p in descriptor.peripheral_defs:
        parts.append(build_repl_fragment(p.name, p.ptype, p.args, p.at,
                                         irqs=p.signals, init=p.init))

    for periph_name, wire in descriptor.updating_entries:
        parts.append(f"{periph_name}:\n    {wire}")

    if not parts and not descriptor.init:
        return None

    repl_root = os.path.join(ARTIFACTS_DIR, "repl")
    os.makedirs(repl_root, exist_ok=True)
    repl_host = os.path.join(repl_root, f"job_{job_index}_{descriptor.name}.gen.repl")

    with open(repl_host, "w") as f:
        if parts:
            f.write("\n\n".join(parts) + "\n")
        if descriptor.init:
            indented = "\n".join(f"        {l}" for l in descriptor.init.splitlines())
            f.write(f"\nsysbus:\n    init:\n{indented}\n")

    return repl_host


def write_inline_repl(node_name, content, job_index):
    """Materialise a machine's inline `repl:` text as a real .repl file and return its
    host path.

    Renode only loads platform descriptions from disk, so inline text has to land in a
    file first. This is what lets a config carry a board that isn't in the released
    Renode image yet (e.g. one that only exists on master) — paste its .repl here
    instead of referencing a path the image doesn't ship.
    """
    if isinstance(content, list):
        content = "\n".join(content)
    repl_root = os.path.join(ARTIFACTS_DIR, "repl")
    os.makedirs(repl_root, exist_ok=True)
    repl_host = os.path.join(repl_root, f"job_{job_index}_{node_name}.inline.repl")
    with open(repl_host, "w") as f:
        f.write(content.rstrip() + "\n")
    return repl_host


# ==========================================================================
# NODE COMMAND FINALIZATION
# ==========================================================================

def finalize_commands(concrete_nodes):
    """Prepend generated commands (instance attaches, then host mappings) before the
    user's own commands: order is [attach] [map] [user]."""
    for node_config in concrete_nodes.values():
        gen = node_config.get("_gen_commands")
        if not gen:
            continue
        block = "\n".join(gen)
        existing = node_config.get("commands")
        if not existing:
            node_config["commands"] = block
        elif isinstance(existing, list):
            node_config["commands"] = [block] + existing
        else:
            node_config["commands"] = block + "\n" + existing.rstrip()


# ==========================================================================
# .RESC GENERATION
# ==========================================================================

def generate_emulation_resc(renode_nodes, hubs_registry, cross_connections,
                            quantum, debug_config, output_filename, emulation_setup=None,
                            no_start=False):
    """One resc per job: every node becomes a named machine in one emulation; hubs and
    cross-machine connectors wire them; one shared `start`.

    renode_nodes    : list of (node_name, node_config)
    hubs_registry   : {hub_name: hub_type}
    debug_config    : {node_name: gdb_port}
    emulation_setup : list of emulation-level lines to emit before machine blocks
                      (e.g. CreateServerSocketTerminal, CreateUartPtyTerminal)
    no_start        : omit the trailing `start` so the platform loads paused and the
                      user starts it by hand from the monitor (`hector run --no-start`)
    """
    lines = []

    # --- emulation-level setup (terminals, etc.) – must exist before machines connect ---
    if emulation_setup:
        lines.append("# === emulation-level setup ===")
        lines.extend(emulation_setup)

    # --- machines ---
    for node_name, node_config in renode_nodes:
        lines.append(f"\n# === machine: {node_name} ===")
        lines.append(f'mach create "{node_name}"')
        for repl in node_config.get("platform", []):
            lines.append(f"machine LoadPlatformDescription @{repl}")
        fw = node_config.get("firmware")
        if fw and fw != "none":
            lines.append(f"sysbus LoadELF @{fw}")
        # Verbatim monitor script lifted from an upstream .resc, emitted before the
        # user's own `commands:` (which stay the last word on this machine).
        resc = node_config.get("resc", "")
        if resc:
            lines.extend(resc if isinstance(resc, list) else [resc.strip()])
        cmds = node_config.get("commands", "")
        if cmds:
            lines.extend(cmds if isinstance(cmds, list) else [cmds.strip()])
        if node_name in debug_config:
            port = debug_config[node_name]
            lines.append(f"machine StartGdbServer {port}")
            lines.append("cpu IsHalted true")
            lines.append(f'echo "GDB server ready for {node_name} on port {port}"')

    # --- emulation-global quantum ---
    if quantum:
        lines.append(f'\nemulation SetGlobalQuantum "{quantum}"')

    # --- hubs (each hub class emits its own create command) ---
    if hubs_registry:
        lines.append("\n# === hubs ===")
        for hub_name, hub_type in hubs_registry.items():
            lines.extend(HUBS.get(hub_type).emit_create(hub_name))

    # --- cross-machine connections (each hub class emits its own connect lines) ---
    if cross_connections:
        lines.append("\n# === cross-machine connections ===")
        for spec in cross_connections:
            lines.extend(HUBS.get(hubs_registry[spec["hub"]]).emit_connect(spec))

    if no_start:
        lines.append('\necho "Platform loaded (paused). Type \'start\' to begin execution."')
    else:
        lines.append("\nstart")
    content = "\n".join(lines)
    with open(output_filename, "w") as f:
        f.write(content)
    return content


def snapshot_resc(snapshot_container_path, debug_config=None, no_start=False):
    """Build resc text that loads a snapshot and resumes.

    When debug_config ({machine_name: gdb_port}) is given, each named machine gets a
    GDB server opened and its CPU halted before the resume — so a loaded snapshot is
    debuggable just like a fresh boot. (A GDB server is a live connection, never part
    of saved snapshot state, so it must be (re)started after every Load.)

    no_start omits the trailing `start`, leaving the restored state paused in the
    monitor for the user to resume by hand (`hector run --snapshot ... --no-start`).
    """
    lines = [f"Load @{snapshot_container_path}"]
    for node_name, port in (debug_config or {}).items():
        lines += [f'mach set "{node_name}"',
                  f"machine StartGdbServer {port}",
                  "cpu IsHalted true",
                  f'echo "GDB server ready for {node_name} on port {port}"']
    if no_start:
        lines.append('echo "Snapshot loaded (paused). Type \'start\' to resume."')
    else:
        lines.append("start")
    return "\n".join(lines) + "\n"


# ==========================================================================
# ARTIFACT COLLECTION
# ==========================================================================

def collect_artifacts(patterns, output_dir, job_index=None, base_dir="."):
    """Sweep the global artifact glob patterns and copy matches into
    <output_dir>/artifacts/ so a single directory can be uploaded by CI / read by a
    dashboard.

    patterns   : list of glob strings (top-level 'artifacts:' or --artifacts override)
    output_dir : the run output directory (--output)
    job_index  : 1-based job number; prefixes copied filenames to avoid cross-job clashes
    base_dir   : directory relative patterns resolve against (the config's directory
                 for 'artifacts:', the cwd for --artifacts)

    Returns the list of collected destination paths (relative to cwd).
    """
    if not patterns:
        return []
    dest_root = os.path.realpath(os.path.join(output_dir, "artifacts"))
    # Never collect from the framework's own tree (the Renode/integration clones and
    # generated files live here) or from our own previous copies.
    prune = (dest_root, os.path.realpath(ARTIFACTS_DIR))
    job_sub = f"job_{job_index}" if job_index else ""
    collected, seen = [], set()
    header_shown = False
    for pattern in patterns:
        for src in sorted(_match_artifacts(pattern, dest_root, base_dir)):
            real = os.path.realpath(src)
            if real in seen or not os.path.isfile(real):
                continue
            if any(real == p or real.startswith(p + os.sep) for p in prune):
                continue
            seen.add(real)
            # Mirror the source path under artifacts/job_N/ so files with the same
            # basename in different directories don't clobber each other.
            rel_src = os.path.relpath(real)
            if rel_src.startswith(".."):       # outside cwd → flatten to basename
                rel_src = os.path.basename(real)
            dest = os.path.join(dest_root, job_sub, rel_src)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(real, dest)
            rel = os.path.relpath(dest)
            collected.append(rel)
            if not header_shown:
                label = f" (job {job_index})" if job_index else ""
                print(f"\n[ARTIFACTS]{label}:")
                header_shown = True
            print(f"  -> {os.path.relpath(real)}  →  {rel}")
    return collected


def _match_artifacts(pattern, dest_root, base_dir="."):
    """Resolve one artifact glob pattern (relative to base_dir) to a list of host paths.

    A bare filename pattern (no '/', e.g. '*.xml') searches the whole base_dir tree
    recursively, pruning hidden dirs (.hector, .git, …) and the artifacts output dir —
    so 'results/junit.xml' is found without sweeping the bundled Renode clone.
    A pattern with a path component ('results/*.bin', 'logs/**/*.log') is passed to
    glob as-is, so explicit directories and '**' behave normally.
    """
    if "/" in pattern or os.sep in pattern:
        return glob.glob(os.path.join(base_dir, pattern), recursive=True)
    matches = []
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs
                   if not d.startswith(".")
                   and os.path.realpath(os.path.join(root, d)) != dest_root]
        matches.extend(os.path.join(root, name) for name in fnmatch.filter(files, pattern))
    return matches
