# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Thin wrappers around `docker run` for the things we launch in the container:
module builds, interactive Renode simulation, renode-test runs, and the
interactive robot REPL. Centralising them here keeps the mount/flag
boilerplate in one place.
"""

import os
import subprocess

from . import core
from .core import to_container_path


def _xdisplay_args():
    xauth = os.environ.get("XAUTHORITY", f"{os.environ.get('HOME')}/.Xauthority")
    display = os.environ.get("DISPLAY", ":0")
    # Pin XAUTHORITY explicitly so X auth still resolves when the container runs as the
    # host UID (see _user_flags) rather than the image's baked-in user with HOME set.
    return ["-e", f"DISPLAY={display}", "-e", "XAUTHORITY=/home/developer/.Xauthority",
            "-v", f"{xauth}:/home/developer/.Xauthority"]


def _user_flags():
    """Run the container as the host user, so files it writes into the bind-mounted
    workspace are owned by them on the host — not root. Used by the shell/build and
    renode-test containers.

    Placed BEFORE _runtime_flags at the renode call sites: docker honours the last
    `-u`, so a mapping that legitimately needs root (e.g. a tap device, via
    runtime.root) still wins. The module-build container (run_build) is the one
    exception — it needs root for apt-get and chowns its artifacts back itself."""
    return ["-u", f"{os.getuid()}:{os.getgid()}"]


def _workspace_mount():
    return ["-v", f"{os.getcwd()}:{core.WORKSPACE_MOUNT}", "-w", core.WORKSPACE_MOUNT]


def _extra_mounts():
    """Bind-mount out-of-tree dependency dirs (e.g. a shared Renode source cache) 1:1, so
    containers reach them at the same path they have on the host. Empty for the common case."""
    args = []
    for d in core.EXTRA_MOUNTS:
        args += ["-v", f"{d}:{d}"]
    return args


def _runtime_flags(runtime):
    """Map aggregated RuntimeOptions (capabilities/devices/root, declared by mappings,
    hubs, modules) to `docker run` flags.

    A requested --device is dropped if absent on the host so `docker run` never fails;
    and if devices were requested but none exist, no flags are applied at all (e.g. a
    tap on a host without /dev/net/tun runs as the normal user in dummy mode rather than
    needlessly as root)."""
    if not runtime:
        return []
    present = [d for d in sorted(runtime.devices) if os.path.exists(d)]
    if runtime.devices and not present:
        return []
    flags = []
    if runtime.root:
        flags += ["-u", "0:0"]
    for cap in sorted(runtime.capabilities):
        flags += ["--cap-add", cap]
    for dev in present:
        flags += ["--device", dev]
    return flags


def run_build(script, image):
    """Run a build script in the container as root (for apt-get + cmake)."""
    if core.NO_DOCKER:
        subprocess.run(["bash", "-c", script], check=True)
        return
    subprocess.run(
        ["docker", "run", "--rm", "-u", "0:0",
         *_workspace_mount(), *_extra_mounts(), image, "bash", "-c", script],
        check=True,
    )


def resolve_shell_image(item, default_image, label="shell"):
    """Decide which image a shell step/test runs in, and log the decision.

    - explicit ``image:``            → use it
    - none                           → ``default_image`` (the run's renode image), logged
                                       so the user sees the fallback
    - under ``--no-docker``          → the image is irrelevant (the step runs on the host);
                                       warn if one was set explicitly, since it's ignored

    Returns the image string. Under --no-docker run_in_container ignores it, so the value
    only matters for display there."""
    image = item.get("image")
    name = item.get("name") or label
    if core.NO_DOCKER:
        if image:
            print(f"[WARN] --no-docker: image '{image}' for '{name}' is ignored; "
                  "running on the host.")
        return image or default_image
    if not image:
        print(f"[INFO] '{name}': no image set; using the default image '{default_image}'.")
    return image or default_image


def run_in_container(script, image, live=False):
    """Run a shell script with the project bind-mounted at the workspace path, returning
    (output, passed); streams when live=True. `set -ex` makes commands echo and the run
    fail on the first error.

    Backs the `shell` test type and the `build:` steps. Normally a one-off container of
    `image`; under --no-docker the script runs directly on the host (the image is moot)."""
    if core.NO_DOCKER:
        cmd = ["bash", "-c", f"set -ex\n{script}"]
    else:
        cmd = ["docker", "run", "--rm", *_workspace_mount(), *_extra_mounts(),
               *_user_flags(), image, "sh", "-c", f"set -ex\n{script}"]
    if live:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True)
        lines = []
        for line in proc.stdout:
            print(line, end="", flush=True)
            lines.append(line)
        proc.wait()
        return "".join(lines), proc.returncode == 0
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.stdout:
        print(proc.stdout, end="")
    return proc.stdout, proc.returncode == 0


def build_renode_argv(resc_filename, image, ports=None, extra_args=None, runtime=None):
    """Build the exact argv that would run an emulation resc — the local `renode`
    invocation under --no-docker, otherwise the full `docker run ... renode` command.

    Returning the command (instead of running it) is what lets the `export` command
    print it verbatim and keeps run_renode a one-liner around this builder.
    runtime: aggregated RuntimeOptions whose docker flags (caps/devices/root) are added."""
    if core.NO_DOCKER:
        return ["renode", resc_filename] + (extra_args or [])
    cmd = ["docker", "run", "-it", "--rm", *_xdisplay_args(), "--net=host",
           *_workspace_mount(), *_extra_mounts(), *_user_flags(), *_runtime_flags(runtime)]
    for port in (ports or []):
        cmd += ["-p", f"{port}:{port}"]
    cmd += [image, "renode", resc_filename] + (extra_args or [])
    return cmd


def run_renode(resc_filename, image, ports=None, extra_args=None, output_dir="results", runtime=None):
    """Run an emulation resc interactively. In debug mode, expose GDB ports.
    runtime: aggregated RuntimeOptions whose docker flags (caps/devices/root) are added."""
    if not core.NO_DOCKER:
        os.makedirs(os.path.join(os.getcwd(), output_dir), exist_ok=True)
    subprocess.run(build_renode_argv(resc_filename, image, ports, extra_args, runtime))


def run_renode_test(robot_file_host, image, results_dir_host,
                    resc_host_path=None, extra_args=None, interactive=False, runtime=None):
    """Run a .robot file with renode-test in the container. Returns True on pass.

    resc_host_path: passed as --variable RESC:<path> so .robot files can load
    the generated emulation script via ${RESC}.
    extra_args: optional list of additional flags forwarded verbatim to renode-test.
    interactive: attach stdin/tty and add --net=host (useful with Pause Execution
    or when TCP ports need to be reachable from the host during the test).
    """
    os.makedirs(results_dir_host, exist_ok=True)
    if core.NO_DOCKER:
        cmd = ["renode-test", robot_file_host, "-r", results_dir_host]
        if resc_host_path:
            cmd += ["--variable", f"RESC:{resc_host_path}"]
        if extra_args:
            cmd += extra_args
        result = subprocess.run(cmd)
        return result.returncode == 0
    flags = ["-it"] if interactive else []
    net = ["--net=host"] if interactive else []
    display = _xdisplay_args() if interactive else []
    cmd = ["docker", "run", "--rm", *flags, *net, *display,
           *_workspace_mount(), *_extra_mounts(), *_user_flags(), *_runtime_flags(runtime),
           image, "renode-test", to_container_path(robot_file_host),
           "-r", to_container_path(results_dir_host)]
    if resc_host_path:
        cmd += ["--variable", f"RESC:{to_container_path(resc_host_path)}"]
    if extra_args:
        cmd += extra_args
    result = subprocess.run(cmd)
    return result.returncode == 0
