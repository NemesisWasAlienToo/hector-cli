"""Unit tests for hector.peripherals pure helpers: signal-line parsing and the
recursive gathering of peripheral-level connection blocks."""

from hector.peripherals import _gather_connections, _parse_repl_signals


# ---- _parse_repl_signals ----

def test_bare_source_becomes_arrow_target():
    assert _parse_repl_signals("nvic -> cpu@0") == {"nvic": ["-> cpu@0"]}


def test_named_signal_source():
    assert _parse_repl_signals("nvic.IRQ -> cpu@0") == {"nvic": ["IRQ -> cpu@0"]}


def test_range_source():
    assert _parse_repl_signals("gpioPortC[0-15] -> nvic@6") == {
        "gpioPortC": ["[0-15] -> nvic@6"]}


def test_pin_source():
    assert _parse_repl_signals("timer1@0 -> gpioPortA#08@01") == {
        "timer1": ["0 -> gpioPortA#08@01"]}


def test_destination_preserved_verbatim():
    # Receiver qualifiers (#index, @pin) on the destination must pass through untouched.
    out = _parse_repl_signals("timer2@1 -> gpioPortB#03@02")
    assert out == {"timer2": ["1 -> gpioPortB#03@02"]}


def test_multiple_lines_accumulate_per_peripheral():
    out = _parse_repl_signals("gpioA[0-7] -> exti@0\ngpioA[8-15] -> exti@1")
    assert out == {"gpioA": ["[0-7] -> exti@0", "[8-15] -> exti@1"]}


def test_hash_on_source_is_flagged_and_skipped():
    # '#index' is a receiver-only qualifier; on the source side it is invalid, so skip.
    assert _parse_repl_signals("gpioA#3 -> exti@0") == {}


def test_line_without_arrow_skipped():
    assert _parse_repl_signals("gpioA cpu") == {}


def test_blank_and_comment_lines_ignored():
    assert _parse_repl_signals("\n# comment\n  \nnvic -> cpu@0") == {"nvic": ["-> cpu@0"]}


def test_empty_input():
    assert _parse_repl_signals("") == {}
    assert _parse_repl_signals(None) == {}


# ---- _gather_connections ----

def test_gather_flat_string_block():
    peripherals = {"mcu": {"connections": "a -> b\nc -> d"}}
    assert _gather_connections(peripherals) == "a -> b\nc -> d"


def test_gather_list_block_is_joined():
    peripherals = {"mcu": {"connections": ["a -> b", "c -> d"]}}
    assert _gather_connections(peripherals) == "a -> b\nc -> d"


def test_gather_recurses_into_child_peripherals():
    peripherals = {
        "grp": {
            "connections": "top -> x",
            "peripherals": {"child": {"connections": "inner -> y"}},
        }
    }
    out = _gather_connections(peripherals)
    assert "top -> x" in out and "inner -> y" in out


def test_gather_none_when_no_connections():
    assert _gather_connections({"mcu": {"type": "X"}}) == ""
    assert _gather_connections(None) == ""
