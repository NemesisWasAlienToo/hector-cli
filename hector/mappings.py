# SPDX-License-Identifier: AGPL-3.0-or-later
"""
MAPPING_BACKENDS  -  bind an emulated peripheral to a host resource.

PTY and TCP backends follow a two-step emulation model (identical to hubs):
  1. An emulation-level object is created before any machine blocks in the resc.
  2. The machine connects its peripheral to that object via `connector Connect`.

The `file` backend is peripheral-level only (no emulation object needed).

==========================================================================
HOW TO ADD A NEW MAPPING BACKEND
==========================================================================
Register a function:  (node_name, peripheral, param, node_config) -> MappingResult

    @MAPPING_BACKENDS.register("tap")
    def tap_backend(node_name, peripheral, param, node_config):
        iface = param or "tap0"
        term  = f"ss_{node_name}_{peripheral}"
        return MappingResult(
            machine_cmd     = f"connector Connect sysbus.{peripheral} {term}",
            emulation_lines = [f'emulation CreateTap "{term}" "{iface}"'],
        )

`emulation_lines` are emitted at the top of the resc before any `mach create` blocks
so the object already exists when the machine tries to connect to it. `machine_cmd` is
queued on the node as an ordinary monitor command.

YAML then accepts:   mappings: |\n  boardA.eth0 -> tap:tap0
==========================================================================
"""

from dataclasses import dataclass, field
from typing import List

from .core import Registry, RuntimeOptions, from_config, parse_endpoint, to_container_path
from .generator import queue_command

MAPPING_BACKENDS = Registry("mapping backend")


@dataclass
class MappingResult:
    """What a mapping backend produces for one mapping line."""
    machine_cmd: str                          # monitor command queued on the node
    emulation_lines: List[str] = field(default_factory=list)   # emulation-level setup
    runtime: RuntimeOptions = field(default_factory=RuntimeOptions)  # execution-env needs


# -------------------- backends --------------------
@MAPPING_BACKENDS.register("file")
def file_backend(_node_name, peripheral, param, _node_config):
    """Redirect UART output to a file.  uart4 -> file:results/uart.log
    Subsequent calls append with a numeric suffix rather than overwriting."""
    if not param:
        raise ValueError("'file' backend requires a path (file:<path>).")
    return MappingResult(
        machine_cmd=f"{peripheral} CreateFileBackend @{to_container_path(from_config(param))} true",
    )


@MAPPING_BACKENDS.register("tcp")
def tcp_backend(node_name, peripheral, param, _node_config):
    """Expose a UART as a TCP socket terminal.  uart4 -> tcp:4567
    Append ':raw' to suppress IAC telnet bytes:  uart4 -> tcp:4567:raw
    """
    if not param:
        raise ValueError("'tcp' backend requires a port number (tcp:<port>).")

    # Optional ':raw' suffix suppresses IAC bytes
    raw = False
    if ":" in param:
        port_str, _, flag = param.partition(":")
        raw = flag.strip().lower() == "raw"
    else:
        port_str = param

    try:
        port = int(port_str)
    except ValueError:
        raise ValueError(f"'tcp' backend: '{port_str}' is not a valid port number.")
    if not 1 <= port <= 65535:
        raise ValueError(f"'tcp' backend: port {port} is out of range (1-65535).")

    term_name = f"ss_{node_name}_{peripheral}"
    create_cmd = (f'emulation CreateServerSocketTerminal {port} "{term_name}" false'
                  if raw else
                  f'emulation CreateServerSocketTerminal {port} "{term_name}"')
    return MappingResult(
        machine_cmd=f"connector Connect sysbus.{peripheral} {term_name}",
        emulation_lines=[create_cmd],
    )


@MAPPING_BACKENDS.register("pty")
def pty_backend(node_name, peripheral, param, _node_config):
    """Expose a UART as a PTY symlink inside the container.  uart4 -> pty:/tmp/uart4
    Note: PTY is not accessible from the host when running in Docker; use tcp: instead.
    """
    if not param:
        raise ValueError("'pty' backend requires a path (pty:/tmp/uart0).")

    term_name = f"ss_{node_name}_{peripheral}"
    return MappingResult(
        machine_cmd=f"connector Connect sysbus.{peripheral} {term_name}",
        emulation_lines=[f'emulation CreateUartPtyTerminal "{term_name}" "{param}"'],
    )


@MAPPING_BACKENDS.register("tap")
def tap_backend(node_name, peripheral, param, _node_config):
    """Bridge an Ethernet peripheral to a host TAP device.  eth0 -> tap:tap0

    Host interface name defaults to 'tap0'. Renode wires the emulated NIC and the host
    TAP through a switch (the NIC can't connect to the TAP directly), so this creates a
    per-mapping switch, a TAP (exposed as `host.<name>`), and joins both to the switch.
    Creating a TAP needs NET_ADMIN and /dev/net/tun on the container (host networking
    alone does NOT grant these).
    """
    iface = param or "tap0"
    sw = f"sw_{node_name}_{peripheral}"        # emulation switch
    tap = f"tap_{node_name}_{peripheral}"      # Renode TAP element -> host.<tap>
    return MappingResult(
        machine_cmd=f"connector Connect sysbus.{peripheral} {sw}",
        emulation_lines=[
            f'emulation CreateSwitch "{sw}"',
            # CreateTap(hostInterfaceName, name): host device first, Renode name second.
            f'emulation CreateTap "{iface}" "{tap}"',
            f'connector Connect host.{tap} {sw}',
        ],
        # Opening a real host TAP needs the TUN device, NET_ADMIN, and root.
        runtime=RuntimeOptions(capabilities={"NET_ADMIN"},
                               devices={"/dev/net/tun"}, root=True),
    )


# -------------------- resolver --------------------
def resolve_mappings(mappings, concrete_nodes):
    """Process each mapping line; queue machine commands on nodes.

    Returns (emulation_lines, runtime): the emulation-level setup lines to emit before
    machine blocks, and the merged RuntimeOptions any backend declared (e.g. a tap needs
    TUN/TAP access) so the caller can grant them without re-scanning the generated resc."""
    emulation_lines = []
    runtime = RuntimeOptions()
    for line in mappings:
        if "->" not in line:
            raise ValueError(f"Mapping '{line}' has no '->' operator")
        lhs, rhs = line.split("->", 1)
        ep = parse_endpoint(lhs)
        backend, _, param = rhs.strip().partition(":")
        backend, param = backend.strip(), (param.strip() or None)

        node = ep["node"]
        if node not in concrete_nodes:
            raise ValueError(f"Mapping '{line}': unknown node '{node}'.")
        if concrete_nodes[node].get("backend", "renode") != "renode":
            raise ValueError(f"Mapping '{line}': left side must be on a renode node.")

        handler = MAPPING_BACKENDS.get(backend)
        result = handler(node, ep["name"], param, concrete_nodes[node])
        queue_command(concrete_nodes[node], result.machine_cmd)
        emulation_lines.extend(result.emulation_lines)
        runtime.merge(result.runtime)
        print(f"[MAP]  {node}.{ep['name']} -> {backend}:{param or ''}")

    return emulation_lines, runtime