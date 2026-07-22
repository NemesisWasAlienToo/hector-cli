"""Unit tests for hector.connections — hub-line detection, chain expansion, node
qualification, and cross-machine spec resolution (generic over the HUBS registry)."""

import pytest

from hector.connections import (_expand_chains, is_hub_line, qualify_node_connection,
                                resolve_connections)

HUBS_REG = {"uart_link": "uart", "gpio_link": "gpio"}


# ---- is_hub_line ----

def test_is_hub_line_detects_bare_hub_token():
    assert is_hub_line("uart_link", HUBS_REG) is True


def test_is_hub_line_ignores_qualified_node_token():
    assert is_hub_line("mcu.usart1", HUBS_REG) is False


def test_is_hub_line_strips_pin_and_range():
    assert is_hub_line("gpio_link@3", HUBS_REG) is True
    assert is_hub_line("gpio_link[0-3]", HUBS_REG) is True


# ---- _expand_chains ----

def test_expand_symmetric_chain():
    assert _expand_chains(["a <-> hub <-> b"]) == ["a <-> hub", "b <-> hub"]


def test_expand_directional_chain():
    assert _expand_chains(["a -> hub -> b"]) == ["a -> hub", "hub -> b"]


def test_expand_passthrough_two_part():
    assert _expand_chains(["a <-> b"]) == ["a <-> b"]
    assert _expand_chains(["a -> b"]) == ["a -> b"]


# ---- qualify_node_connection ----

def test_qualify_bare_peripheral_names():
    out = qualify_node_connection("button -> gpioPortC@13", "mcu", HUBS_REG)
    assert out == "mcu.button -> mcu.gpioPortC@13"


def test_qualify_leaves_hub_name_unqualified():
    out = qualify_node_connection("usart1 <-> uart_link", "mcu", HUBS_REG)
    assert out == "mcu.usart1 <-> uart_link"


def test_qualify_leaves_known_node_prefix():
    out = qualify_node_connection("other.uart1 <-> uart_link", "mcu", HUBS_REG,
                                  known_nodes={"other"})
    assert out == "other.uart1 <-> uart_link"


def test_qualify_periph_signal_gets_node_prefix():
    # nvic.IRQ where nvic is a peripheral (not a node) -> mcu.nvic.IRQ
    out = qualify_node_connection("nvic.IRQ -> cpu@0", "mcu", HUBS_REG)
    assert out == "mcu.nvic.IRQ -> mcu.cpu@0"


def test_qualify_three_part_chain():
    out = qualify_node_connection("a <-> uart_link <-> b", "mcu", HUBS_REG)
    assert out == "mcu.a <-> uart_link <-> mcu.b"


def test_qualify_no_operator_raises():
    with pytest.raises(ValueError, match="no '->' or '<->'"):
        qualify_node_connection("just_a_token", "mcu", HUBS_REG)


# ---- resolve_connections ----

def _nodes(*names):
    return {n: {"backend": "renode"} for n in names}


def test_resolve_symmetric_pair_builds_specs():
    specs = resolve_connections(
        ["mcu.usart1 <-> uart_link <-> board.uart1"], _nodes("mcu", "board"),
        {"uart_link": "uart"})
    assert len(specs) == 2
    assert {s["node"] for s in specs} == {"mcu", "board"}
    assert all(s["hub"] == "uart_link" for s in specs)


def test_resolve_symmetric_hub_requires_symmetric_operator():
    with pytest.raises(ValueError, match="symmetric; use '<->'"):
        resolve_connections(["mcu.usart1 -> uart_link"], _nodes("mcu"),
                            {"uart_link": "uart"})


def test_resolve_directional_hub_requires_arrow():
    with pytest.raises(ValueError, match="directional; use '->'"):
        resolve_connections(["mcu.gpioA@0 <-> gpio_link"], _nodes("mcu"),
                            {"gpio_link": "gpio"})


def test_resolve_non_hub_connection_rejected():
    with pytest.raises(ValueError, match="require a hub"):
        resolve_connections(["mcu.a <-> board.b"], _nodes("mcu", "board"), {})


def test_resolve_both_sides_hub_rejected():
    with pytest.raises(ValueError, match="both sides are hubs"):
        resolve_connections(["uart_link <-> uart_link"], _nodes("mcu"),
                            {"uart_link": "uart"})


def test_resolve_unknown_node_rejected():
    with pytest.raises(ValueError, match="unknown node"):
        resolve_connections(["ghost.usart1 <-> uart_link"], _nodes("mcu"),
                            {"uart_link": "uart"})


def test_resolve_non_renode_node_rejected():
    nodes = {"mcu": {"backend": "qemu"}}
    with pytest.raises(ValueError, match="not a renode node"):
        resolve_connections(["mcu.usart1 <-> uart_link"], nodes,
                            {"uart_link": "uart"})
