# SPDX-License-Identifier: AGPL-3.0-or-later
"""Command framework: a tiny registry + base class so each subcommand is a
self-contained module.

To add a command, drop a module in this package that subclasses Command, fills in
name/help, declares its flags in add_arguments(), does its work in execute(), and
registers itself with @COMMANDS.register("<name>"). Import it from __init__.py and
`hector <name>` exists — no central switch to edit.
"""

from ..core import Registry

COMMANDS = Registry("command")


class Command:
    """One `hector <name>` subcommand."""
    name = ""          # the subcommand word, e.g. "run"
    help = ""          # one-line description shown in `hector --help`

    def add_arguments(self, parser):
        """Declare this command's flags on its argparse subparser."""

    def execute(self, args):
        """Do the work. Return a process exit code (0 = success, falsy == 0)."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Reusable flag groups (shared so each command's surface stays consistent)
# ---------------------------------------------------------------------------

def add_common_arguments(parser):
    """Flags shared by the config-driven commands (run / test / export): they all
    read .hector.yaml, pin a Renode version, expand the matrix, and collect output."""
    parser.add_argument(
        "--set", action="append", metavar="KEY=VALUE", dest="set_args",
        help="Override a config argument. Repeatable. Takes precedence over env vars "
             "and config defaults. Example: --set BIN=fw.elf --set BOARD=nucleo.",
    )
    parser.add_argument(
        "--renode-version", metavar="VERSION", dest="renode_version",
        help="Renode version to use (e.g. 1.16.1). Overrides renode_version from "
             ".hector.yaml.",
    )
    parser.add_argument(
        "--renode-dir", metavar="PATH", dest="renode_dir", default=None,
        help="Location of the Renode source checkout (only fetched when a config builds "
             "'modules:' or uses ${RENODE_DIR}). Reused if it exists, cloned there if "
             "not. Default: .hector/renode. Point it at a cache to avoid re-cloning.",
    )
    parser.add_argument(
        "--renode-integration-dir", metavar="PATH", dest="renode_integration_dir",
        default=None,
        help="Location of the renode-verilator-integration checkout (see --renode-dir). "
             "Default: .hector/renode-verilator-integration.",
    )
    parser.add_argument(
        "--output", metavar="DIR", default="results",
        help="Directory for test results, artifacts, and simulation output files "
             "(default: results).",
    )
    parser.add_argument(
        "--artifacts", action="append", metavar="GLOB", dest="artifacts",
        help="Glob pattern(s) for output files to collect into <output>/artifacts/ "
             "after each job. Repeatable. Overrides the top-level 'artifacts:' in "
             ".hector.yaml when given.",
    )
    parser.add_argument(
        "--gather-execution-metrics", action="append", nargs="?", const=None,
        metavar="NODE", dest="gather_execution_metrics",
        help="Enable Renode's CPU execution profiler. With no argument, enables it for "
             "all machines. Pass a node name to target one machine. Repeatable. Writes "
             "one binary file per node to the output directory.",
    )
    parser.add_argument(
        "--job", metavar="KEY=VALUE",
        help="Select the matrix combination to run, e.g. --job BOARD=stm32f7 "
             "(repeat keys with commas: --job BOARD=stm32f7,FW=release.elf). Required "
             "when a matrix is defined — hector runs one combination per invocation and "
             "does not expand the matrix itself (that's the CI's job).",
    )
    docker_mode = parser.add_mutually_exclusive_group()
    docker_mode.add_argument(
        "--no-docker", action="store_true", dest="no_docker",
        help="Call the locally installed renode / renode-test binaries directly "
             "instead of launching a Docker container.",
    )
    docker_mode.add_argument(
        "--workspace-mount", metavar="PATH", dest="workspace_mount", default=None,
        help="Container path where the project root is bind-mounted "
             "(default: same absolute path as on the host).",
    )


def add_simulation_arguments(parser):
    """Flags shared by commands that assemble/boot a single emulation (run / export)."""
    parser.add_argument(
        "--debug", action="append", metavar="NODE:PORT",
        help="Halt the CPU and open a GDB server for each named node. Repeatable: "
             "--debug boardA:3333 --debug boardB:3334.",
    )
    parser.add_argument(
        "--snapshot", metavar="PATH", dest="snapshot",
        help="Load a Renode snapshot instead of booting from the generated resc.",
    )
    parser.add_argument(
        "--renode-args", metavar="ARGS", dest="renode_args", default="",
        help="Extra arguments passed verbatim to Renode "
             "(e.g. --renode-args '--console --hide-log').",
    )
