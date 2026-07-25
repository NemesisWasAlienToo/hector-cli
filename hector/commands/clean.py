# SPDX-License-Identifier: AGPL-3.0-or-later
"""`hector clean` — remove the files hector generates (the .hector/ build artifacts
and the results directory), so a project can be reset to a pristine checkout."""

from .. import pipeline
from .base import COMMANDS, Command


@COMMANDS.register("clean")
class CleanCommand(Command):
    name = "clean"
    help = "Remove generated files (.hector/ build outputs and the results directory)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output", metavar="DIR", default="results",
            help="Results directory to remove (default: results). Match the --output "
                 "you ran with if you used a custom one.",
        )
        parser.add_argument(
            "--all", action="store_true", dest="all",
            help="Also remove the cached Renode / verilator-integration source "
                 "checkouts under .hector/ — a full re-clone (~200 MB) happens on the "
                 "next build. Omit to keep them for fast iteration.",
        )
        parser.add_argument(
            "-n", "--dry-run", action="store_true", dest="dry_run",
            help="List what would be removed without deleting anything.",
        )

    def execute(self, args):
        return pipeline.run_clean(output_dir=args.output,
                                  include_renode=args.all,
                                  dry_run=args.dry_run)
