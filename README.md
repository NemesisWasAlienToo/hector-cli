# Hector

**`hector`** is the open-source CLI at the core of the Hector platform: a
YAML-driven orchestrator for simulating embedded hardware systems. It combines
[Renode](https://renode.io/) machine emulation with
[Verilator](https://www.veripool.org/verilator/) co-simulated HDL modules,
wiring them together from a single `.hector.yaml` file. Everything runs inside
the official `antmicro/renode` Docker image, so builds are reproducible
regardless of host toolchain.

One config drives every mode — interactive simulation (`hector run`), automated
testing (`hector test`), and command export (`hector export`) — and the same
file is what [Hector CI](https://hector-ci.com) runs in continuous integration.

Licensed under **AGPL-3.0-or-later** — see [LICENSE](LICENSE) and
[LICENSING.md](LICENSING.md).

---

## Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Changelog](CHANGELOG.md)
- [Run via Docker (no install)](#run-via-docker-no-install)
- [Invocation modes](#invocation-modes)
- [Configuration reference](#configuration-reference)
  - [Top-level fields](#top-level-fields)
  - [arguments](#arguments)
  - [matrix](#matrix)
  - [modules](#modules)
    - [developing your own peripherals](#developing-your-own-peripherals)
  - [hubs](#hubs)
  - [machines](#machines)
    - [inline repl and resc](#inline-repl-and-resc)
    - [peripherals](#peripherals)
    - [connections (per-machine)](#connections-per-machine)
    - [mappings](#mappings)
    - [artifacts](#artifacts)
  - [connections (global)](#connections-global)
  - [mappings (global)](#mappings-global)
  - [prepare](#prepare)
  - [tests](#tests)
  - [quantum](#quantum)
  - [ci](#ci)
- [Connection syntax](#connection-syntax)
- [Interpolation](#interpolation)
- [Generated artifacts](#generated-artifacts)
- [Complete example](#complete-example)

---

## Requirements

- Python 3.10+ with `pyyaml` (`pip install pyyaml`)
- Docker (the Renode image is pulled automatically on first run)
- Git — only needed when a config builds `modules:` or uses `${RENODE_DIR}`; the framework then clones the Renode source on first run (see [Renode source checkout](#renode-source-checkout))

---

## Installation

Install the package to get the `hector` command on your `PATH`:

```bash
cd cli
pip install .          # or: pip install -e .   (editable — picks up local edits)
hector --version
```

`pip install` creates a `hector` launcher in your environment's scripts directory
(the venv's `bin/`, or `~/.local/bin` for `pip install --user`). If `hector` isn't
found afterwards, that scripts directory isn't on your `PATH` — add it, e.g.
`export PATH="$HOME/.local/bin:$PATH"`.

**No install?** Run the module directly from the `cli/` directory — it's equivalent:

```bash
python -m hector --version
```

> **Do not add the `cli/` source directory to your `PATH`.** The Python package is
> named `hector/`, so a bare `hector` would resolve to that **directory** instead of
> the command, and your shell fails with `permission denied: hector` (or
> `command not found`). Install with `pip` (above) or use `python -m hector`.

---

## Quick start

```
project/
├── .hector
└── platforms/
    └── boards/
        └── stm32f4_discovery.repl   # your Renode platform file
```

Bootstrap a new project:

```bash
hector init
```

Then simulate or test:

```bash
hector run     # simulate (interactive Renode monitor)
hector test    # run the tests: section
hector export  # print the run command without executing it
hector prepare # run only the prepare: steps
```

Generated files go in `.hector/` — add it to your `.gitignore`. The Renode **binary** runs from the Docker image; the Renode **source** is only cloned when a config needs it (see [Renode source checkout](#renode-source-checkout)).

---

## Run via Docker (no install)

If you'd rather not install hector (or even Python) on the host, build the bundled
image — it sits on top of the official Renode image, so `renode`, `renode-test`
and `hector` are all inside one container:

```bash
cd cli
docker build -t hector-renode .
# match your project's `renode.image` version:
docker build --build-arg RENODE_VERSION=1.16.1 -t hector-renode:1.16.1 .
```

Because Renode is already in the image, hector runs **in-process**
(`HECTOR_NO_DOCKER=1` is baked in) — no Docker socket, no sibling containers, no
host-path matching. Use the bundled `hector-docker` wrapper, which mounts your
project and runs as your UID so output stays yours:

```bash
./hector-docker test                       # run from your project directory
./hector-docker validate -f ci.hector.yaml
./hector-docker run --renode-args '--console'   # headless monitor (no GUI window)

# use it like the real thing by symlinking onto your PATH:
ln -s "$(pwd)/cli/hector-docker" ~/.local/bin/hector
```

Or the raw form (what the wrapper runs):

```bash
docker run --rm -it -u "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$PWD":"$PWD" -w "$PWD" hector-renode test
```

Override the image tag with `HECTOR_IMAGE` (default `hector-renode:latest`).

**Caveats of the in-image mode:** a `shell` test's `image:` is ignored —
the script runs in *this* image instead (a warning is printed), and module builds
rely on this image's toolchain rather than a per-module one. Interactive `hector
run` opens Renode's GUI, which needs X forwarding; pass `--renode-args '--console'`
for a headless monitor. For full per-step image isolation (matching CI), install
the CLI natively with `pip` and let hector launch real per-step containers.

---

## Invocation modes

| Command | Behaviour |
|---|---|
| `hector run` | Run the [`prepare:`](#prepare) steps, then the simulation interactively (Renode monitor) |
| `hector run -f board.yaml` | Read a config file other than `.hector.yaml` (`-f`/`--file`; works on every command) |
| `hector run --set BIN=fw.elf` | Override a config argument at the command line |
| `hector run --set BIN=fw.elf --set BOARD=nucleo` | Override multiple arguments |
| `hector run --debug boardA:3333` | Halt a CPU and open a GDB server |
| `hector run --debug boardA:3333 --debug boardB:3334` | Halt multiple CPUs on different ports |
| `hector run --no-start` | Load the platform and drop into the monitor **paused** — type `start` yourself |
| `hector run --renode-args '--console'` | Pass extra flags verbatim to Renode |
| `hector run --gather-execution-metrics` | Enable Renode's CPU execution profiler for all machines |
| `hector run --gather-execution-metrics boardA` | Enable profiler for one specific machine |
| `hector run --gather-execution-metrics boardA --gather-execution-metrics boardB` | Enable profiler for selected machines |
| `hector run --renode-image 1.16.1` | Override `renode.image` from `.hector.yaml` with a version… |
| `hector run --renode-image my-renode:dev` | …or with any (e.g. self-built) Renode Docker image |
| `hector run --renode-docker-flags '-v /opt/tools:/opt/tools'` | Add `docker run` flags (mounts, env, …) to the Renode containers |
| `hector run --renode-dir /cache/renode` | Use/cache the Renode source checkout at this path (only fetched when needed) |
| `hector run --renode-integration-dir /cache/integration` | Likewise for the verilator-integration checkout |
| `hector run --no-docker` | Use locally installed `renode` / `renode-test` instead of Docker |
| `hector run --workspace-mount /mnt` | Mount the hectorfile's folder at this container path and execute there |
| `hector run --snapshot path/to/snapshot.save` | Load a snapshot instead of booting from the resc |
| `hector run --snapshot snap.save --renode-image 1.16.1` | Load a snapshot without a `.hector.yaml` |
| `hector test` | Run the [`prepare:`](#prepare) steps, then the `tests:` section; exit 1 on any failure |
| `hector test --fail-fast` | Stop after the first failing test |
| `hector prepare` | Run only the [`prepare:`](#prepare) steps — no emulation, no tests; exit 1 on failure |
| `hector test --skip-prepare` | Skip the [`prepare:`](#prepare) steps and reuse what an earlier run prepared (also on `run`) |
| `hector test --test-file tests/boot.robot` | Run a specific `.robot` file instead of the YAML tests |
| `hector test --test-name "Button press"` | Run only tests whose name contains the given substring |
| `hector test --test-name "boot" --test-name "uart"` | Run tests matching any of the given names |
| `hector test --live` | Stream bash output line-by-line and enable verbose keyword output for robot tests |
| `hector test --snapshot path/to/snapshot.save` | Load a snapshot at the start of every test |
| `hector test --reporters junit --reporters json` | Select which reporters emit after tests (repeatable) |
| `hector test --output my-results` | Write test results and artifacts to `my-results/` instead of `results/` |
| `hector test --renode-test-args '--loglevel DEBUG'` | Pass extra flags verbatim to `renode-test` |
| `hector run --job BOARD=stm32f7` | Select the matrix combination where BOARD=stm32f7 |
| `hector run --job BOARD=stm32f7,FW=release.elf` | Select the exact combination (pin every matrix variable) |
| `hector export` | Generate the files and print the run command instead of executing it |
| `hector export --no-docker` | Print the bare `renode <resc>` command instead of the `docker run …` one |
| `hector validate` | Validate `.hector.yaml` without running anything |
| `hector validate -f board.yaml` | Validate a config file by another name |
| `hector init` | Scaffold a starter `.hector.yaml` |
| `hector init -f board.yaml` | Scaffold the starter config under a custom name |
| `hector clean` | Remove generated build artifacts (`.hector/resc,repl,tests`) and `results/`; keeps the Renode cache |
| `hector clean --all` | Also remove the cached Renode source checkouts under `.hector/` (forces a re-clone next build) |
| `hector clean --output my-results` | Clean a custom results directory instead of `results/` |
| `hector clean --dry-run` | Show what would be removed without deleting anything |
| `hector --version` | Print the tool version |

`hector` is structured as subcommands: `run` (simulate), `test` (run the `tests:`
section), `export` (emit the command without running it), plus `init`, `validate`,
and `clean`. Run `hector <command> --help` for the flags each one accepts.

Every command reads (or, for `init`, writes) `.hector.yaml` by default. Point it
at a different file with **`-f` / `--file`** — useful when one project keeps
several configs (e.g. `ci.hector.yaml`, `local.hector.yaml`):

```bash
hector test -f ci.hector.yaml
hector run  --file boards/nucleo.yaml
```

**`.yaml` and `.yml` are interchangeable.** If the requested file isn't there but its
counterpart is, hector uses that instead — so a project may keep `.hector.yml` and
every command still finds it with no flag, and `-f board.yaml` will pick up
`board.yml`.

### Debug mode (`--debug NODE:PORT`)

Repeat the flag for each machine you want to debug. ([Renode docs: GDB debugging](https://renode.readthedocs.io/en/latest/debugging/gdb.html))

- Adds `machine StartGdbServer <port>` to the generated resc while that machine is active.
- Adds `cpu IsHalted true` to freeze the CPU until a debugger attaches.
- Exposes the port via `-p PORT:PORT` in Docker.

All other machines boot and run normally.

`--debug` also works alongside `--snapshot`: the loaded snapshot opens the same GDB
server(s) and halts the debugged CPU(s) before resuming, so you can attach to a
restored state. (A GDB server is a live connection, never part of saved snapshot
state, so it is always (re)started on load.)

### Manual start (`--no-start`)

Every generated resc ends with a `start`, so `hector run` boots the platform
immediately. Pass `--no-start` to omit it: hector builds/loads the platform, wires
everything up, and drops you at the Renode monitor **paused**, so you can inspect
state, set watchpoints, or step the setup by hand and issue `start` yourself.

```bash
hector run --no-start        # land in the monitor; type `start` when ready
```

- Applies to a fresh boot and to `--snapshot` (the restored state loads paused).
- Composes with `--debug`: the GDB server(s) open at load, but nothing runs until
  you `start`, so you can attach a debugger *before* the very first instruction.
- `hector test` ignores this (tests must run); it only affects `run`/`export`.

Connect with:
```bash
arm-none-eabi-gdb firmware.elf
(gdb) target extended-remote localhost:3333
(gdb) break main
(gdb) continue
```

Or use VS Code with the Cortex-Debug extension pointed at `localhost:3333`.

### Test mode (`hector test`)

Runs the [`prepare:`](#prepare) steps, then every step in the `tests:` section in declaration order. A failing prepare step skips the tests. All test steps run to completion even if one fails. The process exits with code 1 if any step failed, making it usable directly in CI.

Add `--fail-fast` to stop after the first failing job when running a matrix.

#### Filtering tests by name (`--test-name`)

Run only the tests whose name contains the given substring. The flag is repeatable — any match runs:

```bash
# run one test
hector test --test-name "Button press"

# run two tests by name fragment
hector test --test-name "boot" --test-name "uart"
```

Matching is case-sensitive substring search against the `name:` field in the YAML (or the basename of `--test-file`).

#### Streaming output live (`--live`)

By default bash test output is captured and printed as a block after the step finishes, and robot tests show only a per-test summary line. With `--live`:

- **bash steps** — each output line is printed as it is written by the script.
- **robot steps** — `renode-test` runs with `--verbose`, printing every keyword call and its timing as it executes.

```bash
hector test --live

# combine with --test-name to focus on one test with full output
hector test --test-name "Button press" --live
```

Both flags are independent and can be used together or separately.

#### Loading a snapshot (`--snapshot`)

Load a previously saved Renode snapshot instead of booting from the generated resc. The snapshot restores the complete emulation state (all machines, memory, peripheral registers) and resumes execution.

```bash
# simulation mode: drop into the monitor with state restored
hector run --snapshot results/step_1_Linux_boots/snapshot.save

# test mode: every test starts from the snapshot instead of booting
hector test --snapshot results/step_1_Linux_boots/snapshot.save
```

When used with `--renode-image`, no `.hector.yaml` is needed at all — useful for inspecting a snapshot outside of any project:

```bash
hector run --snapshot /path/to/snapshot.save --renode-image 1.16.1
```

The CLI flag overrides any per-test `snapshot:` field in the YAML (see [tests](#tests)).

**Saving a snapshot** from the interactive Renode monitor:

```
Save @/home/user/projects/myboard/.hector/snapshots/post_boot.save
```

Use the actual host path to your project directory (the same path you see on the host — the container mounts it at the identical location). Create the directory first.

#### Running a specific `.robot` file (`--test-file`)

Pass any `.robot` file directly instead of the YAML-defined tests. Hector generates the resc from your YAML config, then runs the file against it. The generated resc path is injected as `${RESC}` so the file can load the emulation:

```bash
hector test --test-file tests/boot.robot
```

`tests/boot.robot` must include the resc itself:
```robot
*** Settings ***
Library           Collections
Resource          ${RENODEKEYWORDS}
Suite Teardown    Reset Emulation

*** Test Cases ***
Boot sequence
    Execute Command    include @${RESC}
    Create Terminal Tester    sysbus.usart2    machine=boardA
    Wait For Line On Uart     Board initialized    timeout=30
```

#### Changing the output directory (`--output`)

By default Hector writes test results, Robot Framework XML/HTML reports, and JUnit XML to `results/`. Pass `--output` to redirect everything to a different path:

```bash
hector test --output ci-results
hector test --output /tmp/run-42
```

In simulation mode the flag controls the directory pre-created for Renode to write file-mapped outputs (e.g. UART logs from `file:results/uart.log`). Note that your YAML `file:` paths should match whatever directory you choose here.

#### Test reporters (`--reporters`)

After all steps complete, Hector calls one or more reporters with the full result list. Two are built in:

- **`junit`** (default) — writes `<output>/junit.xml`, compatible with GitLab CI, GitHub Actions, and Jenkins.
- **`json`** — writes `<output>/manifest.json`, a machine-readable index for dashboards / CI: one entry per test with `status`, `duration`, `commands`, and relative paths to its detail artifacts (`report_html`, plus `log_html` / `robot_xml` for robot tests).

The flag is repeatable (repeat it once per reporter):

```bash
hector test                                   # default: junit
hector test --reporters junit --reporters json   # also emit the dashboard manifest
```

To add a custom reporter, register it in Python before invoking the pipeline:

```python
from hector.reporters import REPORTERS

@REPORTERS.register("csv")
def csv_reporter(results, output_dir):
    import csv, os
    with open(os.path.join(output_dir, "results.csv"), "w") as f:
        w = csv.DictWriter(f, fieldnames=["name", "type", "passed", "duration"])
        w.writeheader()
        for r in results:
            w.writerow({"name": r.name, "type": r.type,
                        "passed": r.passed, "duration": r.duration})
```

Then pass its name with `--reporters csv`. The flag is repeatable, so combine reporters by repeating it: `--reporters junit --reporters csv`.

#### Passing extra flags to `renode-test` (`--renode-test-args`)

Forwards additional flags verbatim to the `renode-test` invocation for every test step. Accepts any flag that Robot Framework accepts:

```bash
# Enable verbose logging for debugging
hector test --renode-test-args '--loglevel DEBUG'

# Inject a variable into every robot step
hector test --renode-test-args '--variable FOO:bar'

# Run only tests tagged "smoke"
hector test --renode-test-args '--include smoke'
```

These are appended after any per-step `args:` keys defined in the YAML, so per-step args take precedence.

### Simulation mode

Runs the [`prepare:`](#prepare) steps, then launches one Renode emulation per job in the Docker container (a failing prepare step skips it, exit 1). `run` writes no reports; to get reports for the prepare steps, run them through `hector test`. Each machine declared in the YAML becomes a named Renode machine in that emulation. The Renode monitor is interactive; type `help` at the prompt for available commands.

#### Gathering execution metrics (`--gather-execution-metrics`)

Enables Renode's built-in CPU execution profiler. Without a machine name, enables it for all machines. Repeatable to target specific machines:

```bash
# all machines
hector run --gather-execution-metrics

# specific machines only
hector run --gather-execution-metrics boardA
hector run --gather-execution-metrics boardA --gather-execution-metrics boardB

# combine with --output
hector run --gather-execution-metrics --output ci-results
```

For each targeted machine, Hector injects `cpu EnableProfiler @<path>` into the generated resc. Profiler output is written to the output directory, one binary file per machine per job:

```
results/
├── metrics_boardA_job_1.bin
└── metrics_boardB_job_1.bin
```

Works in both simulation and test mode. In test mode each test step re-runs the resc, so the metrics file for each machine reflects only the most recent test step's execution.

Analyse the output with Renode's [ExecutionMetricsAnalyzer](https://renode.readthedocs.io/en/latest/advanced/execution-metrics.html).

#### Passing extra flags to Renode (`--renode-args`)

Forwards additional flags verbatim to the `renode` process:

```bash
hector run --renode-args '--console'
hector run --renode-args '--hide-log --config my.conf'
```

#### Paths and working directory

Everything a hectorfile executes — `shell` tests, Renode and `renode-test` — runs **in the hectorfile's folder**, and paths written in the file (`firmware:`, `platform:`, module `source:`, test `file:` / `snapshot:`, `file:` mappings, `artifacts:`, paths inside scripts and `commands:`) are **relative to that folder**. So `hector test -f boards/nucleo/.hector.yaml` behaves the same as running `hector test` inside `boards/nucleo/`.

The directory you run hector from is mounted into the container (at the same path), and the container's working directory (`-w`) is the hectorfile's folder. If the hectorfile lives **outside** the directory you run from (`hector test -f ../other/.hector.yaml`), its folder is mounted as well, at its own path. (With [`--workspace-mount`](#overriding-the-workspace-mount-path---workspace-mount) the hectorfile's folder is mounted at the given path instead.) A path like `../shared/board.repl` works as long as it lands inside one of those mounts — for anything else, add a mount with [`docker-flags`](#extra-docker-flags-docker-flags). Under `--no-docker` the processes simply run with the hectorfile's folder as their cwd.

**Relative `@paths` inside Renode.** The generated resc starts with `path add @<hectorfile's folder>`, so Renode looks up a relative `@path` in the hectorfile's folder first, then in its own install folder. That covers `platform:`/`firmware:`, your `resc:` and `commands:` lines (`sysbus LoadELF @fw/app.elf`, `include @scripts/setup.resc`) and `using "..."` inside `.repl` files — in `hector run` and in tests alike, even though renode-test starts Renode in its install folder. Paths that ship with Renode (`platforms/cpus/stm32f103.repl`) keep working, unless a file with the same relative path exists in the hectorfile's folder, which then takes precedence. Note that `$ORIGIN` is the generated resc's folder (`.hector/resc/`), not the hectorfile's.

Paths given on the **command line** (`--output`, `--snapshot`, `--test-file`, `--artifacts`, `--renode-dir`, …) stay relative to where you run hector, and `.hector/` is still created there.

#### Extra Docker flags (`docker-flags`)

There are no flags for *every* container. Each container gets the flags declared on
the thing it runs:

- **`renode.docker-flags`** — the Renode containers: the emulation (`run`), robot tests
  (renode-test), the background sim of `requires-machine: true`, and module builds.
- **A `shell` test's or `prepare:` step's own `docker-flags:`** — that test's or step's
  containers only (a `shell` test in the Renode image doesn't get the Renode flags).

Each is a string or a list of strings:

```yaml
renode:
  image: "1.16.1"
  docker-flags:
    - -v /opt/toolchains:/opt/toolchains:ro
    - -e LICENSE_SERVER=10.0.0.5

tests:
  - name: Flash over USB
    type: shell
    image: python:3.12-slim
    docker-flags: --device=/dev/ttyUSB0
    script: python3 tools/flash.py /dev/ttyUSB0
```

`--renode-docker-flags` on the command line is **appended** to `renode.docker-flags`:

```bash
hector test --renode-docker-flags '-v /data/firmware:/data/firmware'
```

Use absolute host paths for `-v` (Docker treats a bare name as a named volume). A
prepare step without `image:` runs on the host, so `docker-flags:` there is an error, as
it is on a robot test (use `renode.docker-flags`). Ignored under `--no-docker`, with a
warning.

> **Migration:** the top-level `docker_args:` reached every container and is now a
> config error; `--docker-args` is gone. Move flags the Renode containers need to
> `renode.docker-flags` and the rest to the `docker-flags:` of the test or step that
> needs them.

#### Container networking

Every container hector starts — the Renode emulation (`run`), robot tests, `shell` tests, `prepare:` steps and module builds — runs with `--net=host`. GDB servers (`--debug`), `tcp:` mappings and anything a step listens on are reachable from the host on the same port, and steps can reach host services on `localhost`. No port publishing is involved.

With a remote Docker daemon (`DOCKER_HOST=tcp://docker:2375`, as with a CI's Docker-in-Docker service), "the host" is the daemon's machine: containers still reach each other on `localhost`, and hector itself connects to the background sim's monitor on the `DOCKER_HOST` host. Bind mounts use host paths, so the project must be at the same path on the daemon's machine (CI runners share their build directory with the DinD service).

#### Container user

Containers run as **your UID:GID** (`-u`), so files they write into the project are yours, not root's. The image's own home folder belongs to its user (UID 1000 in the Renode image), so hector also sets `HOME=/tmp`. Without it, Renode can't create its user folder under any other UID and aborts at startup. To use a different home, set it in that container's `docker-flags` (`-e HOME=/some/dir`), and hector leaves it alone. Module builds run as root, and so does Renode when a mapping needs root (e.g. `tap`).

#### Running without Docker (`--no-docker`)

Call the locally installed `renode` and `renode-test` binaries directly instead of launching a Docker container. `shell` tests and `prepare:` steps also run on the host (their `image:` is ignored, with a warning), as do module builds.

```bash
hector run --no-docker
hector test --no-docker
```

Requires `renode` and `renode-test` to be on your `PATH` — and, since images are ignored, whatever toolchains your `shell` scripts call (e.g. a compiler). **`--no-docker` and `--workspace-mount` are mutually exclusive** — they both control how the project root is made accessible and cannot be combined.

#### Choosing Renode (`renode.image` / `--renode-image`)

The `renode:` section names the Renode image and its container flags:

```yaml
renode:
  image: "1.16.1"                 # → antmicro/renode:1.16.1
  docker-flags: -e FOO=1          # optional: see Extra Docker flags
```

`image:` is either a **version** (`1.16.1`, `v1.16.1` → the official
`antmicro/renode` image) or any **Docker image reference**: a mirror, a nightly, your
own build — even one a [prepare step](#prepare) builds, because the image is only used
after the prepare steps (see [`examples/custom-renode-image`](examples/custom-renode-image)).

```yaml
renode:
  image: "ghcr.io/acme/renode:1.16.1-patched"
```

`--renode-image` overrides it without editing the file:

```bash
hector test --renode-image 1.15.0
hector test --renode-image my-renode:dev
```

When combined with `--snapshot` in simulation mode, `.hector.yaml` is not required at all — the two flags together are self-contained:

```bash
hector run --snapshot path/to/snapshot.save --renode-image 1.16.1
```

If a config needs the Renode source (see below), hector clones the tag matching the
version — for an image, taken from its tag when it looks like one (`…:1.16.1`,
`…:v1.16.1`). So tag your own images with the Renode version they're based on, or
point `--renode-dir` at a checkout.

> **Migration:** `renode` is a section: `renode: "1.16.1"` becomes `renode:` with
> `image: "1.16.1"` under it. `renode_version:` / `renode_image:` and
> `--renode-version` / `--renode` are replaced by `renode.image` / `--renode-image`.
> The old forms are config errors.

#### Renode source checkout

Running a simulation does **not** need the Renode source — the binary and its bundled platforms come from the `antmicro/renode` Docker image. Hector clones the Renode source (and the verilator-integration repo) into `.hector/` **only when a config actually needs it**:

- it builds `modules:` (Verilated / C# co-simulated peripherals, which compile against the Renode source), or
- it interpolates `${RENODE_DIR}` / `${INTEGRATION_DIR}`.

For everything else — plain or YAML-defined machines, firmware URLs, `shell` tests — nothing is cloned, so runs start immediately.

When the source *is* needed, point hector at a cached or shared checkout instead of re-cloning each time:

```bash
hector test --renode-dir /cache/renode --renode-integration-dir /cache/renode-integration
```

An existing directory is reused as-is; a missing one is cloned into. The location may live **outside the project** (e.g. a persistent CI cache) — hector bind-mounts an out-of-tree checkout into every container 1:1 (at the same path), so `modules:` builds and `${RENODE_DIR}` references still resolve. A path under the project works too (it's covered by the normal workspace mount).

#### Overriding the workspace mount path (`--workspace-mount`)

By default everything is bind-mounted into the container at the **same absolute path** as on the host (e.g. `/home/user/projects/myboard`), so paths look identical inside and outside the container. `--workspace-mount PATH` instead mounts the **hectorfile's folder** at `PATH`, and that's where every step, Renode and `renode-test` execute:

```bash
hector run --workspace-mount /workspace                              # . → /workspace
hector test -f boards/nucleo/.hector.yaml --workspace-mount /workspace  # boards/nucleo → /workspace
```

When you run from a different folder than the hectorfile's (the second line), that folder — where `.hector/` and `--output` live — is additionally mounted at its own path, unless it's already inside the hectorfile's folder.

**Cannot be combined with `--no-docker`** — if you are running locally there is no container mount to configure.

### Selecting a matrix combination (`--job`)

**hector runs exactly one matrix combination per invocation — it does not expand the matrix itself.** Iterating combinations (and running them in parallel) is the CI's job: it reads the `matrix:`, then calls hector once per combination.

- **No matrix:** a single invocation runs the one (empty) job — no `--job` needed.
- **Matrix defined:** you must pin it to one combination with `--job KEY=VALUE`, repeating keys with commas to constrain every variable:

```bash
hector test --job BOARD=stm32f7                 # one variable pins it
hector test --job BOARD=stm32f7,FW=release.elf  # pin every variable
```

If `--job` is missing (or matches more than one combination), hector lists the combinations and exits without running:

```
[ERROR] The matrix produces 3 combinations; a run targets one. Select it with
--job KEY=VALUE (e.g. --job BOARD=stm32f4).
  Combinations:
  BOARD=stm32f4 FW=debug.elf
  BOARD=stm32f7 FW=debug.elf
  BOARD=stm32f4 FW=release.elf
```

Values match as strings, so `--job RATE=2` selects a numeric `2` in the matrix.
### Export mode (`hector export`)

Builds everything a run would except the [`prepare:`](#prepare) steps, which it skips — the per-machine `.repl` files and the emulation
`.resc` — but, instead of launching, prints the exact command that *would* run it:

```bash
# the docker invocation hector would execute
hector export
# → docker run -it --rm … antmicro/renode:1.16.1 renode .hector/resc/job_1.resc

# with --no-docker, the bare local command instead
hector export --no-docker
# → renode .hector/resc/job_1.resc
```

Useful for inspecting or wrapping the command (custom Docker flags, a different
runner, CI plumbing). With a matrix, one command per job is printed. The same
build flags as `run` apply (`--set`, `--debug`, `--snapshot`, `--renode-args`, …).

### Validate mode (`hector validate`)

```bash
hector validate
```

Parses and validates `.hector.yaml` without touching Docker. All errors are collected and reported at once:

```
[VALIDATE] Checking .hector.yaml ...
  ERROR  modules.uart0.type: Required: the Renode class this module exposes.
  ERROR  hubs.mylink.type: Unknown hub type 'spi'. Available: ble, can, ...
  WARN   machines.boardA.peripherals.btn: Unknown machine key 'tyep'.
[VALIDATE] FAILED — 2 error(s), 1 warning(s).
```

---

## Configuration reference

The configuration lives in `.hector.yaml`.

### Top-level fields

| Field | Required | Description |
|---|---|---|
| `version` | No | Schema version, currently `"0.2"`. `"0.1"` is an error listing what changed; another unknown value warns. |
| `renode` | Yes¹ | Section: `image:` — a Renode version (`1.16.1` → `antmicro/renode:1.16.1`) or any Docker image; optional `docker-flags:` for the Renode containers. See [choosing Renode](#choosing-renode-renodeimage----renode-image) and [extra Docker flags](#extra-docker-flags-docker-flags). |
| `arguments` | No | Scalar defaults, overridable by env var or `--set`. |
| `matrix` | No | Cross-product job expansion. |
| `modules` | No | Verilated / C# peripheral type definitions. |
| `hubs` | No | Emulation-level connection objects (uart, can, ethernet, gpio, usb, wireless, ble, wisun). |
| `machines` | No | The machines to simulate. Optional: a config may only run `shell` tests. `run`/`export`, robot tests and `requires-machine: true` shell tests require at least one. |
| `connections` | No | Global signal wiring. |
| `mappings` | No | Emulated peripheral → host resource bindings. |
| `prepare` | No | Shell steps run before anything uses the Renode image: fetch/compile inputs, build the image. |
| `tests` | No | Test steps run by `hector test`. |
| `quantum` | No | Override the global time quantum (seconds). |
| `ci` | No | CI pipeline definitions: when and how a CI server runs this config. |

¹ Required (with its `image:`), unless `--renode-image` is passed.

---

### arguments

Scalar parameters with defaults. Usable anywhere in the YAML as `${NAME}`. Matrix variables take precedence over arguments when names collide.

```yaml
arguments:
  BOARD: stm32f4_discovery
  FW: firmware.elf
```

Override at runtime — three ways, in increasing precedence order:

```bash
# 1. config default  (declared above)

# 2. environment variable — same name as the argument key
BOARD=stm32f7_discovery hector run

# 3. --set flag — highest precedence, beats env vars
hector run --set BOARD=stm32f7_discovery
hector run --set BOARD=stm32f7_discovery --set FW=release.elf
```

`--set` can also introduce keys not declared in `arguments:` — they are merged into the interpolation context and can be referenced in the YAML as `${KEY}`.

---

### matrix

Declares the cross-product of values that make up the build/test space. Each combination is one complete simulation run. **hector does not run the whole matrix** — a single invocation runs one combination, selected with [`--job`](#selecting-a-matrix-combination---job); iterating the matrix is the CI's job. The `matrix:` block is the source of truth the CI reads to enumerate combinations.

```yaml
matrix:
  variables:
    BOARD: ["stm32f4_discovery", "stm32f7_discovery"]
    FW:    ["debug.elf", "release.elf"]
```

This declares four combinations (run one with e.g. `--job BOARD=stm32f4_discovery,FW=debug.elf`). An `exclude` block can remove specific combinations:

```yaml
matrix:
  variables:
    BOARD: ["stm32f4_discovery", "stm32f7_discovery"]
    FW:    ["debug.elf", "release.elf"]
  exclude:
    - BOARD: stm32f7_discovery
      FW: debug.elf
```

A 1×1 matrix is a convenient way to keep the field present in the YAML while running only one job:

```yaml
matrix:
  variables:
    VARIANT: ["default"]
```

---

### modules

Defines reusable peripheral **types**. A module is built once per job, producing a loadable artifact (`.so` for Verilator, `.dll` for C#). Modules are referenced by name from a machine's `peripherals:` section.

#### kind: renode-verilator

Builds a verilated co-simulation peripheral into a `.so` inside the Renode Docker container (guaranteeing ABI compatibility). Loaded by Renode via its co-simulation interface. ([Renode docs: co-simulation with HDL](https://renode.readthedocs.io/en/latest/advanced/co-simulating-with-an-hdl-simulator.html))

```yaml
modules:
  uartlite:
    kind: renode-verilator       # default if omitted
    type: CoSimulated.CoSimulatedUART
    source: "${INTEGRATION_DIR}/samples/uartlite"
    cmake_flags: ""              # optional extra CMake arguments
```

| Field | Required | Description |
|---|---|---|
| `kind` | No (default: `renode-verilator`) | `renode-verilator` or `csharp`. |
| `type` | Yes | Fully qualified Renode class name the artifact exposes. |
| `source` | Yes | Path to the CMake project root. `${INTEGRATION_DIR}` and `${RENODE_DIR}` are available. |
| `cmake_flags` | No | Extra flags appended to the `cmake` invocation. |

`${INTEGRATION_DIR}` resolves to the managed clone of [renode-verilator-integration](https://github.com/antmicro/renode-verilator-integration) inside `.hector/`. Its `samples/` directory contains ready-to-build examples.

**Multiple instances** of one module are declared as separate `peripherals:` entries. The framework copies the built `.so` per instance so each gets independent simulation state.

#### kind: csharp

A native C# Renode peripheral, loaded at emulation scope via `i @<path>` before any machine block so the type is available to every machine in the job. ([Renode docs: writing peripherals](https://renode.readthedocs.io/en/latest/advanced/writing-peripherals.html))

`source` can take three forms:

**Single `.cs` file (recommended)** — Renode compiles it **at load time** using its bundled C# compiler. No .NET SDK, no build step, nothing to install; the source is compiled against the running Renode's own assemblies, so it always matches the version in use. See the runnable [`csharp-peripheral`](examples/csharp-peripheral) example.

```yaml
modules:
  my_periph:
    kind: csharp
    type: Antmicro.Renode.Peripherals.Miscellaneous.MyPeripheral
    source: MyPeripheral.cs
```

**Pre-built DLL** — point `source` directly at a `.dll` (used as-is):

```yaml
modules:
  my_periph:
    kind: csharp
    type: My.Namespace.MyPeripheral
    source: prebuilt/my_periph.dll
```

**Build from a `.csproj`** — point `source` at a directory containing a `.csproj`; `dotnet build` (or `msbuild`) runs in the container. This needs an image that ships the **.NET SDK** *and* Renode's reference assemblies — the stock Renode image has only the runtime, so a `.cs` source is simpler unless you specifically need a pre-built binary:

```yaml
modules:
  my_periph:
    kind: csharp
    type: My.Namespace.MyPeripheral
    source: hw/cs/MyPeripheral
```

| Field | Required | Description |
|---|---|---|
| `kind` | Yes | Must be `csharp`. |
| `type` | Yes | Fully qualified C# class name as it appears in the generated `.repl`. |
| `source` | Yes | A `.cs` file (compiled at load), a `.csproj` directory (built in the container), **or** a pre-built `.dll`. |

The `type` must match the class your source exposes. Multiple peripherals in the same job can share one source (different `type` values, same `source`); Hector emits a single `i @<path>` import even when multiple instances reference it.

#### Developing your own peripherals

The `modules:` block above only *wires in* a peripheral you've built — the actual
modelling (the Verilog/C++ of a Verilated block, or the C# of a native peripheral)
is Renode's domain, not Hector's. Hector compiles your `source:` and loads the
result; **how** you write that source is documented by Renode and Verilator. The
references below are where to go to design your own hardware in depth.

##### Verilated (HDL) peripherals

A Verilated peripheral is your RTL (Verilog / SystemVerilog) compiled by Verilator
and bridged to Renode over a bus interface (APB / AXI-Lite / Wishbone). Hector
builds it from the CMake project you point `source:` at, linking against the
**renode-verilator-integration** library (`${INTEGRATION_DIR}`).

- **How Renode co-simulates HDL** (the model, the bus connectors, the lifecycle) — [Renode docs: Co-simulating with an HDL simulator](https://renode.readthedocs.io/en/latest/advanced/co-simulating-with-an-hdl-simulator.html)
- **The integration library + copy-ready CMake samples** (start from `samples/uartlite`, which the `docker-runner`/module examples mirror) — [antmicro/renode-verilator-integration](https://github.com/antmicro/renode-verilator-integration)
- **Verilating your RTL** (the Verilator C++ API, `--cc`, the `V<top>` model) — [Verilator manual](https://verilator.org/guide/latest/)
- **Declaring the peripheral in a platform** (the `CoSimulated*` type, its bus window) — [Renode docs: platform description format](https://renode.readthedocs.io/en/latest/advanced/platform_description_format.html)

Workflow: verilate your RTL → wrap it with the integration library's bus connector
in a CMake project → point a `renode-verilator` module's `source:` at that project
→ reference the module from a machine's `peripherals:`.

##### C# peripherals

A C# peripheral is a native Renode model — full speed, with direct access to
Renode's register / IRQ / GPIO infrastructure. Use this when you don't have (or
don't need) RTL, e.g. a register-level model of a sensor or controller.

- **Writing a peripheral from scratch** (interfaces, read/write, reset — the canonical guide) — [Renode docs: Writing your own peripheral](https://renode.readthedocs.io/en/latest/advanced/writing-peripherals.html)
- **Register modelling helpers** (`DoubleWordRegisterCollection`, fields, value/read/write callbacks) — [Renode docs: Registers](https://renode.readthedocs.io/en/latest/advanced/registers.html)
- **Hundreds of real models to read and adapt** — the Renode source tree under [`src/.../Emulator/Peripherals`](https://github.com/renode/renode/tree/master/src/Infrastructure/src/Emulator/Peripherals/Peripherals)
- **Wiring the finished class into a machine** (the `.repl` entry, IRQ/GPIO connections) — [Renode docs: platform description format](https://renode.readthedocs.io/en/latest/advanced/platform_description_format.html)

Workflow: implement the class (e.g. an `IDoubleWordPeripheral` with a register
collection, plus `GPIO`/`IKnownSize`/`IGPIOReceiver` as needed) in a **single
`.cs` file** → point a `csharp` module's `source:` at it → reference its
fully-qualified `type` from `peripherals:`. Renode compiles the `.cs` at load
(bundled C# compiler — no .NET SDK), so this is the simplest, version-matched
path; the [`csharp-peripheral`](examples/csharp-peripheral) example is a complete,
runnable starting point. Reach for a `.csproj`/`.dll` only to pre-compile a larger
project — and note that needs a build image carrying both the .NET SDK and
Renode's reference assemblies.

Either kind, once built, is a first-class Renode peripheral: connect it with
[connections](#connection-syntax), bind it to host resources with [mappings](#mappings-global),
and drive it from your [tests](#tests).

> **Version note:** Renode's online docs track its latest release. If you pin an
> older Renode version, cross-check against that release's docs/tag — the
> co-simulation bus interface and some C# APIs evolve between versions.

---

### hubs

Emulation-level connection objects instantiated at the Renode emulation scope, spanning all machines. Declared here and referenced from `connections:`.

```yaml
hubs:
  uartlink: { type: uart }
  canbus:   { type: can }
  lan:      { type: ethernet }
  irqline:  { type: gpio }
  usblink:  { type: usb }
  radio:    { type: wireless }
  ble_net:  { type: ble }
  mesh:     { type: wisun }
```

| Type | Renode object | Operator | Description |
|---|---|---|---|
| `uart` | `CreateUARTHub` | `<->` | Symmetric UART medium; N machines can connect |
| `can` | `CreateCANHub` | `<->` | Symmetric CAN bus |
| `ethernet` | [`CreateSwitch`](https://renode.readthedocs.io/en/latest/networking/wired.html) | `<->` | Ethernet switch |
| `gpio` | `CreateGPIOConnector` | `->` | Directional GPIO link; one source and one destination |
| `usb` | [`CreateUSBConnector`](https://renode.readthedocs.io/en/latest/tutorials/usbip.html) | `->` | Asymmetric USB; device side → hub → controller side |
| `wireless` | [`CreateIEEE802_15_4Medium`](https://renode.readthedocs.io/en/latest/networking/wireless.html) | `<->` | IEEE 802.15.4 mesh (ZigBee, Thread, Matter) |
| `ble` | [`CreateBLEMedium`](https://renode.readthedocs.io/en/latest/networking/wireless.html) | `<->` | Bluetooth Low Energy |
| `wisun` | `CreateWiSUNMedium` | `<->` | Wi-SUN IEEE 802.11ah mesh (smart grid IoT) |

When any hub is present, Hector automatically sets `emulation SetGlobalQuantum` to 10 µs to ensure cross-machine communication is deterministic. Override with the top-level `quantum:` field.

#### USB connections

USB is asymmetric — the arrow direction picks the role. Both forms are equivalent:

```yaml
connections: |
  # chained one-liner — device -> hub -> controller:
  mcu.usb -> usblink -> host.usb

  # …or the two endpoint→hub lines it expands to:
  mcu.usb   -> usblink      # mcu is the USB DEVICE  (periph → hub)
  usblink   -> host.usb     # host is the USB CONTROLLER (hub → periph)
```

Each `usb` hub is a **1-to-1 connector** and can carry only one device. The USB host controller, however, supports multiple devices — each on its own address. To attach multiple devices to the same host, declare one hub per device and point all of them at the same host peripheral:

```yaml
hubs:
  usb_kbd:     { type: usb }
  usb_storage: { type: usb }

connections: |
  board.usb_keyboard -> usb_kbd
  usb_kbd            -> board.usb_host
  board.usb_msc      -> usb_storage
  usb_storage        -> board.usb_host
```

Hector generates a `connector Connect` for the device side and a `RegisterInController` for the host side of each hub. The host enumerates devices sequentially and assigns each a unique USB address.

#### Wireless positioning and range models

Both `wireless` and `ble` (and `wisun`) support optional per-machine positioning and packet delivery models ([Renode docs: wireless networking](https://renode.readthedocs.io/en/latest/networking/wireless.html)). Add raw Renode monitor commands in a machine's `commands:` block:

```yaml
machines:
  nodeA:
    commands: |
      wireless SetPosition sysbus.radio  0.0 0.0 0.0
      wireless SetMediumFunction RangeWirelessFunction  10.0
```

Available medium functions: `SimpleWirelessFunction` (default, all delivered), `RangeWirelessFunction [maxRange]`, `RangeLossWirelessFunction [lossRange txRatio rxRatio]`.

---

### machines

Each entry under `machines:` becomes a named machine in the Renode emulation.

```yaml
machines:
  sensor_mcu:
    backend: renode        # optional; 'renode' is the only supported backend
    platform:
      - platforms/boards/${BOARD}.repl
    repl: |
      ...
    firmware: ${FW}
    peripherals: { ... }
    connections: |
      ...
    mappings: |
      ...
    resc: |
      ...
    commands: |
      ...
```

| Field | Description |
|---|---|
| `backend` | Must be `renode` (default). |
| `platform` | List of [`.repl` platform description](https://renode.readthedocs.io/en/latest/advanced/platform_description_format.html) **file paths**, loaded in order. |
| `repl` | Inline `.repl` platform description **text** (see [below](#inline-repl-and-resc)). |
| `firmware` | ELF file loaded with [`sysbus LoadELF`](https://renode.readthedocs.io/en/latest/basic/machines.html). Omit or set to `none` to skip. |
| `peripherals` | Peripheral instances composed onto this machine. See below. |
| `connections` | Signal wiring scoped to this machine. Covers GPIO, IRQ, and bracket-range connections. Bare peripheral names are accepted. |
| `mappings` | Per-machine host resource bindings. Same syntax as global `mappings:`, but the machine name can be left out (`usart2 -> tcp:3456`). |
| `resc` | Inline `.resc` monitor-script **text** (see [below](#inline-repl-and-resc)). |
| `commands` | Raw [Renode monitor](https://renode.readthedocs.io/en/latest/basic/monitor-syntax.html) commands inserted into the resc after hardware loads. |

> **Note:** `artifacts` is now a **top-level** key, not a per-machine one. See [artifacts](#artifacts).

#### Inline `repl` and `resc`

`platform:` takes *paths*, which only works for boards the released Renode image
already ships. When the board you need exists only on Renode's **master** branch (or
in your own fork), there is no path to point at — so `repl:` and `resc:` take the
file **contents** verbatim instead:

```yaml
machines:
  mcu:
    repl: |                                   # a .repl pasted straight in
      sram: Memory.MappedMemory @ sysbus 0x20000000
          size: 0x10000000
      cpu: CPU.CortexM @ sysbus
          cpuType: "cortex-m3"
          nvic: nvic
    resc: |                                   # a .resc's setup lines
      sysbus ApplySVD @https://.../STM32F103.svd.gz
      sysbus Tag <0x40021000, 0x40021003> "RCC_CR" 0x0A020083
```

- **`repl:`** is written to `.hector/repl/job_<n>_<node>.inline.repl` and loaded with
  `machine LoadPlatformDescription` (Renode only reads platform descriptions from
  disk). It is loaded **after** any `platform:` files.

> **Patching a bundled platform: use `using`, not `platform:`.** Every
> `LoadPlatformDescription` is its **own description scope**, so an entry that another
> file created is only partly reachable from `repl:` — setting a *constructor*
> attribute on it fails with
> `E35: Constructor attribute within entry for variable that is not created`.
> To override one, pull the base platform into the *same* scope from inside `repl:`:
>
> ```yaml
> repl: |
>   using "platforms/boards/nucleo_h753zi.repl"
>
>   nvic:
>       priorityMask: 0xFF        # works: same scope that creates `nvic`
> ```
>
> This is what Renode's own scripts do with `LoadPlatformDescriptionFromString`.
> Use `platform:` alone when you're loading a board as-is, and `using` inside `repl:`
> when you need to patch it. See [`examples/nucleo-h753zi`](examples/nucleo-h753zi).
- **`resc:`** is emitted verbatim into that machine's block, **after** the platform
  and firmware load and **before** `commands:`.

Resulting order inside one machine:

```
mach create "<node>"
machine LoadPlatformDescription @<platform: files>
machine LoadPlatformDescription @<inline repl:>
sysbus LoadELF @<firmware:>
<resc:>
<commands:>
```

> **Do not put `mach create` in `resc:`** — hector already creates the machine. Use
> `resc:` for the lines that follow it (`sysbus ApplySVD`, `sysbus Tag`, macros,
> additional `LoadPlatformDescription`, …).

Both accept a block scalar or a list of lines, and both are interpolated like every
other field. Worked examples:

- [`examples/inline-repl-resc`](examples/inline-repl-resc) — the mechanics, on an
  STM32F103 that boots real firmware.
- [`examples/nucleo-f767zi`](examples/nucleo-f767zi) — the real motivation: a
  **NUCLEO-F767ZI**, which Renode 1.16.1 ships no `.repl` for at all, defined inline
  and running against the pinned release image.
- [`examples/nucleo-h753zi`](examples/nucleo-h753zi) — the other side: a board that
  **is** shipped, loaded via `using` and *patched* inline, booting Hubris.
- [`examples/torizon-verdin-imx8mp`](examples/torizon-verdin-imx8mp) — the
  unmodified Torizon OS image booting to its login prompt on a Toradex Verdin iMX8M
  Plus: prepare steps build a patched Renode and the eMMC image from the official
  Tezi tarball; `renode.docker-flags` caps the container at 3 GB / 4 CPUs.
- [`examples/custom-renode-image`](examples/custom-renode-image) — a prepare step
  builds the Renode image that `renode.image` names; the sim and tests then use it.
- [`examples/external-firmware-resc`](examples/external-firmware-resc) — firmware
  fetched by a `prepare:` step and loaded from `resc:` by a path relative to the
  hectorfile (`sysbus LoadELF @fw/button.elf`).

#### peripherals

Each entry declares one peripheral instance on this machine. The `type` field is either a built-in Renode class name, a `renode-verilator` module name, or a `csharp` module name. Properties are written directly as flat keys alongside `type` and `at`.

```yaml
peripherals:
  uart0:                          # instance name
    type: uartlite                # module name OR built-in Renode class
    at: "sysbus <0x70000000, +0x100>"
    frequency: 100000000          # peripheral property — passed through to the .repl

  extra_ram:
    type: Memory.MappedMemory
    at: "sysbus <0x90000000, +0x10000>"
    size: 0x10000

  Btn:
    type: Miscellaneous.Button
    at: gpioPortC 13
    invert: true

  custom_accel:
    type: my_accel               # references a csharp module
    at: "sysbus <0x40010000, +0x100>"

  nvic:
    type: IRQControllers.NVIC
    at: sysbus 0xE000E000
    priorityMask: 0xF0
    init: |
      someNvicSetupCommand
```

The `at` field is passed through as-is:

| Form | Example | Used for |
|---|---|---|
| Bus range | `sysbus <0x70000000, +0x100>` | Memory-mapped peripherals |
| GPIO port + index | `gpioPortC 13` | Button, LED registered at a pin slot |
| Named object | `sysbus` | CPU, NVIC, and other sysbus-attached peripherals |
| `none` | `none` | Peripherals with no bus registration (e.g. `CombinedInput`) |

The optional `init:` block contains Renode monitor commands that run when the peripheral is loaded during platform initialisation (same as `init:` in a native `.repl` file).

#### connections (per-machine)

All signal wiring for a machine lives here. Peripheral names are automatically scoped to the parent machine; hub names and already-qualified `machine.x` tokens are left unchanged. Three forms are supported:

**Simple GPIO / IRQ** — connects a peripheral output to a GPIO input or NVIC line:
```yaml
connections: |
  Btn -> gpioPortC@13          # Button IRQ → GPIO port C pin 13
  usart2 -> nvic@38            # UART interrupt → NVIC line 38
  usart2 <-> uartlink          # cross-machine hub
  gpioPortA@7 -> irqline       # GPIO pin → cross-machine GPIO hub
```

**Signal name** — `periph.Signal` notation for named IRQ outputs:
```yaml
connections: |
  nvic.IRQ -> cpu@0            # NVIC IRQ output → CPU interrupt input
```

**Bracket range** — compact multi-pin wiring (Renode `.repl` range syntax, passed through as-is):
```yaml
connections: |
  gpioPortC[0-15] -> exti@[0-15]   # all 16 GPIO pins → EXTI lines
  exti[0-4] -> nvic@[6-10]         # EXTI lines 0-4 → NVIC inputs 6-10
```

All three forms can be mixed freely in the same block.

**Peripheral-scoped wiring** — a `connections:` block may also be placed *on a peripheral* (including a nested grouping peripheral), to keep wiring next to the part it concerns. These lines are merged into the machine's wiring at build time — peripheral names are flat in the generated `.repl`, so scoping is purely organizational:

```yaml
machines:
  blackpill:
    peripherals:
      mcu:                         # a grouping peripheral
        type: ...
        peripherals: { cpu: {...}, nvic: {...}, ... }
        connections: |             # wiring scoped to the mcu
          nvic.IRQ -> cpu@0
      button:
        type: Miscellaneous.Button
        at: gpioPortC 13
    connections: |                 # machine-level wiring
      button -> gpioPortC@13
```

Peripheral-scoped connections are always intra-machine; cross-machine hub links must use the machine-level `connections:` block.

#### mappings

Binds an emulated peripheral to a host resource. Same syntax as the global `mappings:` section.

```yaml
mappings: |
  uart4 -> file:results/uart_output.log
  eth0  -> tap:tap0
```

#### artifacts

A **top-level** (global) list of glob patterns. After each job completes, every
matching file is copied into `<output>/artifacts/job_<N>/…` (mirroring its source path,
so same-named files in different directories don't clash). This gives CI a single
directory to upload and a dashboard one place to look.

Two pattern styles are supported:

- **Bare filename** (no `/`, e.g. `*.xml`, `metrics_*.bin`) — searched **recursively**
  across the whole project, skipping hidden dirs (the bundled Renode clone in `.hector/`,
  `.git/`, …) and the artifacts output dir. Use this to grab outputs wherever they land.
- **Path pattern** (`results/*.log`, `logs/**/*.vcd`) — taken literally; `**` matches any
  depth, a single `*` matches one level.

```yaml
artifacts:
  - "*.xml"            # every .xml anywhere (junit.xml, robot_output.xml, …)
  - results/*.log      # .log files directly under results/
  - logs/**/*.vcd      # .vcd files at any depth under logs/
```

Override the YAML list on the command line with `--artifacts` (repeatable); when given,
it replaces the config value — same precedence as `--renode-image`:

```bash
hector test --artifacts 'results/*.bin' --artifacts 'logs/**/*.log'
```

---

### connections (global)

The top-level `connections:` block is the natural home for cross-board wiring.

```yaml
connections: |
  boardA.usart2 <-> uartlink <-> boardB.usart2
  boardA.gpioPortA@7 -> irqline -> boardB.gpioPortB@4
```

See [Connection syntax](#connection-syntax) for the full grammar.

---

### mappings (global)

Binds emulated peripherals to host resources. Each line is `[machine.]peripheral -> backend:param`.

```yaml
mappings: |
  boardA.uart4  -> file:results/uart.log
  boardA.usart2 -> tcp:4567
  boardA.uart1  -> pty:/workspace/ptys/uart1
  boardB.eth0   -> tap:tap0
```

#### backend: file

Redirect UART output to a file using Renode's `CreateFileBackend` ([Renode docs: UART integration](https://renode.readthedocs.io/en/latest/host-integration/uart.html)). Subsequent runs append with a numeric suffix rather than overwriting.

```yaml
boardA.uart4 -> file:results/uart_output.log
```

The file path is relative to the project root. The directory must exist before the simulation starts.

#### backend: tcp

Expose a UART as a TCP socket terminal. With `--net=host` (the default Docker mode) the port is directly accessible from the host.

```yaml
boardA.uart4 -> tcp:4567
```

Connect with: `nc localhost 4567` or `telnet localhost 4567`.

Append `:raw` to suppress IAC telnet negotiation bytes (useful when connecting a tool like `picocom` via `nc`):

```yaml
boardA.uart4 -> tcp:4567:raw
```

#### backend: pty

Expose a UART as a PTY device (Linux/macOS only). Useful for connecting tools that expect a serial device path.

```yaml
boardA.uart4 -> pty:/workspace/ptys/uart4
```

**Note:** PTY devices are created inside the Docker container and are not visible on the host filesystem by default. For host-accessible serial ports, prefer `tcp`. To use PTY from the host, run the container with `--privileged` and bind-mount `/dev/pts`.

#### backend: tap

Connect an Ethernet peripheral to a Linux TAP network interface, bridging the emulated network to the host.

```yaml
boardA.eth0 -> tap:tap0
```

If the interface name is omitted, `tap0` is used. Requires `NET_ADMIN` capability in the container; with `--net=host` this is typically available automatically.

---

### prepare

Steps that produce what the run needs — fetch or compile firmware, generate a file,
**build the Renode image** — run once per job, **before anything uses the Renode
image**: before module builds, the emulation and the tests. They run for `hector run`
and `hector test` (not `export`).

```yaml
renode:
  image: "my-renode:1.16.1"            # built below, used from then on

prepare:
  - name: Build the Renode image
    script: |                          # no image → runs on the host (docker is there)
      docker build -t my-renode:1.16.1 docker/renode

  - name: Compile firmware
    image: arm-gcc:13                  # a toolchain image — no Renode involved
    steps:
      - name: make
        script: make -C firmware

machines:
  mcu:
    firmware: firmware/build/app.elf   # the prepare output, read straight back
```

Each entry has the shape of a `shell` test (`name`, optional `image` and
[`docker-flags`](#extra-docker-flags-docker-flags), and `steps:` or a single-step
`script:`), with two differences:

- **No `image:` runs it on the host**, in the hectorfile's folder (a `shell` test
  without `image:` runs in the Renode image instead, which may not exist yet here).
- **The emulation never runs** during prepare: `requires-machine` (and `type`) are config
  errors. Use a `shell` test with `requires-machine: true` for that.

Entries run in order and stop at the first failure, which also skips the emulation and
tests (exit 1). They share the bind-mounted project, so a file a prepare step writes is
simply there afterwards. Under `hector test`, each entry is reported like a test
(`type: "prepare"`, with its own `report.html`); `hector run` writes no reports — its
output is in the terminal. Under `--no-docker`, every entry runs on the host.

A step without `image:` runs whatever its script says **on your machine**, with your
user's rights. That's no more than hector itself can do (it drives Docker, which is
root-equivalent), but it does mean a hectorfile is code: run hectorfiles you trust, and
in CI, run hector against an isolated Docker daemon (e.g. Docker-in-Docker).

Pass **`--skip-prepare`** to `hector run` or `hector test` to skip the prepare steps and
reuse what an earlier run left behind — e.g. iterating on a test without re-fetching
firmware or rebuilding the image:

```bash
hector test                          # prepares, then tests
hector test --skip-prepare           # tests only, against the existing outputs
```

**`hector prepare`** runs only the prepare steps and exits — 1 if one fails. Use it
when something else starts the emulation: `hector export` never runs prepare steps,
so a tool that launches the exported command runs `hector prepare` first. It takes the
same `-f`, `--set` and `--job` flags as `run`/`test`, and writes no reports.

```bash
hector prepare --job BOARD=stm32f4   # fetch / build what that job needs
hector export  --job BOARD=stm32f4   # then print the command that runs it
```

> **Migration:** the `build:` section was renamed to `prepare:` (`build:`/`setup:` are
> now config errors). An entry without `image:` used to run in the Renode image; it now
> runs on the host, so give it an `image:` if it relied on that.

---

### tests

A list of steps executed sequentially when running `hector test`. All steps run even if one fails. The process exits with code 1 if any step failed.

```yaml
tests:
  - name: Firmware boots
    type: robot
    script: |
      Create Terminal Tester    sysbus.usart2
      Wait For Line On Uart     Board initialized    timeout=30

  - name: Check output
    type: shell
    script: |
      grep -q "Board initialized" results/uart_output.log \
        && echo "PASS" || { echo "FAIL"; exit 1; }
```

There are two test types: **`robot`** (boots the emulation and drives it with Robot
Framework) and **`shell`** (runs a shell script in a container). A `shell` test runs
without an emulation unless it sets `requires-machine: true`, which runs the emulation in
the background for it (see below).

#### type: robot

Each `robot` step can provide its keywords either inline via `script:` or as an external file via `file:`. Both are run with `renode-test` inside the Docker container. ([Renode docs: Robot Framework testing](https://renode.readthedocs.io/en/latest/introduction/testing.html))

##### Inline script

The `script` value is the body of a Robot Framework test case. Hector wraps it in a minimal `.robot` file that auto-loads the generated resc (which starts the emulation) and resets the emulation on teardown:

```yaml
- name: UART echo
  type: robot
  script: |
    Create Terminal Tester    sysbus.usart2
    Write Line To Uart        ping
    Wait For Line On Uart     pong    timeout=10
```

##### External file

Point `file:` at an existing `.robot` file on the host. The file is passed to `renode-test` as-is; Hector injects the generated resc path as the Robot variable `${RESC}` so the file can load the emulation:

```yaml
- name: Boot sequence
  type: robot
  file: tests/boot.robot
```

`tests/boot.robot`:
```robot
*** Settings ***
Library           Collections
Suite Teardown    Reset Emulation

*** Test Cases ***
Boot sequence
    Execute Command    include @${RESC}
    Create Terminal Tester    sysbus.usart2
    Wait For Line On Uart     Board initialized    timeout=30
```

`${RESC}` resolves to the container-absolute path of the generated `.resc` for this job. If `file:` and `script:` are both present, `file:` takes precedence.

##### Loading a snapshot for one test (`snapshot`)

Provide a `snapshot:` path to load a saved Renode state instead of booting from the resc for that specific step. The CLI `--snapshot` flag overrides this field when present.

```yaml
- name: Verify UART after boot
  type: robot
  snapshot: .hector/snapshots/post_boot.save
  script: |
    Execute Command           mach set "boardA"
    Create Terminal Tester    sysbus.usart2    machine=boardA
    Write Line To Uart        ping
    Wait For Line On Uart     pong    timeout=5
```

This is useful when only one test in a suite needs a checkpoint — other tests still boot normally. `snapshot:` is only supported for inline `script:` tests; file-based (`file:`) tests ignore it.

##### Extra renode-test flags (`args`)

Use the optional `args` field to pass additional flags directly to the `renode-test` invocation. Accepts a list or a shell-style string:

```yaml
- name: Verbose UART test
  type: robot
  args: "--loglevel DEBUG"
  script: |
    Create Terminal Tester    sysbus.usart2
    Wait For Line On Uart     Ready    timeout=30

- name: Tagged subset
  type: robot
  args:
    - --include
    - smoke
  file: tests/full_suite.robot
```

Any flag that `renode-test` (Robot Framework) accepts can be passed here — `--include`, `--exclude`, `--loglevel`, `--variable`, `--listener`, etc.

##### Available Robot keywords

| Keyword | Description |
|---|---|
| `Create Terminal Tester    sysbus.usart2    machine=boardA` | Set up a UART listener; `machine=` required in multi-board setups |
| `Wait For Line On Uart    <text>    timeout=<n>` | Assert UART output within N seconds |
| `Write Line To Uart    <text>` | Send a line to a UART |
| `Execute Command    mach set "boardA"` | Change the active machine (multi-board) |
| `Execute Command    <monitor command>` | Send any Renode monitor command |
| `Read From Uart    <n>` | Read N bytes from UART |

Test results (HTML report, JUnit XML) are written to `results/` by default (override with `--output`).

**Note:** each `robot` step is an independent simulation run (a fresh Renode process). Put all assertions that must share the same simulation state inside one step.

#### type: shell

Each step's `script` runs **inside a one-off Docker container** with the project directory bind-mounted at the workspace path, so the script can read/write your files and artifacts. Scripts execute with `set -ex` (exit on error; echo each command), so `+ command` trace lines appear in the output; a non-zero exit fails the step.

```yaml
- name: Validate log in a clean env
  type: shell
  image: python:3.12-slim          # the container to run in
  script: |
    pip install --quiet pyyaml
    python3 tools/check_trace.py results/uart_output.log
```

- **`image:` is optional.** Omit it to use the run's renode image (which already has `python`/`wget`/shell tools) — hector logs which image it picked. Set it to pin a specific toolchain.
- **`docker-flags:`** adds `docker run` flags (mounts, `--device`, env, …) to this test's containers only. See [extra Docker flags](#extra-docker-flags-docker-flags).
- **`--no-docker`** runs the script on the host instead, ignoring `image:` (with a warning). See [Running without Docker](#running-without-docker---no-docker).

##### `requires-machine: true` — the emulation in the background

By default a `shell` test runs without Renode (compile, fetch, lint, check a file), so it
also works when the config defines **no machines at all**. Set `requires-machine: true` to
run the test **against a live emulation**:

```yaml
- name: Talk to the running firmware
  type: shell
  requires-machine: true
  image: python:3.12-slim
  script: |
    python3 checks/monitor.py 'mach set "mcu"' 'sysbus GetSymbolAddress "main"'
```

For such a test hector:

1. starts Renode headless in the background (its own container, same image, mounts,
   `renode.docker-flags` and host network as `hector run`; on the host under
   `--no-docker`),
2. loads the generated resc through Renode's monitor and waits until it's done — a
   resc error (e.g. a missing ELF) fails the test before any step runs,
3. runs the steps with **`HECTOR_MONITOR_PORT`** set to the monitor's TCP port,
4. stops Renode after the last step and saves its log as `renode.log` next to the
   test's `report.html`.

Steps reach the emulation over the host network: the monitor on
`localhost:$HECTOR_MONITOR_PORT` (send a newline first to get a prompt — only the
first client gets a banner), plus any `tcp:` [mappings](#mappings) — e.g.
`usart2 -> tcp:3456:raw` under the machine puts its console on `localhost:3456`. A
`pty` mapping won't work here: the pty exists only inside Renode's container. With
`--snapshot` (or a test `snapshot:`), the snapshot is loaded and started instead of
the resc — so host-side [mappings](#mappings) (`tcp:`, `pty:`, `file:` terminals)
don't exist then: Renode doesn't save them, and the resc that creates them isn't run.
See [`examples/background-sim`](examples/background-sim) for a working monitor client.

> **Migration:** `requires_sim` was renamed to `requires-machine` (a config error with
> the fix). It now defaults to `false`.

A test that needs the emulation but finds no machine defined is skipped and marked
failed.

> **Migration:** the old `bash` and `docker` test types are now both `shell` (a `bash`
> step → a `shell` step running on the host under `--no-docker`; a `docker` step → a
> `shell` step with an `image:`). Old configs still run, with a rename warning.

---

### quantum

Override the emulation-wide time quantum (in seconds). The quantum controls how often Renode synchronises virtual time across machines and is only relevant in multi-machine jobs with hubs. ([Renode docs: time framework](https://renode.readthedocs.io/en/latest/advanced/time_framework.html))

```yaml
quantum: 0.0001    # 100 µs
```

If absent and any hub is declared, the framework defaults to `0.00001` (10 µs). If no hubs are present, the quantum is not set and Renode uses its internal default.

---

### ci

An **optional** block describing CI pipelines (when and how to run this config in
continuous integration). The CLI itself never acts on `ci:` — no `hector` command
reads it — it only validates the block's shape so a misconfiguration is caught
early. The field is consumed by [Hector CI](https://hector-ci.com), the companion
server that runs this same `.hector.yaml` (there is no separate `hector-ci.yml`);
its full reference lives with that product. A minimal shape:

```yaml
ci:
  embedded-tests:
    when:
      branch: [main, "release/*"]
      event: [push, pull_request, manual]
    reporters: [json, junit]
    timeout: 30m
```

If you only ever drive `hector` yourself (locally or from your own CI runner),
you can omit `ci:` entirely.

---

## Connection syntax

Pin and line numbers use Renode's `@` notation throughout.

### Intra-machine signal wiring

Connects the output of one peripheral to the input of another on the same machine. Generates a Renode [platform description](https://renode.readthedocs.io/en/latest/advanced/platform_description_format.html) **updating entry** keyed on the source peripheral.

```
<machine>.<source>               -> <machine>.<dest>@<pin>
<machine>.<source>@<srcPin>      -> <machine>.<dest>@<pin>
<machine>.<source>.<Signal>      -> <machine>.<dest>@<pin>
<machine>.<source>[<range>]      -> <machine>.<dest>@[<range>]
```

Inside a per-machine `connections:` block the machine prefix is optional — bare names are scoped to the parent machine automatically:

```yaml
connections: |
  button -> gpioPortC@13            # peripheral → GPIO pin
  gpioPortA@5 -> led@0             # GPIO pin → LED input
  nvic.IRQ -> cpu@0                # named signal output
  gpioPortC[0-15] -> exti@[0-15]  # bracket range: 16 pins in one line
  exti[0-4] -> nvic@[6-10]        # bracket range with offset destination
```

### Cross-machine symmetric hub (uart / can / ethernet / wireless / ble / wisun)

Chained two-endpoint shorthand, or one endpoint↔hub line each — equivalent:
```
<nodeA>.<periph> <-> <hub> <-> <nodeB>.<periph>

# …or as separate lines (and the only form for 3+ endpoints):
boardA.usart2 <-> uartlink
boardB.usart2 <-> uartlink
boardC.usart2 <-> uartlink
```

### Cross-machine GPIO (directional)

Left side is the SOURCE, right side is the DESTINATION. Chained one-liner, or the two
endpoint→hub lines it expands to — equivalent:
```
<nodeA>.<port>@<pin> -> <gpiohub> -> <nodeB>.<port>@<pin>

# …or split:
boardA.gpioPortA@7 -> irqline        # source
irqline -> boardB.gpioPortB@4        # destination
```

### USB (asymmetric)

Chained one-liner, or the two equivalent endpoint→hub lines:
```
<device_node>.<periph> -> <usbhub> -> <host_node>.<periph>

# …or split:
<device_node>.<periph> -> <usbhub>
<usbhub> -> <host_node>.<periph>
```

---

## Interpolation

`${NAME}` is expanded anywhere in the YAML (keys, values, strings, block scalars). Precedence (highest wins):

1. Matrix variables for the current job
2. `arguments:` values (or env var override of the same name)
3. Framework variables: `${RENODE_DIR}`, `${INTEGRATION_DIR}`

`${RENODE_DIR}` and `${INTEGRATION_DIR}` are container-absolute paths (`/workspace/.hector/renode` and `/workspace/.hector/renode-verilator-integration`). They are primarily useful in module `source:` fields.

**YAML quoting rule:** `${...}` inside a YAML flow sequence (`[...]`) or flow mapping (`{...}`) will cause a parse error because `{` is a reserved character in flow context. Use block style instead:

```yaml
# Wrong — will fail to parse
platform: [ platforms/boards/${BOARD}.repl ]

# Correct
platform:
  - platforms/boards/${BOARD}.repl
```

---

## Generated artifacts

Everything the framework generates lives under `.hector/` and is safe to delete (it will be rebuilt on the next run). Add this directory to `.gitignore`.

```
.hector/
├── renode/                        # managed Renode clone
├── renode-verilator-integration/  # managed integration clone
├── build/
│   ├── modules/<name>/            # compiled .so / .dll per module
│   └── instances/<machine>__<inst>.so  # per-instance .so copies (verilator only)
├── repl/
│   └── job_<N>_<machine>.gen.repl   # generated platform descriptions
├── resc/
│   └── job_<N>.resc               # generated emulation scripts
└── tests/
    └── job_<N>_test_<M>.robot    # generated Robot Framework wrappers

results/                           # test + simulation output (override with --output)
├── test_0_<name>/                 # one directory per test (robot / shell alike)
│   ├── report.html               # human-readable report (all test types)
│   ├── log.html                  # robot only: full interactive log
│   ├── robot_output.xml          # robot only: native Robot Framework XML
│   └── renode.log                # shell + requires-machine: true only: the emulation's log
├── test_1_<name>/
│   └── report.html
├── artifacts/                     # files collected by the top-level 'artifacts:' globs
│   └── job_<N>/…                 # mirrors each source path (avoids name clashes)
├── junit.xml                      # aggregated JUnit XML  (--reporters junit)
└── manifest.json                  # machine-readable result index  (--reporters json)
```

`manifest.json` is the structured surface for dashboards / CI: one entry per test with
its `status`, `duration`, `commands`, and relative paths to its detail artifacts
(`report_html`, and for robot also `log_html` / `robot_xml`). Enable it with
`--reporters junit --reporters json`.

---

## Complete example

```yaml
version: "0.2"
renode:
  image: "1.16.1"

matrix:
  variables:
    VARIANT: ["default"]

arguments:
  BOARD: stm32f4_discovery
  FW: stm32f4_test.elf

artifacts:
  - results/*.log

modules:
  uartlite:
    kind: renode-verilator
    type: CoSimulated.CoSimulatedUART
    source: "${INTEGRATION_DIR}/samples/uartlite"

hubs:
  uartlink: { type: uart }
  irqline:  { type: gpio }

machines:
  boardA:
    platform:
      - platforms/boards/${BOARD}.repl
    firmware: ${FW}
    peripherals:
      uart0:
        type: uartlite
        at: "sysbus <0x70000000, +0x100>"
        frequency: 100000000
      Btn:
        type: Miscellaneous.Button
        at: gpioPortC 13
    connections: |
      Btn -> gpioPortC@13
    mappings: |
      uart4 -> file:results/${VARIANT}_uart.log

  boardB:
    platform:
      - platforms/boards/${BOARD}.repl
    firmware: ${FW}

connections: |
  boardA.usart2 <-> uartlink <-> boardB.usart2
  boardA.gpioPortA@7 -> irqline -> boardB.gpioPortB@4

prepare:
  - name: Fetch firmware
    image: alpine:3.19
    script: |
      wget -q https://example.com/${FW} -O ${FW}

tests:
  - name: Firmware boots
    type: robot
    script: |
      Create Terminal Tester    sysbus.usart2
      Wait For Line On Uart     Board initialized    timeout=30

  - name: UART echo
    type: robot
    script: |
      Create Terminal Tester    sysbus.usart2
      Write Line To Uart        ping
      Wait For Line On Uart     pong    timeout=10

  - name: Check log
    type: shell
    script: |
      grep -q "Board initialized" results/${VARIANT}_uart.log \
        && echo "PASS" || { echo "FAIL"; exit 1; }
```

Run it:

```bash
hector run                              # simulate
hector run --debug boardA:3333          # debug boardA
hector test                       # run tests
hector test --fail-fast           # stop on first failure
hector run --job VARIANT=default        # run only one matrix combination
BOARD=stm32f7_discovery hector run      # override argument via env
```

---

## License

Hector (the CLI) is licensed under the **GNU Affero General Public License v3.0
or later** (AGPL-3.0-or-later). The full text is in [LICENSE](LICENSE); see
[LICENSING.md](LICENSING.md) for what that means in practice — notably that your
own firmware, `.hector.yaml` configs, and test files are **not** derivative
works of Hector and carry no license obligation from it.

A separate commercial license is available for the **Hector CI** server; contact
`info@hector-ci.com`.
