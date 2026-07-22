"""Unit tests for hector.mappings — peripheral->host backends and the resolver that
queues machine commands, collects emulation setup, and merges runtime requirements."""

import pytest

from hector import core
from hector.mappings import MAPPING_BACKENDS, resolve_mappings


@pytest.fixture(autouse=True)
def in_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(core, "WORKSPACE_MOUNT", str(tmp_path))
    monkeypatch.setattr(core, "EXTRA_MOUNTS", [])


# ---- individual backends ----

def test_file_backend_creates_file_backend_cmd():
    res = MAPPING_BACKENDS.get("file")("mcu", "uart4", "results/uart.log", {})
    assert res.machine_cmd.startswith("uart4 CreateFileBackend @")
    assert res.machine_cmd.endswith('results/uart.log true')


def test_file_backend_requires_path():
    with pytest.raises(ValueError, match="requires a path"):
        MAPPING_BACKENDS.get("file")("mcu", "uart4", None, {})


def test_tcp_backend_default_and_raw():
    plain = MAPPING_BACKENDS.get("tcp")("mcu", "uart4", "4567", {})
    assert plain.emulation_lines == ['emulation CreateServerSocketTerminal 4567 "ss_mcu_uart4"']
    assert plain.machine_cmd == "connector Connect sysbus.uart4 ss_mcu_uart4"
    raw = MAPPING_BACKENDS.get("tcp")("mcu", "uart4", "4567:raw", {})
    assert raw.emulation_lines == ['emulation CreateServerSocketTerminal 4567 "ss_mcu_uart4" false']


def test_tcp_backend_bad_port_and_range():
    with pytest.raises(ValueError, match="valid port"):
        MAPPING_BACKENDS.get("tcp")("mcu", "uart4", "notaport", {})
    with pytest.raises(ValueError, match="out of range"):
        MAPPING_BACKENDS.get("tcp")("mcu", "uart4", "70000", {})
    with pytest.raises(ValueError, match="requires a port"):
        MAPPING_BACKENDS.get("tcp")("mcu", "uart4", None, {})


def test_pty_backend():
    res = MAPPING_BACKENDS.get("pty")("mcu", "uart0", "/tmp/uart0", {})
    assert res.emulation_lines == ['emulation CreateUartPtyTerminal "ss_mcu_uart0" "/tmp/uart0"']
    assert res.machine_cmd == "connector Connect sysbus.uart0 ss_mcu_uart0"


def test_tap_backend_wires_switch_and_declares_runtime():
    res = MAPPING_BACKENDS.get("tap")("mcu", "eth0", "tap0", {})
    assert 'emulation CreateSwitch "sw_mcu_eth0"' in res.emulation_lines
    assert 'emulation CreateTap "tap0" "tap_mcu_eth0"' in res.emulation_lines
    assert 'connector Connect host.tap_mcu_eth0 sw_mcu_eth0' in res.emulation_lines
    # A real host TAP needs NET_ADMIN + /dev/net/tun + root.
    assert res.runtime.capabilities == {"NET_ADMIN"}
    assert res.runtime.devices == {"/dev/net/tun"}
    assert res.runtime.root is True


# ---- resolve_mappings ----

def _nodes(*names):
    return {n: {"backend": "renode"} for n in names}


def test_resolve_queues_command_and_collects_emulation():
    nodes = _nodes("mcu")
    emu, runtime = resolve_mappings(["mcu.uart4 -> tcp:4567"], nodes)
    assert nodes["mcu"]["_gen_commands"] == ["connector Connect sysbus.uart4 ss_mcu_uart4"]
    assert emu == ['emulation CreateServerSocketTerminal 4567 "ss_mcu_uart4"']
    assert runtime.capabilities == set()


def test_resolve_merges_runtime_from_tap():
    nodes = _nodes("mcu")
    _emu, runtime = resolve_mappings(["mcu.eth0 -> tap:tap0"], nodes)
    assert runtime.root is True and "NET_ADMIN" in runtime.capabilities


def test_resolve_missing_operator():
    with pytest.raises(ValueError, match="no '->' operator"):
        resolve_mappings(["uart4 tcp:4567"], _nodes("mcu"))


def test_resolve_unknown_node():
    with pytest.raises(ValueError, match="unknown node"):
        resolve_mappings(["ghost.uart4 -> tcp:4567"], _nodes("mcu"))


def test_resolve_non_renode_node():
    nodes = {"mcu": {"backend": "qemu"}}
    with pytest.raises(ValueError, match="must be on a renode node"):
        resolve_mappings(["mcu.uart4 -> tcp:4567"], nodes)


def test_resolve_unknown_backend():
    with pytest.raises(KeyError):
        resolve_mappings(["mcu.uart4 -> bogus:1"], _nodes("mcu"))
