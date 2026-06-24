# SPDX-License-Identifier: AGPL-3.0-or-later
"""`hector init` — scaffold a new .hector.yaml in the current directory."""

from ..scaffold import scaffold_init
from .base import COMMANDS, Command, add_config_file_argument


@COMMANDS.register("init")
class InitCommand(Command):
    name = "init"
    help = "Scaffold a new config file in the current directory."

    def add_arguments(self, parser):
        add_config_file_argument(parser)

    def execute(self, args):
        scaffold_init(args.file)
        return 0
