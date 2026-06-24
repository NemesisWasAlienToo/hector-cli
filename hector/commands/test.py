# SPDX-License-Identifier: AGPL-3.0-or-later
"""`hector test` — run the `tests:` section; exit 1 on any failure."""

from .. import pipeline
from .base import COMMANDS, Command, add_common_arguments


@COMMANDS.register("test")
class TestCommand(Command):
    name = "test"
    help = "Run the 'tests:' section against the generated emulation; exit 1 on failure."

    def add_arguments(self, parser):
        add_common_arguments(parser)
        parser.add_argument(
            "--test-file", metavar="FILE", dest="test_file",
            help="Run a specific .robot file against the generated resc instead of the "
                 "YAML-defined tests. ${RESC} expands to the resc path.",
        )
        parser.add_argument(
            "--test-name", metavar="NAME", dest="test_name", action="append",
            help="Run only tests whose name contains NAME. Repeatable.",
        )
        parser.add_argument(
            "--reporters", action="append", metavar="REPORTER", dest="reporters",
            help="Reporter to call after tests. Repeatable (default: junit). "
                 "Example: --reporters junit --reporters json.",
        )
        parser.add_argument(
            "--live", action="store_true",
            help="Stream bash test output line-by-line and run robot tests verbosely.",
        )
        parser.add_argument(
            "--snapshot", metavar="PATH", dest="snapshot",
            help="Load a Renode snapshot at the start of every test instead of booting "
                 "from the resc. Overrides per-test 'snapshot:' fields.",
        )
        parser.add_argument(
            "--renode-test-args", metavar="ARGS", dest="renode_test_args", default="",
            help="Extra arguments passed verbatim to renode-test "
                 "(e.g. --renode-test-args '--loglevel DEBUG').",
        )
        parser.add_argument(
            "--fail-fast", action="store_true", dest="fail_fast",
            help="Stop after the first failing test instead of running them all.",
        )

    def execute(self, args):
        pipeline.apply_global_flags(args)
        config = pipeline.load_config_or_exit()
        cfg = pipeline.build_job_config(pipeline.action_test, config, args, test_mode=True)
        return pipeline.execute_jobs(cfg, args)
