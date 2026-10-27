# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Thin wrappers around `docker run` for the things we launch in the container:
module builds, interactive Renode simulation, renode-test runs, and the
interactive robot REPL. Centralising them here keeps the mount/flag
boilerplate in one place.
"""

import os
import re
import socket
import subprocess
import time

from . import core
from .core import to_container_path


def _xdisplay_args():
    # X11 forwarding for the interactive Renode GUI — X/POSIX only. Windows has no X
    # server or ~/.Xauthority, so emit nothing (a bogus -v mount would break the run);
    # there, use `hector run --renode-args '--console'` for a headless monitor. Also
    # skip if no Xauthority file can be located.
    if os.name == "nt":
        return []
    xauth = os.environ.get("XAUTHORITY") or (
        f"{os.environ['HOME']}/.Xauthority" if os.environ.get("HOME") else None)
    if not xauth:
        return []
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
    exception — it needs root for apt-get and chowns its artifacts back itself.

    The image's HOME belongs to its own user (uid 1000 in the Renode image), so any
    other uid can't write there and Renode aborts at startup. HOME is pointed at /tmp
    unless the user's docker args already set it.

    No-op on Windows: there is no host uid to map, and Docker Desktop handles
    bind-mount ownership itself."""
    ids = core.host_uid_gid()
    if not ids:
        return []
    flags = ["-u", f"{ids[0]}:{ids[1]}"]
    if not any(a.startswith(("HOME=", "--env=HOME=")) for a in core.DOCKER_ARGS):
        flags += ["-e", "HOME=/tmp"]
    return flags


def _workspace_mount(workdir=None):
    """Bind-mount the workspace and set the working directory (default: the config's
    directory, core.execution_dir)."""
    return ["-v", f"{core.workspace_root()}:{core.WORKSPACE_MOUNT}",
            "-w", workdir or core.execution_dir()]


def _extra_mounts():
    """Bind-mount out-of-tree dirs (the config's dir, a shared Renode source cache) 1:1,
    so containers reach them at the same path they have on the host, then append the
    user's own `docker run` flags (extra -v mounts, --env, ...). Empty for the common case."""
    args = []
    for d in core.EXTRA_MOUNTS:
        args += ["-v", f"{d}:{d}"]
    return args + core.DOCKER_ARGS


# Every container shares the host's network stack: GDB servers, tcp: mappings and
# anything a build/test step listens on are reachable from the host as-is, and steps
# can reach host services (e.g. a local registry or a TCP-mapped UART) on localhost.
# No -p publishing is needed (Docker ignores it in this mode anyway).
_HOST_NETWORK = ["--net=host"]


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
        subprocess.run(["bash", "-c", script], check=True, cwd=core.execution_dir())
        return
    subprocess.run(
        ["docker", "run", "--rm", *_HOST_NETWORK, "-u", "0:0",
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


def run_in_container(script, image, live=False, env=None):
    """Run a shell script with the project bind-mounted at the workspace path, returning
    (output, passed); streams when live=True. `set -ex` makes commands echo and the run
    fail on the first error. env: extra environment variables for the script.

    Backs the `shell` test type. Normally a one-off container of
    `image`; under --no-docker the script runs directly on the host (the image is moot).
    Either way it runs in the config's directory (core.execution_dir)."""
    cwd = None
    proc_env = None
    if core.NO_DOCKER:
        cmd = ["bash", "-c", f"set -ex\n{script}"]
        cwd = core.execution_dir()
        proc_env = {**os.environ, **env} if env else None
    else:
        env_flags = [f for k, v in (env or {}).items() for f in ("-e", f"{k}={v}")]
        cmd = ["docker", "run", "--rm", *_HOST_NETWORK, *_workspace_mount(),
               *_extra_mounts(), *_user_flags(), *env_flags,
               image, "sh", "-c", f"set -ex\n{script}"]
    if live:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, cwd=cwd, env=proc_env,
                                stderr=subprocess.STDOUT, text=True)
        lines = []
        for line in proc.stdout:
            print(line, end="", flush=True)
            lines.append(line)
        proc.wait()
        return "".join(lines), proc.returncode == 0
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                          cwd=cwd, env=proc_env)
    if proc.stdout:
        print(proc.stdout, end="")
    return proc.stdout, proc.returncode == 0


def build_renode_argv(resc_filename, image, extra_args=None, runtime=None):
    """Build the exact argv that would run an emulation resc — the local `renode`
    invocation under --no-docker, otherwise the full `docker run ... renode` command.

    Returning the command (instead of running it) is what lets the `export` command
    print it verbatim and keeps run_renode a one-liner around this builder.
    runtime: aggregated RuntimeOptions whose docker flags (caps/devices/root) are added.
    The resc path is made absolute: Renode runs in the config's directory, not the cwd."""
    if core.NO_DOCKER:
        return ["renode", os.path.abspath(resc_filename)] + (extra_args or [])
    return ["docker", "run", "-it", "--rm", *_xdisplay_args(), *_HOST_NETWORK,
            *_workspace_mount(), *_extra_mounts(), *_user_flags(), *_runtime_flags(runtime),
            image, "renode", to_container_path(resc_filename)] + (extra_args or [])


def run_renode(resc_filename, image, extra_args=None, output_dir="results", runtime=None):
    """Run an emulation resc interactively. GDB ports (--debug) are reachable from the
    host through the host network.
    runtime: aggregated RuntimeOptions whose docker flags (caps/devices/root) are added."""
    if not core.NO_DOCKER:
        os.makedirs(os.path.join(os.getcwd(), output_dir), exist_ok=True)
    subprocess.run(build_renode_argv(resc_filename, image, extra_args, runtime),
                   cwd=core.execution_dir() if core.NO_DOCKER else None)


