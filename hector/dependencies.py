# SPDX-License-Identifier: AGPL-3.0-or-later
"""Managed clones of Renode and the verilator integration, pinned to the `renode:` version."""

import os

from .core import (ARTIFACTS_DIR, INTEGRATION_REPO_URL, RENODE_REPO_URL,
                   register_dependency_mount, run_shell)


def prepare_dependencies(git_tag, renode_dir=None, integration_dir=None):
    """Ensure the Renode source and verilator-integration checkouts exist, returning
    their paths. Each location defaults to .hector/ but can be overridden (e.g. a cached
    or shared checkout): an existing directory is reused as-is (no clone), a missing one
    is cloned into. Only called when the run actually needs the source (see callers)."""
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    renode_dir = renode_dir or os.path.join(ARTIFACTS_DIR, "renode")
    integration_dir = integration_dir or os.path.join(ARTIFACTS_DIR, "renode-verilator-integration")

    if not os.path.isdir(renode_dir):
        print(f"[DEPS] Cloning Renode @ {git_tag} → {renode_dir} ...")
        run_shell(f'git clone --depth 1 --branch "{git_tag}" --recurse-submodules '
                  f'--shallow-submodules "{RENODE_REPO_URL}" "{renode_dir}"')
    else:
        print(f"[DEPS] Renode present at {renode_dir} (delete to refresh).")

    if not os.path.isdir(integration_dir):
        print(f"[DEPS] Cloning renode-verilator-integration → {integration_dir} ...")
        run_shell(f'git clone --recurse-submodules "{INTEGRATION_REPO_URL}" "{integration_dir}"')
    else:
        print(f"[DEPS] Integration present at {integration_dir} (delete to refresh).")

    return renode_dir, integration_dir


def framework_vars(renode_dir, integration_dir):
    """Interpolation variables exposing the checkouts as container paths, bind-mounting
    any that live outside the workspace so containers reach them at the same path."""
    return {
        "RENODE_DIR": register_dependency_mount(renode_dir),
        "INTEGRATION_DIR": register_dependency_mount(integration_dir),
    }