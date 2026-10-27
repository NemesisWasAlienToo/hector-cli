# SPDX-License-Identifier: AGPL-3.0-or-later
"""Project scaffolding: `hector init`."""

import os
import sys

_TEMPLATE = """\
version: "0.1"
renode:
  image: "{renode_version}"

# arguments: scalar defaults, each overridable by an env var of the same name.
arguments:
  BIN: firmware.elf

machines:
  {board}:
    platform:
      - platforms/boards/{board}.repl
    firmware: ${{BIN}}

# Uncomment to capture UART output to a file:
# mappings: |
#   {board}.usart2 -> file:results/uart.log

# Uncomment to add tests (run with: hector test):
# tests:
#   - name: Firmware boots
#     type: robot
#     script: |
#       Create Terminal Tester    sysbus.usart2
#       Wait For Line On Uart     Ready    timeout=30
"""

_PLATFORMS_NOTE = """\
[INIT] Next steps:
  1. Add your .repl platform file to  platforms/boards/{board}.repl
  2. Set BIN to your firmware path, or override at runtime:  BIN=path/to/fw.elf hector run
  3. Run the simulation:  hector run
  4. Run tests:           hector test
  5. Debug a machine:     hector run --debug {board}:3333
"""


def scaffold_init(target=".hector.yaml"):
    """Interactively create a starter config in the current directory (default
    name .hector.yaml; override via -f/--file)."""
    if os.path.exists(target):
        print(f"[INIT] {target} already exists — not overwriting.")
        print("[INIT] Delete or rename it, then run 'hector init' again.")
        sys.exit(1)

    print("Hector project initialisation")
    print("  Press Enter to accept the default shown in [brackets].\n")

    board = _prompt("  Board / machine name", "stm32f4_discovery")
    renode_version = _prompt("  Renode version   ", "1.16.1")

    content = _TEMPLATE.format(board=board, renode_version=renode_version)
    with open(target, "w") as fh:
        fh.write(content)

    os.makedirs(os.path.join("platforms", "boards"), exist_ok=True)
    os.makedirs("results", exist_ok=True)

    print(f"\n[INIT] Created {target}")
    print(_PLATFORMS_NOTE.format(board=board))


def _prompt(label: str, default: str) -> str:
    try:
        value = input(f"{label} [{default}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return value or default
