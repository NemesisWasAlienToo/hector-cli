# SPDX-License-Identifier: AGPL-3.0-or-later
"""`hector validate` — check .hector.yaml without running anything; exit 1 on errors."""

from .. import pipeline
from .base import COMMANDS, Command


@COMMANDS.register("validate")
class ValidateCommand(Command):
    name = "validate"
    help = "Validate .hector.yaml without running anything; exit 1 on errors."

    def execute(self, args):
        # _run_validate prints a report and exits with the right code itself.
        pipeline._run_validate()
