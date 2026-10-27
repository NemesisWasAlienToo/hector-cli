# SPDX-License-Identifier: AGPL-3.0-or-later
"""`hector prepare` — run only the `prepare:` steps; exit 1 if one fails.

For when something else starts the emulation, e.g. a CI's live session built on
`hector export`, which never runs prepare steps itself.
"""

from .. import pipeline
from .base import COMMANDS, Command, add_common_arguments


@COMMANDS.register("prepare")
class PrepareCommand(Command):
    name = "prepare"
    help = "Run only the 'prepare:' steps (no emulation, no tests); exit 1 on failure."

    def add_arguments(self, parser):
        add_common_arguments(parser)

    def execute(self, args):
        pipeline.apply_global_flags(args)
        config = pipeline.load_config_or_exit()
        cfg = pipeline.build_job_config(pipeline.action_prepare, config, args)
        return pipeline.execute_jobs(cfg, args)
