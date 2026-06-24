# SPDX-License-Identifier: AGPL-3.0-or-later
"""`hector validate` — check .hector.yaml without running anything; exit 1 on errors."""

from .. import pipeline
from .base import COMMANDS, Command, add_config_file_argument


@COMMANDS.register("validate")
class ValidateCommand(Command):
    name = "validate"
    help = "Validate the config file without running anything; exit 1 on errors."

    def add_arguments(self, parser):
        add_config_file_argument(parser)

    def execute(self, args):
        pipeline.apply_global_flags(args)   # picks up -f/--file
        # _run_validate prints a report and exits with the right code itself.
        pipeline._run_validate()
