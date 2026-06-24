# SPDX-License-Identifier: AGPL-3.0-or-later
"""Peripheral instantiation: place a native Renode class OR a module type into a machine.

Verilator (.so) modules:  per-instance .so copy + SimulationFilePathLinux command
                          (stored in NodeDescriptor.so_commands).
C# (.dll) modules:        emulation-level `i @<dll>` import (stored in
                          NodeDescriptor.csharp_dlls; pipeline.py emits these before
                          any machine block in the resc).
"""

import os

from .core import to_container_path
from .generator import NodeDescriptor, PeripheralDef
from .modules import materialize_instance_so

_RESERVED = {"type", "at", "peripherals", "init", "connections"}


def _parse_repl_signals(raw):
    """Parse repl-style signal connection lines into {peripheral_name: [repl_line, ...]}.

    Each line: <periph>[<pin_range>] -> <target>@<pin>
      nvic -> cpu@0               =>  nvic:        ["-> cpu@0"]
      nvic.IRQ -> cpu@0           =>  nvic:        ["IRQ -> cpu@0"]
      gpioPortC[0-15] -> nvic@6  =>  gpioPortC:   ["[0-15] -> nvic@6"]

    The destination (right of '->') is preserved verbatim, so Renode's receiver
    qualifiers pass through untouched, e.g. a local index '#N' and an input pin '@N':
      timer1@0 -> gpioPortA#08@01  =>  timer1:     ["0 -> gpioPortA#08@01"]
    The source (left of '->') is only a named signal, a number, or a range — '#' is a
    receiver-only qualifier, so a '#' on the source side is flagged, not emitted.
    """
    result = {}
    for line in (raw or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if " -> " not in line:
            print(f"  [WARN] irqs: '{line}' has no '->' — skipped.")
            continue
        source, target = line.split(" -> ", 1)
        source, target = source.strip(), target.strip()
        if "#" in source:
            # '#localIndex' is a Renode *receiver* qualifier (it belongs on the
            # destination, right of '->'). It has no meaning on the source side, so
            # emitting it would produce a .repl Renode rejects. Flag and skip.
            print(f"  [WARN] irqs: '{line}' has '#' on the source side; '#index' is a "
                  "destination (receiver) qualifier and belongs after '->' "
                  "(e.g. 'timer1@0 -> gpioPortA#08@01'). Skipped.")
            continue
        if "[" in source:
            periph, pin = source.split("[", 1)
            irq_line = f"[{pin} -> {target}"
        elif "." in source:
            periph, signal = source.split(".", 1)
            irq_line = f"{signal} -> {target}"
        elif "@" in source:
            periph, pin = source.split("@", 1)
            irq_line = f"{pin} -> {target}"
        else:
            periph = source
            irq_line = f"-> {target}"
        result.setdefault(periph.strip(), []).append(irq_line)
    return result


def _gather_connections(peripherals):
    """Collect `connections:` blocks declared on peripherals (recursively).

    Lets wiring live next to the peripheral it concerns — e.g. an `mcu` grouping
    peripheral can carry all the MCU-internal wiring, separate from a board-level
    `connections:` at the node. Returns the combined raw text, parsed together with
    the node-level connections. These are always intra-machine signals; cross-machine
    hub links must still use the node-level `connections:` block.
    """
    blocks = []
    for spec in (peripherals or {}).values():
        spec = spec or {}
        if not isinstance(spec, dict):
            continue
        conn = spec.get("connections")
        if conn:
            blocks.append(conn if isinstance(conn, str) else "\n".join(str(c) for c in conn))
        child = spec.get("peripherals")
        if child:
            sub = _gather_connections(child)
            if sub:
                blocks.append(sub)
    return "\n".join(blocks)


def resolve_peripherals(concrete_nodes, modules_registry):
    """Build a NodeDescriptor for each renode node.

    Returns {node_name: NodeDescriptor} with peripheral_defs, so_commands,
    csharp_dlls, and init populated. updating_entries is left empty — connections.py
    fills those in later.
    """
    descriptors = {}
    for node_name, node_config in concrete_nodes.items():
        if node_config.get("backend", "renode") != "renode":
            continue
        # Wiring may be declared at the node level (`connections:`) or inline on a
        # peripheral (a `connections:` block on the peripheral it concerns). Both are
        # intra-machine signals and merge into one map.
        raw_signals = node_config.get("_repl_signals", "")
        periph_signals = _gather_connections(node_config.get("peripherals") or {})
        signals_map = _parse_repl_signals(
            "\n".join(s for s in (raw_signals, periph_signals) if s))
        init = (node_config.get("init") or "").strip() or None
        descriptor = NodeDescriptor(name=node_name, init=init)

        for instance, spec in (node_config.get("peripherals") or {}).items():
            _resolve(instance, spec or {}, node_name, descriptor, modules_registry,
                     default_at="sysbus", signals_map=signals_map)

        # Signals targeting peripherals not declared in this YAML (from a platform .repl file)
        # can't be inlined; emit them as updating entries instead.
        declared = {p.name for p in descriptor.peripheral_defs}
        for periph_name, wires in signals_map.items():
            if periph_name not in declared:
                for wire in wires:
                    descriptor.updating_entries.append((periph_name, wire))

        descriptors[node_name] = descriptor
    return descriptors


def _resolve(instance, spec, node_name, descriptor, modules_registry, default_at, signals_map=None):
    type_name = spec.get("type")
    if not type_name:
        raise ValueError(f"peripherals.{instance} on '{node_name}' is missing 'type'.")

    at = spec["at"] if "at" in spec else default_at
    at = at or None
    signals = list((signals_map or {}).get(instance, []))
    init = spec.get("init") or None
    args = {k: v for k, v in spec.items() if k not in _RESERVED}

    if type_name in modules_registry:
        mod = modules_registry[type_name]
        descriptor.peripheral_defs.append(
            PeripheralDef(name=instance, ptype=mod["type"], at=at,
                          args=args, signals=signals, init=init))

        if mod["artifact_type"] == "so":
            inst_so = materialize_instance_so(node_name, instance, mod["artifact_host"])
            descriptor.so_commands.append(
                f"{instance} SimulationFilePathLinux @{to_container_path(inst_so)}")
            print(f"[INST] {node_name}.{instance} = module '{type_name}' ({mod['type']})"
                  + (f" @ {at}" if at else "")
                  + f"  [.so: {os.path.basename(inst_so)}]")
        else:
            descriptor.csharp_dlls.add(mod["artifact_host"])
            print(f"[INST] {node_name}.{instance} = C# module '{type_name}' ({mod['type']})"
                  + (f" @ {at}" if at else "")
                  + f"  [.dll: {os.path.basename(mod['artifact_host'])}]")
    else:
        descriptor.peripheral_defs.append(
            PeripheralDef(name=instance, ptype=type_name, at=at,
                          args=args, signals=signals, init=init))
        print(f"[INST] {node_name}.{instance} = native {type_name} "
              + (f"@ {at}" if at else "(no registration)"))

    for child_instance, child_spec in (spec.get("peripherals") or {}).items():
        _resolve(child_instance, child_spec or {}, node_name, descriptor, modules_registry,
                 default_at=instance, signals_map=signals_map)
