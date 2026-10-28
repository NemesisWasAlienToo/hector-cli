"""Unit tests for hector.generator — the single place descriptors become .repl/.resc
text on disk. All string/file output is asserted directly; Renode is never launched."""

import os

import pytest

from hector.generator import (NodeDescriptor, PeripheralDef, build_repl_fragment,
                              collect_artifacts, finalize_commands, generate_emulation_resc,
                              generate_node_repl, repl_value, snapshot_resc,
                              write_inline_repl)


# ---- repl_value ----

@pytest.mark.parametrize("value,expected", [
    (True, "true"),
    (False, "false"),
    (5, "5"),
    (0x40, "64"),                    # ints render decimal
    ("0x40000000", "0x40000000"),    # hex literal string: unquoted
    ("gpioPortA", "gpioPortA"),      # identifier / peripheral ref: unquoted
    ("cortex-m3", '"cortex-m3"'),    # arbitrary string: quoted
    ([1, "gpioPortA"], "[1, gpioPortA]"),
])
def test_repl_value(value, expected):
    assert repl_value(value) == expected


# ---- build_repl_fragment ----

def test_fragment_head_only():
    assert build_repl_fragment("cpu", "CPU.CortexM") == "cpu: CPU.CortexM"


def test_fragment_with_registration_args_irqs():
    frag = build_repl_fragment(
        "usart2", "UART.STM32_UART", args={"frequency": 200000000},
        at="sysbus <0x40004400, +0x100>", irqs=["-> nvic@38"])
    assert frag.splitlines() == [
        "usart2: UART.STM32_UART @ sysbus <0x40004400, +0x100>",
        "    frequency: 200000000",
        "    -> nvic@38",
    ]


def test_fragment_init_block_is_indented():
    frag = build_repl_fragment("sysbus", "X", init="Tag a b\nApplySVD @x")
    assert "    init:" in frag
    assert "        Tag a b" in frag and "        ApplySVD @x" in frag


# ---- generate_node_repl / write_inline_repl ----

def test_generate_node_repl_writes_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    desc = NodeDescriptor(name="mcu", peripheral_defs=[
        PeripheralDef("led", "Miscellaneous.LED", at="gpioPortA 5", args={},
                      signals=[], init=None)])
    path = generate_node_repl(desc, job_index=1)
    assert path.endswith(os.path.join(".hector", "repl", "job_1_mcu.gen.repl"))
    body = open(path).read()
    assert "led: Miscellaneous.LED @ gpioPortA 5" in body


def test_generate_node_repl_returns_none_when_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert generate_node_repl(NodeDescriptor(name="empty"), job_index=1) is None


