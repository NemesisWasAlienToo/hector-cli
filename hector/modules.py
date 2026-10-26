# SPDX-License-Identifier: AGPL-3.0-or-later
"""
MODULE_KINDS — how a module type is built into a loadable artifact (.so or .dll).

Register a builder `(module_name, module_config, BuildContext) -> artifact_host_path`:
    @MODULE_KINDS.register("my-kind")
    def build_my_kind(module_name, cfg, ctx):
        return path_to_artifact
"""

import glob
import os
import shutil
from dataclasses import dataclass

from .core import (ARTIFACTS_DIR, LIBOPENLIBM_NAME, Registry,
                   container_path_for, from_config, host_uid_gid, split_host_container,
                   to_container_path)
from .docker import run_build

MODULE_KINDS = Registry("module kind")


@dataclass
class BuildContext:
    renode_dir_container: str
    integration_dir_host: str
    image: str


def _libopenlibm_flag(integration_dir_host):
    libm = os.path.join(integration_dir_host, "lib", LIBOPENLIBM_NAME)
    if os.path.isfile(libm):
        return f'-DLIBOPENLIBM="{container_path_for(libm)}"'
    print(f"  [!] {LIBOPENLIBM_NAME} not found at {libm}; skipping -DLIBOPENLIBM "
          "(add it via cmake_flags if your build needs it).")
    return ""


@MODULE_KINDS.register("renode-verilator")
def build_renode_verilator(module_name, module_config, ctx):
    """Build a verilated co-simulation peripheral into a .so, inside the Renode image."""
    if not module_config.get("type"):
        raise ValueError(f"Module '{module_name}' is missing required 'type' (its Renode class).")
    source = module_config.get("source")
    if not source:
        raise ValueError(f"Module '{module_name}' is missing required 'source'.")

    source_host, source_container = split_host_container(from_config(source))
    if not os.path.isdir(source_host):
        raise FileNotFoundError(f"Module '{module_name}': source dir not found: {source} ({source_host})")

    build_host = os.path.join(ARTIFACTS_DIR, "build", "modules", module_name)
    os.makedirs(build_host, exist_ok=True)
    build_container = to_container_path(build_host)
    cmake_flags = module_config.get("cmake_flags", "")
    auto_flags = _libopenlibm_flag(ctx.integration_dir_host)
    # chown the build output back to the host user (the build runs as root). No host
    # uid on Windows → skip it; Docker Desktop maps bind-mount ownership itself.
    _ids = host_uid_gid()
    chown = f'chown -R {_ids[0]}:{_ids[1]} "{build_container}"\n' if _ids else ""

    print(f"\n[MODULE] Building '{module_name}' ({module_config['type']}) in {ctx.image}")
    print(f"         source: {source}")

    run_build(
        "set -e\n"
        "export DEBIAN_FRONTEND=noninteractive\n"
        "apt-get update\n"
        "apt-get install -y --no-install-recommends build-essential cmake verilator\n"
        f'cmake -S "{source_container}" -B "{build_container}" '
        f'-DUSER_RENODE_DIR="{ctx.renode_dir_container}" {auto_flags} {cmake_flags}\n'
        f'cmake --build "{build_container}"\n'
        f'{chown}',
        ctx.image,
    )

    so_files = glob.glob(os.path.join(build_host, "**", "*.so"), recursive=True)
    if not so_files:
        raise RuntimeError(f"Module '{module_name}' produced no .so in {build_host}.")
    if len(so_files) > 1:
        raise RuntimeError(f"Module '{module_name}' produced multiple .so files: {so_files}.")
    print(f"  -> {so_files[0]}")
    return so_files[0]


# Renode DLLs bundled in its own installation — filter these out when locating
# the user's output DLL after a dotnet build.
_RENODE_DLL_PREFIXES = (
    "Antmicro.", "Mono.", "System.", "Microsoft.", "mscorlib",
    "netstandard", "IronPython", "FasterReflection",
)


