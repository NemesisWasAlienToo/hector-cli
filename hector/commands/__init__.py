# SPDX-License-Identifier: AGPL-3.0-or-later
"""hector's command surface: one `hector <name>` subcommand per module here.

Importing this package registers every command into COMMANDS; build_parser() then
wires them all into a single argparse parser. To add a command, create a module
(see run.py for the template) and add it to the import list below.
"""

import argparse

from ..core import TOOL_VERSION
from .base import COMMANDS, Command, add_common_arguments, add_simulation_arguments

# Importing each module runs its @COMMANDS.register(...) decorator.
from . import run, test, export, init, validate, clean  # noqa: E402,F401

__all__ = ["COMMANDS", "Command", "build_parser",
           "add_common_arguments", "add_simulation_arguments"]


def build_parser():
    """Assemble the top-level `hector` parser with one subparser per registered command."""
    parser = argparse.ArgumentParser(
        prog="hector",
        description="YAML-driven Renode + Verilator simulation orchestrator",
    )
    parser.add_argument("--version", action="version", version=f"hector {TOOL_VERSION}")

    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")
    for name in sorted(COMMANDS.keys()):
        cmd = COMMANDS.get(name)()      # the registry holds classes; instantiate
        sp = sub.add_parser(cmd.name, help=cmd.help, description=cmd.help)
        cmd.add_arguments(sp)
        sp.set_defaults(_command=cmd)
    return parser
