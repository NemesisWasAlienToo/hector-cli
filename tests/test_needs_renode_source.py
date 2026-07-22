"""Unit tests for hector._needs_renode_source — the check whose miss hung Live View.

A config that builds a `renode-verilator` module (or interpolates ${RENODE_DIR}/${INTEGRATION_DIR})
must clone the Renode source; everything else must NOT (a wasted ~200 MB clone + build).
"""

from hector.pipeline import _needs_renode_source


def test_verilator_module_needs_source():
    cfg = {"modules": {"uartlite": {"kind": "renode-verilator", "source": "x"}}}
    assert _needs_renode_source(cfg) is True


def test_module_default_kind_is_verilator():
    assert _needs_renode_source({"modules": {"u": {"source": "x"}}}) is True


def test_csharp_module_does_not_need_source():
    assert _needs_renode_source({"modules": {"u": {"kind": "csharp", "source": "x.cs"}}}) is False


def test_renode_dir_interpolation_needs_source():
    assert _needs_renode_source({"machines": {"m": {"firmware": "${RENODE_DIR}/fw.elf"}}}) is True


def test_integration_dir_interpolation_needs_source():
    assert _needs_renode_source({"modules": {"u": {"source": "${INTEGRATION_DIR}/s"}}}) is True


def test_plain_machine_does_not_need_source():
    cfg = {"machines": {"blackpill": {"platform": ["platforms/cpus/stm32f103.repl"],
                                      "firmware": "https://example.com/fw.elf"}}}
    assert _needs_renode_source(cfg) is False


def test_empty_config_does_not_need_source():
    assert _needs_renode_source({}) is False