@MODULE_KINDS.register("csharp")
def build_csharp(module_name, module_config, ctx):
    """Build or locate a C# Renode peripheral plugin.

    `source` may be:
      - a raw ``.cs`` file        → Renode compiles it at load time (its bundled Roslyn;
                                     no .NET SDK needed). Simplest and version-matched —
                                     what most peripherals should use.
      - a pre-built ``.dll``      → used as-is.
      - a directory with a ``.csproj`` → built with ``dotnet``/``msbuild`` in the
                                     container (needs an image that ships the .NET SDK;
                                     the stock Renode image has only the runtime).
    The artifact is loaded at emulation scope via ``i @<path>``; one import covers all
    instances.
    """
    if not module_config.get("type"):
        raise ValueError(f"Module '{module_name}' is missing required 'type' (the C# class name).")
    source = module_config.get("source")
    if not source:
        raise ValueError(f"Module '{module_name}' is missing required 'source'.")

    source_host, _ = split_host_container(from_config(source))

    # ---- raw .cs: Renode compiles it at load time (bundled Roslyn) — no SDK, no build ----
    if source_host.endswith(".cs"):
        if not os.path.isfile(source_host):
            raise FileNotFoundError(f"Module '{module_name}': source not found: {source} ({source_host})")
        print(f"\n[MODULE] C# '{module_name}' ({module_config['type']}) — compiled by Renode at load")
        print(f"         source: {source}")
        return source_host

    # ---- pre-built DLL: use as-is ----
    if source_host.endswith(".dll"):
        if not os.path.isfile(source_host):
            raise FileNotFoundError(f"Module '{module_name}': DLL not found: {source} ({source_host})")
        print(f"\n[MODULE] C# '{module_name}' ({module_config['type']}) using pre-built DLL")
        print(f"         source: {source}")
        return source_host

    # ---- build from source ----
    if not os.path.isdir(source_host):
        raise FileNotFoundError(
            f"Module '{module_name}': source not found: {source} ({source_host})\n"
            "  Provide a .cs file (Renode compiles it at load), a directory with a .csproj, "
            "or a pre-built .dll."
        )

    source_container = to_container_path(source_host)
    build_host = os.path.join(ARTIFACTS_DIR, "build", "modules", module_name)
    os.makedirs(build_host, exist_ok=True)
    build_container = to_container_path(build_host)
    # chown the build output back to the host user (the build runs as root). No host
    # uid on Windows → skip it; Docker Desktop maps bind-mount ownership itself.
    _ids = host_uid_gid()
    chown = f'chown -R {_ids[0]}:{_ids[1]} "{build_container}"\n' if _ids else ""

    print(f"\n[MODULE] Building C# '{module_name}' ({module_config['type']}) in {ctx.image}")
    print(f"         source: {source}")

    run_build(
        "set -e\n"
        # Renode's official image ships Mono; dotnet may also be present.
        # Try dotnet first (produces a self-contained output), fall back to msbuild/xbuild.
        f'if command -v dotnet >/dev/null 2>&1; then\n'
        f'  dotnet build "{source_container}" -o "{build_container}" -c Release\n'
        f'elif command -v msbuild >/dev/null 2>&1; then\n'
        f'  msbuild "{source_container}" /p:OutputPath="{build_container}" /p:Configuration=Release\n'
        f'else\n'
        f'  echo "[ERROR] Neither dotnet nor msbuild found in container {ctx.image}"; exit 1\n'
        f'fi\n'
        f'{chown}',
        ctx.image,
    )

    # Collect DLLs, excluding Renode/framework assemblies
    all_dlls = glob.glob(os.path.join(build_host, "**", "*.dll"), recursive=True)
    user_dlls = [
        f for f in all_dlls
        if not any(os.path.basename(f).startswith(p) for p in _RENODE_DLL_PREFIXES)
    ]

    if not user_dlls:
        raise RuntimeError(
            f"Module '{module_name}': no user DLL found in {build_host}.\n"
            f"  All .dll files found: {[os.path.basename(f) for f in all_dlls]}"
        )
    if len(user_dlls) > 1:
        # Try to pick the one whose name matches the module or the last path component of source
        stem = os.path.basename(source_host)
        candidates = [f for f in user_dlls
                      if module_name.lower() in os.path.basename(f).lower()
                      or stem.lower() in os.path.basename(f).lower()]
        if len(candidates) == 1:
            user_dlls = candidates
        else:
            raise RuntimeError(
                f"Module '{module_name}': multiple user DLLs found — cannot determine which "
                f"to use: {[os.path.basename(f) for f in user_dlls]}.\n"
                f"  Rename your project output or point 'source' directly at the .dll."
            )

    print(f"  -> {user_dlls[0]}")
    return user_dlls[0]


def build_modules(modules_cfg, ctx):
    """Build every declared module via its registered kind.

    Returns {module_name: {'type': renode_class, 'artifact_host': path, 'artifact_type': 'so'|'dll'}}
    """
    registry = {}
    for name, cfg in (modules_cfg or {}).items():
        kind = cfg.get("kind", "renode-verilator")
        builder = MODULE_KINDS.get(kind)
        artifact_host = builder(name, cfg, ctx)
        # csharp modules (raw .cs, .csproj or pre-built .dll) load via `i @<path>`;
        # renode-verilator modules produce a co-simulation .so.
        artifact_type = "dll" if kind == "csharp" else "so"
        registry[name] = {
            "type": cfg.get("type"),
            "artifact_host": artifact_host,
            "artifact_type": artifact_type,
        }
    return registry


def materialize_instance_so(node_name, instance, module_so_host):
    """Copy a module's .so to a per-instance file so each instance gets a distinct inode
    (and therefore independent simulation state when loaded)."""
    inst_dir = os.path.join(ARTIFACTS_DIR, "build", "instances")
    os.makedirs(inst_dir, exist_ok=True)
    dest = os.path.join(inst_dir, f"{node_name}__{instance}.so")
    shutil.copy2(module_so_host, dest)
    return dest
