# SPDX-License-Identifier: AGPL-3.0-or-later
"""`hector run` — boot the emulation interactively in the Renode monitor."""

from .. import pipeline
from .base import COMMANDS, Command, add_common_arguments, add_simulation_arguments


@COMMANDS.register("run")
class RunCommand(Command):
    name = "run"
    help = "Build the emulation and run it interactively in Renode."

    def add_arguments(self, parser):
        add_common_arguments(parser)
        add_simulation_arguments(parser)

    def execute(self, args):
        pipeline.apply_global_flags(args)

        # Convenience fast path: a snapshot + pinned version/image needs no .hector.yaml.
        if args.snapshot and (args.renode_version or args.renode_image):
            pipeline.snapshot_fastpath(args)
            return 0

        config = pipeline.load_config_or_exit()
        cfg = pipeline.build_job_config(pipeline.action_simulate, config, args)
        return pipeline.execute_jobs(cfg, args)
