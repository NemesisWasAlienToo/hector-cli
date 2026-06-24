# SPDX-License-Identifier: AGPL-3.0-or-later
"""`hector init` — scaffold a new .hector.yaml in the current directory."""

from ..scaffold import scaffold_init
from .base import COMMANDS, Command


@COMMANDS.register("init")
class InitCommand(Command):
    name = "init"
    help = "Scaffold a new .hector.yaml in the current directory."

    def execute(self, args):
        scaffold_init()
        return 0
