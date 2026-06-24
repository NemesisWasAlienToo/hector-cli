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
- [Quick start](#quick-start)
- [Invocation modes](#invocation-modes)
- [Configuration reference](#configuration-reference)
  - [Top-level fields](#top-level-fields)
  - [arguments](#arguments)
  - [matrix](#matrix)
  - [modules](#modules)
  - [hubs](#hubs)
  - [machines](#machines)
    - [peripherals](#peripherals)
    - [connections (per-machine)](#connections-per-machine)
    - [mappings](#mappings)
    - [artifacts](#artifacts)
  - [connections (global)](#connections-global)
  - [mappings (global)](#mappings-global)
  - [build](#build)
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
```

Generated files go in `.hector/` — add it to your `.gitignore`. The Renode **binary** runs from the Docker image; the Renode **source** is only cloned when a config needs it (see [Renode source checkout](#renode-source-checkout)).

---

## Invocation modes

| Command | Behaviour |
|---|---|
| `hector run` | Run simulation interactively (Renode monitor) |
| `hector run -f board.yaml` | Read a config file other than `.hector.yaml` (`-f`/`--file`; works on every command) |
| `hector run --set BIN=fw.elf` | Override a config argument at the command line |
| `hector run --set BIN=fw.elf --set BOARD=nucleo` | Override multiple arguments |
| `hector run --debug boardA:3333` | Halt a CPU and open a GDB server |
| `hector run --debug boardA:3333 --debug boardB:3334` | Halt multiple CPUs on different ports |
| `hector run --renode-args '--console'` | Pass extra flags verbatim to Renode |
| `hector run --gather-execution-metrics` | Enable Renode's CPU execution profiler for all machines |
| `hector run --gather-execution-metrics boardA` | Enable profiler for one specific machine |
| `hector run --gather-execution-metrics boardA --gather-execution-metrics boardB` | Enable profiler for selected machines |
| `hector run --renode-version 1.16.1` | Override the Renode version from `.hector.yaml` |
| `hector run --renode-dir /cache/renode` | Use/cache the Renode source checkout at this path (only fetched when needed) |
| `hector run --renode-integration-dir /cache/integration` | Likewise for the verilator-integration checkout |
| `hector run --no-docker` | Use locally installed `renode` / `renode-test` instead of Docker |
| `hector run --workspace-mount /mnt` | Override the container path the project root is mounted at |
| `hector run --snapshot path/to/snapshot.save` | Load a snapshot instead of booting from the resc |
| `hector run --snapshot snap.save --renode-version 1.16.1` | Load a snapshot without a `.hector.yaml` |
| `hector test` | Run the `tests:` section; exit 1 on any failure |
| `hector test --fail-fast` | Stop after the first failing test |
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
| `hector --version` | Print the tool version |

`hector` is structured as subcommands: `run` (simulate), `test` (run the `tests:`
section), `export` (emit the command without running it), plus `init` and
`validate`. Run `hector <command> --help` for the flags each one accepts.

Every command reads (or, for `init`, writes) `.hector.yaml` by default. Point it
at a different file with **`-f` / `--file`** — useful when one project keeps
several configs (e.g. `ci.hector.yaml`, `local.hector.yaml`):

```bash
hector test -f ci.hector.yaml
hector run  --file boards/nucleo.yaml
```

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

Connect with:
```bash
arm-none-eabi-gdb firmware.elf
(gdb) target extended-remote localhost:3333
(gdb) break main
(gdb) continue
```

Or use VS Code with the Cortex-Debug extension pointed at `localhost:3333`.

### Test mode (`hector test`)

Runs every step in the `tests:` section in declaration order. All steps run to completion even if one fails. The process exits with code 1 if any step failed, making it usable directly in CI.

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

When used with `--renode-version`, no `.hector.yaml` is needed at all — useful for inspecting a snapshot outside of any project:

```bash
hector run --snapshot /path/to/snapshot.save --renode-version 1.16.1
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

Launches one Renode emulation per job in the Docker container. Each machine declared in the YAML becomes a named Renode machine in that emulation. The Renode monitor is interactive; type `help` at the prompt for available commands.

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

#### Running without Docker (`--no-docker`)

Call the locally installed `renode` and `renode-test` binaries directly instead of launching a Docker container. `build:` steps and `shell` tests also run on the host (their `image:` is ignored, with a warning), as do module builds.

```bash
hector run --no-docker
hector test --no-docker
```

Requires `renode` and `renode-test` to be on your `PATH` — and, since images are ignored, whatever toolchains your `build:`/`shell` scripts call (e.g. a compiler). **`--no-docker` and `--workspace-mount` are mutually exclusive** — they both control how the project root is made accessible and cannot be combined.

#### Overriding the Renode version (`--renode-version`)

Override the `renode_version:` from `.hector.yaml` without editing the file:

```bash
hector run --renode-version 1.15.0
hector test --renode-version 1.15.0
```

When combined with `--snapshot` in simulation mode, `.hector.yaml` is not required at all — the two flags together are self-contained:

```bash
hector run --snapshot path/to/snapshot.save --renode-version 1.16.1
```

#### Renode source checkout

Running a simulation does **not** need the Renode source — the binary and its bundled platforms come from the `antmicro/renode` Docker image. Hector clones the Renode source (and the verilator-integration repo) into `.hector/` **only when a config actually needs it**:

- it builds `modules:` (Verilated / C# co-simulated peripherals, which compile against the Renode source), or
- it interpolates `${RENODE_DIR}` / `${INTEGRATION_DIR}`.

For everything else — plain or YAML-defined machines, firmware URLs, `build:`/`shell` steps — nothing is cloned, so runs start immediately.

When the source *is* needed, point hector at a cached or shared checkout instead of re-cloning each time:

```bash
hector test --renode-dir /cache/renode --renode-integration-dir /cache/renode-integration
```

An existing directory is reused as-is; a missing one is cloned into. The location may live **outside the project** (e.g. a persistent CI cache) — hector bind-mounts an out-of-tree checkout into every container 1:1 (at the same path), so `modules:` builds and `${RENODE_DIR}` references still resolve. A path under the project works too (it's covered by the normal workspace mount).

#### Overriding the workspace mount path (`--workspace-mount`)

By default the project root is bind-mounted into the container at the **same absolute path** as on the host (e.g. `/home/user/projects/myboard`), so paths look identical inside and outside the container. Override this only if the host path is unavailable at that location inside the image:

```bash
hector run --workspace-mount /workspace
```

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

Builds everything a run would — the per-machine `.repl` files and the emulation
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
| `version` | No | Schema version (currently `"0.1"`). Warns if unrecognised. |
| `renode_version` | Yes | Renode version, no leading `v` (e.g. `1.16.1`). Selects both the git tag for cloning and the Docker image tag. |
| `arguments` | No | Scalar defaults, overridable by env var or `--set`. |
| `build` | No | Pre-sim shell steps run once per job in containers (compile firmware, fetch/generate files, …). Interpolated with the job's arguments/matrix variables. |
| `matrix` | No | Cross-product job expansion. |
| `modules` | No | Verilated / C# peripheral type definitions. |
| `hubs` | No | Emulation-level connection objects (uart, can, ethernet, gpio, usb, wireless, ble, wisun). |
| `machines` | No | The machines to simulate. Optional: a config may be build-only or run sim-independent (`requires_sim: false`) shell tests. `run`/`export` and sim-backed tests require at least one. |
| `connections` | No | Global signal wiring. |
| `mappings` | No | Emulated peripheral → host resource bindings. |
| `tests` | No | Test steps run by `hector test`. |
| `quantum` | No | Override the global time quantum (seconds). |
| `ci` | No | CI pipeline definitions: when and how a CI server runs this config. |

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

Builds (or locates) a C# Renode peripheral plugin. The resulting `.dll` is loaded at emulation scope via `i @<path>` before any machine block, making the type available to all machines in the job. ([Renode docs: writing peripherals](https://renode.readthedocs.io/en/latest/advanced/writing-peripherals.html))

Two usage modes:

**Pre-built DLL** — point `source` directly at the `.dll`:

```yaml
modules:
  my_periph:
    kind: csharp
    type: My.Namespace.MyPeripheral
    source: prebuilt/my_periph.dll
```

**Build from source** — point `source` at a directory containing a `.csproj`. `dotnet build` runs inside the Renode container (which ships with Mono/dotnet):

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
| `type` | Yes | Fully qualified C# class name as it will appear in the generated `.repl`. |
| `source` | Yes | Path to a `.csproj` directory **or** a pre-built `.dll` file. |

The `type` field is what you would write in a `.repl` entry — it must match the class exposed by the compiled DLL. Multiple peripherals in the same job can share one DLL (different `type` values, same `source`); Hector emits a single `i @<path>` import even when multiple instances reference the same DLL.

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
    firmware: ${FW}
    peripherals: { ... }
    connections: |
      ...
    mappings: |
      ...
    commands: |
      ...
```

| Field | Description |
|---|---|
| `backend` | Must be `renode` (default). |
| `platform` | List of [`.repl` platform description](https://renode.readthedocs.io/en/latest/advanced/platform_description_format.html) files loaded in order. |
| `firmware` | ELF file loaded with [`sysbus LoadELF`](https://renode.readthedocs.io/en/latest/basic/machines.html). Omit or set to `none` to skip. |
| `peripherals` | Peripheral instances composed onto this machine. See below. |
| `connections` | Signal wiring scoped to this machine. Covers GPIO, IRQ, and bracket-range connections. Bare peripheral names are accepted. |
| `mappings` | Per-machine host resource bindings. Same syntax as global `mappings:`. |
| `commands` | Raw [Renode monitor](https://renode.readthedocs.io/en/latest/basic/monitor-syntax.html) commands inserted into the resc after hardware loads. |

> **Note:** `artifacts` is now a **top-level** key, not a per-machine one. See [artifacts](#artifacts).

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
it replaces the config value — same precedence as `--renode-version`:

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

### build

Pre-simulation steps that produce the inputs a run/test needs — compile firmware, fetch a binary, generate a file. Each step runs **in a container** with the project bind-mounted (the same engine as the `shell` test type), once per job, *before* the machines are built. Steps run in order and the job aborts on the first failure (the sim depends on their output).

```yaml
build:
  - name: Compile firmware
    image: arm-gcc:13                 # a toolchain image — no Renode involved
    steps:
      - script: make -C firmware

  - name: Fetch bootloader            # no image → the run's renode image (logged)
    script: |
      wget -O boot.bin https://example.com/boot.bin

machines:
  mcu:
    firmware: firmware/build/app.elf   # the build output, read straight back
```

Same shape as a `shell` test (`name`, optional `image`, and `steps:` or a single-step `script:`). Build steps and the sim/tests all share the one bind-mounted project directory at the same path, so **a file a build step writes is simply there for the sim and tests** — reference it by its normal path, no copying or declaration. Under `--no-docker`, build steps run on the host (image ignored).

Build steps **report like tests**: each block becomes one entry (`type: "build"`) in the JUnit/JSON reports with its own `report.html`, alongside the test results. A failing build step marks the job failed and skips the simulation/tests.

> **Migration:** `build:` replaces the old host-side `prepare:` script. A one-line
> `prepare:` becomes a one-step `build:` (no `image:` → runs in the renode image, which
> has the usual shell tools). Old `prepare:`/`setup:` keys still parse, with a rename
> warning.

> **Tip:** containers may write build outputs as `root`. If later host steps (git, rm)
> trip on ownership, that's the known cause; gitignore generated outputs like `.hector/`.

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
Framework) and **`shell`** (runs a shell script in a container). By default every
test runs *after* the simulation; a `shell` test that doesn't need Renode can opt out
with `requires_sim: false` (see below).

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
- **`--no-docker`** runs the script on the host instead, ignoring `image:` (with a warning). See [Running without Docker](#running-without-docker---no-docker).

##### `requires_sim: false`

By default a `shell` test runs after the simulation and counts as needing it. Set `requires_sim: false` for a check that's independent of Renode (lint a file, validate a generated artifact, run a host tool). Such a test runs even when the config defines **no machines at all** — handy for build-and-check pipelines:

```yaml
- name: Lint the generated config
  type: shell
  requires_sim: false
  image: python:3.12-slim
  script: |
    python3 -m yamllint .hector.yaml
```

A test that needs the simulation but finds no machine defined is skipped and marked failed, with a note telling you to add a machine or set `requires_sim: false`.

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
├── build_0_<name>/                # one directory per build: step (reported like a test)
│   └── report.html
├── test_0_<name>/                 # one directory per test (robot / shell alike)
│   ├── report.html               # human-readable report (all test types)
│   ├── log.html                  # robot only: full interactive log
│   └── robot_output.xml          # robot only: native Robot Framework XML
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
version: "0.1"
renode_version: "1.16.1"

matrix:
  variables:
    VARIANT: ["default"]

arguments:
  BOARD: stm32f4_discovery
  FW: stm32f4_test.elf

# Pre-sim build steps, run once per job (in containers) before the machines are built.
build:
  - name: Fetch firmware
    script: |                         # no image → the run's renode image (has wget)
      wget -q https://example.com/${FW} -O ${FW}

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