def test_generate_node_repl_emits_updating_entries_and_init(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    desc = NodeDescriptor(name="m", updating_entries=[("gpioPortA", "5 -> led@0")],
                          init="logLevel 3")
    body = open(generate_node_repl(desc, 2)).read()
    assert "gpioPortA:\n    5 -> led@0" in body
    assert "sysbus:\n    init:\n        logLevel 3" in body


def test_write_inline_repl_string(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = write_inline_repl("board", "cpu: CPU.CortexM @ sysbus\n    cpuType: \"m3\"", 1)
    assert path.endswith("job_1_board.inline.repl")
    assert open(path).read() == 'cpu: CPU.CortexM @ sysbus\n    cpuType: "m3"\n'


def test_write_inline_repl_list_is_joined(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = write_inline_repl("b", ["line1", "line2"], 1)
    assert open(path).read() == "line1\nline2\n"


# ---- finalize_commands ----

def test_finalize_prepends_generated_before_user_string():
    node = {"_gen_commands": ["attach a", "map b"], "commands": "showAnalyzer x"}
    finalize_commands({"m": node})
    assert node["commands"] == "attach a\nmap b\nshowAnalyzer x"


def test_finalize_prepends_generated_before_user_list():
    node = {"_gen_commands": ["gen"], "commands": ["u1", "u2"]}
    finalize_commands({"m": node})
    assert node["commands"] == ["gen", "u1", "u2"]


def test_finalize_generated_only():
    node = {"_gen_commands": ["only gen"]}
    finalize_commands({"m": node})
    assert node["commands"] == "only gen"


def test_finalize_noop_without_generated():
    node = {"commands": "keep"}
    finalize_commands({"m": node})
    assert node["commands"] == "keep"


# ---- generate_emulation_resc ----

def _one_machine(**extra):
    node = {"platform": ["board.repl"], "firmware": "fw.elf"}
    node.update(extra)
    return [("mcu", node)]


def test_resc_machine_block_order(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "job.resc"
    text = generate_emulation_resc(
        _one_machine(resc="sysbus Tag x", commands="showAnalyzer u"),
        hubs_registry={}, cross_connections=[], quantum=None,
        debug_config={}, output_filename=str(out))
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    order = [lines.index(x) for x in (
        'mach create "mcu"',
        "machine LoadPlatformDescription @board.repl",
        "sysbus LoadELF @fw.elf",
        "sysbus Tag x",
        "showAnalyzer u",
        "start")]
    assert order == sorted(order)          # strictly increasing => correct ordering
    assert out.read_text() == text


def test_resc_default_ends_with_start(tmp_path):
    out = tmp_path / "j.resc"
    text = generate_emulation_resc(_one_machine(), {}, [], None, {}, str(out))
    assert text.rstrip().endswith("start")


def test_resc_no_start_replaces_start_with_hint(tmp_path):
    out = tmp_path / "j.resc"
    text = generate_emulation_resc(_one_machine(), {}, [], None, {}, str(out),
                                   no_start=True)
    assert "\nstart" not in text
    assert "paused" in text.lower()


def test_resc_debug_block_halts_cpu(tmp_path):
    out = tmp_path / "j.resc"
    text = generate_emulation_resc(_one_machine(), {}, [], None,
                                   {"mcu": 3333}, str(out))
    assert "machine StartGdbServer 3333" in text
    assert "cpu IsHalted true" in text


def test_resc_quantum_and_emulation_setup(tmp_path):
    out = tmp_path / "j.resc"
    text = generate_emulation_resc(
        _one_machine(), {}, [], "0.0001", {}, str(out),
        emulation_setup=["i @mod.cs"])
    assert 'emulation SetGlobalQuantum "0.0001"' in text
    # emulation-level setup must precede the first machine block.
    assert text.index("i @mod.cs") < text.index('mach create "mcu"')


def test_resc_search_dir_is_the_first_line(tmp_path):
    # Relative @paths must resolve against the config's dir before anything loads.
    out = tmp_path / "j.resc"
    text = generate_emulation_resc(_one_machine(), {}, [], None, {}, str(out),
                                   emulation_setup=["i @mod.cs"], search_dir="/w/my board")
    assert text.splitlines()[:2] == ["path add @/w/my\\ board", "$PROJECT=@/w/my\\ board"]


def test_resc_without_search_dir_has_no_path_add(tmp_path):
    out = tmp_path / "j.resc"
    assert "path add" not in generate_emulation_resc(_one_machine(), {}, [], None, {}, str(out))


# ---- snapshot_resc ----

def test_snapshot_resc_loads_and_starts():
    text = snapshot_resc("/workspace/s.save")
    assert text.startswith("Load @/workspace/s.save")
    assert text.rstrip().endswith("start")


def test_snapshot_resc_no_start():
    text = snapshot_resc("/workspace/s.save", no_start=True)
    assert "start" not in text.split("\n")
    assert "paused" in text.lower()


def test_snapshot_resc_reopens_gdb_after_load():
    text = snapshot_resc("/workspace/s.save", debug_config={"mcu": 4444})
    # A GDB server is never part of saved state, so it must be (re)started post-Load.
    assert text.index("Load @") < text.index("StartGdbServer 4444")
    assert 'mach set "mcu"' in text


# ---- collect_artifacts ----

def test_collect_artifacts_resolves_against_base_dir(tmp_path, monkeypatch):
    # Config in board/: its 'artifacts:' globs resolve there, not against the cwd.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "board" / "build").mkdir(parents=True)
    (tmp_path / "board" / "build" / "fw.bin").write_text("x")
    (tmp_path / "board" / "uart.log").write_text("x")
    (tmp_path / "other.log").write_text("x")
    collected = collect_artifacts(["build/*.bin", "*.log"], "results", 1,
                                  base_dir=str(tmp_path / "board"))
    assert sorted(collected) == [
        os.path.join("results", "artifacts", "job_1", "board", "build", "fw.bin"),
        os.path.join("results", "artifacts", "job_1", "board", "uart.log")]


def test_snapshot_resc_replays_around_load():
    # Assemblies before Load; host bindings (not in the snapshot) recreated after it.
    text = snapshot_resc("/w/s.save", work_dir="/w", before_load=["i @/w/p.cs"],
                         after_load=['emulation CreateServerSocketTerminal 3456 "t"',
                                     'mach set "mcu"', "connector Connect sysbus.usart2 t"])
    lines = text.splitlines()
    assert lines[:2] == ["path add @/w", "$PROJECT=@/w"]
    assert lines.index("i @/w/p.cs") < lines.index("Load @/w/s.save") < lines.index(
        "connector Connect sysbus.usart2 t") < lines.index("start")
