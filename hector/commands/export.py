# SPDX-License-Identifier: AGPL-3.0-or-later
"""`hector export` — generate the emulation files but, instead of running, print
the command that would run them.

Emits the `docker run ... renode ...` invocation (or the bare `renode ...` command
under --no-docker) for each matrix job, so you can inspect, copy, or wrap it.
"""

from .. import pipeline
from .base import COMMANDS, Command, add_common_arguments, add_simulation_arguments


@COMMANDS.register("export")
class ExportCommand(Command):
    name = "export"
    help = "Generate the files and print the run command instead of executing it."

    def add_arguments(self, parser):
        add_common_arguments(parser)
        add_simulation_arguments(parser)

    def execute(self, args):
        pipeline.apply_global_flags(args)
        config = pipeline.load_config_or_exit()
        cfg = pipeline.build_job_config(pipeline.action_export, config, args)
        return pipeline.execute_jobs(cfg, args)
