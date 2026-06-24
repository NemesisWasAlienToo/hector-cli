# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Connection resolution. Generic over the HUBS registry, so adding a hub type needs no
change here.

  intra-machine (same node, '->')   -> repl updating entry (GPIO/IRQ wire)
  periph <-> hub  /  port@pin -> hub -> cross-machine link via a declared hub
"""

import re

from .core import parse_endpoint
from .hubs import HUBS


def is_hub_line(line, hubs_registry):
    """Return True if any token in the line is a declared hub name."""
    for tok in re.split(r"<->|->", line):
        base = re.split(r"[@\[]", tok.strip())[0]
        if "." not in base and base in hubs_registry:
            return True
    return False


def _expand_chains(connections):
    """Expand inline hub-chain syntax into two separate endpoint↔hub lines.

    Symmetric:    A <-> hub <-> B   →   A <-> hub  +  B <-> hub
    Directional:  A -> hub -> B    →   A -> hub   +  hub -> B
    """
    result = []
    for line in connections:
        parts = line.split("<->")
        if len(parts) == 3:
            a, hub, b = (p.strip() for p in parts)
            result += [f"{a} <-> {hub}", f"{b} <-> {hub}"]
            continue
        if "<->" not in line:
            parts = line.split("->")
            if len(parts) == 3:
                a, hub, b = (p.strip() for p in parts)
                result += [f"{a} -> {hub}", f"{hub} -> {b}"]
                continue
        result.append(line)
    return result


def qualify_node_connection(line, node_name, hubs_registry, known_nodes=None):
    """Qualify bare peripheral names in a per-node connections block with the node name.
    Hub names and already-qualified 'node.x' tokens are left unchanged.
    'periph.Signal' tokens (where periph is not a node) are qualified as 'node.periph.Signal'."""
    known_nodes = known_nodes or set()
    def q(tok):
        tok = tok.strip()
        base = tok.split("@", 1)[0]
        if "." in base:
            prefix = base.split(".", 1)[0]
            if prefix in known_nodes or prefix in hubs_registry:
                return tok
            return f"{node_name}.{tok}"
        return tok if base in hubs_registry else f"{node_name}.{tok}"
    parts = line.split("<->")
    if len(parts) == 3:
        a, hub, b = (p.strip() for p in parts)
        return f"{q(a)} <-> {hub} <-> {q(b)}"
    if "<->" not in line:
        parts = line.split("->")
        if len(parts) == 3:
            a, hub, b = (p.strip() for p in parts)
            return f"{q(a)} -> {hub} -> {q(b)}"
    if "<->" in line:
        a, b = line.split("<->", 1); return f"{q(a)} <-> {q(b)}"
    if "->" in line:
        a, b = line.split("->", 1); return f"{q(a)} -> {q(b)}"
    raise ValueError(f"Connection '{line}' (node '{node_name}') has no '->' or '<->'")


def resolve_connections(connections, concrete_nodes, hubs_registry):
    """Return cross_connection_specs for hub-connected endpoints.
    All intra-machine wires must have been injected into _repl_signals before calling this.
    `hubs_registry` maps a hub NAME to its declared type string."""
    def check_node(node, line):
        if node not in concrete_nodes:
            raise ValueError(f"Connection '{line}': unknown node '{node}'.")
        if concrete_nodes[node].get("backend", "renode") != "renode":
            raise ValueError(f"Connection '{line}': '{node}' is not a renode node.")

    specs = []
    hub_specs = {}
    for line in _expand_chains(connections):
        if "<->" in line:  a, b = line.split("<->", 1); op = "<->"
        elif "->" in line: a, b = line.split("->", 1); op = "->"
        else: raise ValueError(f"Connection '{line}' has no '->' or '<->'")
        a, b = a.strip(), b.strip()
        a_hub = is_hub_line(a, hubs_registry)
        b_hub = is_hub_line(b, hubs_registry)

        if not a_hub and not b_hub:
            raise ValueError(
                f"Connection '{line}': non-hub connection reached resolve_connections. "
                "Cross-machine links require a hub declared under 'hubs:'. "
                "Intra-machine wires belong in the per-node 'connections:' block.")

        if a_hub and b_hub:
            raise ValueError(f"Connection '{line}': both sides are hubs.")

        hub_name = (a if a_hub else b).split("@", 1)[0]
        ep = parse_endpoint(b if a_hub else a)
        check_node(ep["node"], line)
        hub_cls = HUBS.get(hubs_registry[hub_name])

        if hub_cls.symmetric and op != "<->":
            raise ValueError(f"Connection '{line}': '{hub_name}' is symmetric; use '<->'.")
        if not hub_cls.symmetric and op != "->":
            raise ValueError(f"Connection '{line}': '{hub_name}' is directional; use '->'.")

        spec = hub_cls.build_spec(ep["node"], ep["name"], hub_name, ep,
                                  hub_on_left=a_hub, line=line)
        specs.append(spec)
        hub_specs.setdefault(hub_name, (hub_cls, []))[1].append(spec)

    for hub_name, (hub_cls, hspecs) in hub_specs.items():
        if hub_cls.symmetric and len(hspecs) == 2:
            a = f'{hspecs[0]["node"]}.{hspecs[0]["periph"]}'
            b = f'{hspecs[1]["node"]}.{hspecs[1]["periph"]}'
            print(f"[XCONN] {a} <-> {hub_name} <-> {b}")
        else:
            for spec in hspecs:
                print(f"[XCONN] {hub_cls.describe(spec)}")
    return specs