class BackgroundRenode:
    """A headless Renode running alongside a `shell` test (`requires_sim: true`).

    Renode is started with its monitor on a TCP port (`-P`, reachable from the host and
    every container through the host network), then the resc is `include`d through that
    monitor — waiting for the prompt to come back is what tells us the emulation is
    loaded, and the reply is where load errors show up. Used as a context manager:

        with BackgroundRenode(image, log_path, runtime) as sim:
            sim.include(resc_host_path)        # raises RuntimeError on a resc error
            sim.release()                      # free the monitor for the test
            ... sim.port ...                   # the test talks to it here
    """

    _PROMPT = re.compile(r"\([^()\r\n]*\) $")         # "(monitor) ", "(mcu) "
    _ERROR = re.compile(r"There was an error|Could not find file|Error E\d+")
    _TELNET = re.compile(rb"\xff[\xfb-\xfe].|\xff[\xf0-\xfa]")

    def __init__(self, image, log_path, runtime=None, timeout=120):
        self.image, self.log_path, self.runtime, self.timeout = image, log_path, runtime, timeout
        self.port = _free_port()
        self.name = f"hector-sim-{os.getpid()}-{self.port}"
        self._proc = self._sock = None

    def __enter__(self):
        argv = ["renode", "--disable-xwt", "--plain", "-P", str(self.port)]
        os.makedirs(os.path.dirname(self.log_path) or ".", exist_ok=True)
        if core.NO_DOCKER:
            self._log = open(self.log_path, "w")
            self._proc = subprocess.Popen(argv, cwd=core.execution_dir(),
                                          stdout=self._log, stderr=subprocess.STDOUT)
        else:
            subprocess.run(["docker", "run", "-d", "--name", self.name, *_HOST_NETWORK,
                            *_workspace_mount(), *_extra_mounts(), *_user_flags(),
                            *_runtime_flags(self.runtime), self.image, *argv],
                           check=True, stdout=subprocess.DEVNULL)
        try:
            self._connect()
        except Exception:
            self.__exit__(None, None, None)
            raise
        return self

    def _connect(self):
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self._sock = socket.create_connection(("127.0.0.1", self.port), timeout=1)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise RuntimeError(f"Renode's monitor never opened on port {self.port}.")
                time.sleep(0.2)
        self._sock.settimeout(self.timeout)
        self._read_prompt()

    def _read_prompt(self):
        buf = b""
        while True:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise RuntimeError("Renode closed its monitor connection (did it crash?).")
            buf += chunk
            text = self._TELNET.sub(b"", buf).decode(errors="replace").replace("\r", "")
            if self._PROMPT.search(text):
                return text

    def command(self, line):
        """Run one monitor command; returns its output. Raises RuntimeError on an error."""
        self._sock.sendall(f"{line}\n".encode())
        out = self._read_prompt()
        if self._ERROR.search(out):
            raise RuntimeError(f"'{line}' failed:\n{out.strip()}")
        return out

    def include(self, resc_host_path):
        path = (os.path.abspath(resc_host_path) if core.NO_DOCKER
                else to_container_path(resc_host_path))
        return self.command(f"include @{path}")

    def release(self):
        """Drop hector's monitor connection so the test can connect to the port."""
        if self._sock:
            self._sock.close()
            self._sock = None

    def __exit__(self, *exc):
        self.release()
        if core.NO_DOCKER:
            if self._proc:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                self._log.close()
            return
        with open(self.log_path, "w") as log:
            subprocess.run(["docker", "logs", self.name], stdout=log, stderr=subprocess.STDOUT)
        subprocess.run(["docker", "rm", "-f", self.name],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_renode_test(robot_file_host, image, results_dir_host,
                    resc_host_path=None, extra_args=None, interactive=False, runtime=None):
    """Run a .robot file with renode-test in the container. Returns True on pass.

    resc_host_path: passed as --variable RESC:<path> so .robot files can load
    the generated emulation script via ${RESC}.
    extra_args: optional list of additional flags forwarded verbatim to renode-test.
    interactive: attach stdin/tty and X display (useful with Pause Execution).

    renode-test runs FROM the results dir: Renode's launcher adds its own `-r $(pwd)`,
    which (depending on the Renode version) can come after ours and win — running
    there makes both agree. Inputs are passed as absolute paths for the same reason.
    Renode itself is started by renode-test in its own install dir, so this doesn't
    change how paths inside the tests resolve.
    """
    os.makedirs(results_dir_host, exist_ok=True)
    if core.NO_DOCKER:
        results_dir = os.path.abspath(results_dir_host)
        cmd = ["renode-test", os.path.abspath(robot_file_host), "-r", results_dir]
        if resc_host_path:
            cmd += ["--variable", f"RESC:{os.path.abspath(resc_host_path)}"]
        if extra_args:
            cmd += extra_args
        result = subprocess.run(cmd, cwd=results_dir)
        return result.returncode == 0
    results_dir = to_container_path(results_dir_host)
    flags = ["-it"] if interactive else []
    display = _xdisplay_args() if interactive else []
    cmd = ["docker", "run", "--rm", *flags, *_HOST_NETWORK, *display,
           *_workspace_mount(workdir=results_dir), *_extra_mounts(), *_user_flags(),
           *_runtime_flags(runtime),
           image, "renode-test", to_container_path(robot_file_host), "-r", results_dir]
    if resc_host_path:
        cmd += ["--variable", f"RESC:{to_container_path(resc_host_path)}"]
    if extra_args:
        cmd += extra_args
    result = subprocess.run(cmd)
    return result.returncode == 0
