"""Unit tests for hector.core text helpers: interpolate, as_lines, parse_endpoint."""

import pytest

from hector.core import as_lines, interpolate, parse_endpoint


# ---- interpolate ----

def test_interpolate_simple_and_unknown_kept():
    ctx = {"BIN": "fw.elf"}
    assert interpolate("load ${BIN}", ctx) == "load fw.elf"
    # An undefined variable is left verbatim (not blanked) so the miss is visible.
    assert interpolate("${MISSING}", ctx) == "${MISSING}"


def test_interpolate_multiple_vars():
    ctx = {"A": "1", "B": "2"}
    assert interpolate("${A}-${B}-${A}", ctx) == "1-2-1"


def test_interpolate_recurses_into_dict_and_list():
    ctx = {"X": "v"}
    data = {"k": ["${X}", {"n": "${X}"}], "plain": 5}
    assert interpolate(data, ctx) == {"k": ["v", {"n": "v"}], "plain": 5}


def test_interpolate_non_string_passthrough():
    assert interpolate(42, {}) == 42
    assert interpolate(None, {}) is None
    assert interpolate(True, {}) is True


# ---- as_lines ----

def test_as_lines_block_string_drops_blanks_and_comments():
    text = "a -> b\n\n# a comment\n  c -> d  \n"
    assert as_lines(text) == ["a -> b", "c -> d"]


def test_as_lines_accepts_list_and_coerces():
    assert as_lines(["x", 3, "  # skip", "y"]) == ["x", "3", "y"]


def test_as_lines_empty():
    assert as_lines(None) == []
    assert as_lines("") == []
    assert as_lines([]) == []


# ---- parse_endpoint ----

def test_parse_endpoint_self():
    ep = parse_endpoint("uart_link")
    assert ep["kind"] == "self" and ep["node"] == "uart_link" and ep["name"] == "uart_link"


def test_parse_endpoint_plain():
    ep = parse_endpoint("mcu.usart1")
    assert ep["kind"] == "plain" and ep["node"] == "mcu" and ep["name"] == "usart1"


def test_parse_endpoint_pin_decimal_and_hex():
    dec = parse_endpoint("board.gpioPortC@13")
    assert dec["kind"] == "pin" and dec["name"] == "gpioPortC" and dec["pin"] == 13
    hexed = parse_endpoint("board.gpio@0x1F")
    assert hexed["kind"] == "pin" and hexed["pin"] == 0x1F


def test_parse_endpoint_signal():
    ep = parse_endpoint("mcu.nvic.IRQ")
    assert ep["kind"] == "signal" and ep["node"] == "mcu"
    assert ep["periph"] == "nvic" and ep["signal"] == "IRQ"


def test_parse_endpoint_unparseable_raises():
    with pytest.raises(ValueError, match="Could not parse endpoint"):
        parse_endpoint("mcu.a.b.c.d")
