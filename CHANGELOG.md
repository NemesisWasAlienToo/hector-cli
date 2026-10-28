# Changelog

All notable changes to `hector-cli`. Versions follow [semver](https://semver.org/);
while hector is 0.x, a minor version may contain breaking changes (marked
**Breaking**).

## 0.13.0 — 2026-10-28

### Added
- `$PROJECT`: a Renode monitor variable set to the hectorfile's folder in every
  generated resc (snapshot loaders too). Save snapshots with
  `Save $PROJECT/snapshots/x.save`; `hector run` prints this hint.

### Changed
- `prepare:` steps always stream their output. Before, they streamed only under
  `hector test --live`, so under `hector run` (which has no `--live`) a long step, e.g.
  the Verdin example's Renode build, printed nothing until it finished.
- Renode containers run with `--ulimit core=0`: a crashing Renode no longer writes a
  multi-hundred-MB core dump into the project. `renode.docker-flags` can override it.

### Fixed
- Snapshots: `Save @post_boot.save` from `hector run`'s monitor failed with "Access to
  the path '/opt/renode/…' is denied" (Renode writes relative paths into its install
  folder) and then crashed Renode. `$PROJECT` gives a working path; changing Renode's
  working folder instead was tried and rejected — it breaks saving machines with
  Python peripherals, whose scripts Renode finds relative to its install folder.
- Loading a snapshot (`--snapshot`, a test's `snapshot:`, robot or `requires-machine`
  shell tests) now recreates the host-side mappings (`tcp:`, `pty:`, `file:`, `tap:`),
  which aren't part of a snapshot — e.g. a `tcp:` console port was missing after a
  load. C# assemblies are imported before `Load`.

### Docs
- Examples: READMEs for `multi-machine-uart-link`, `network-ping`, `stm32f103-full`,
  `yaml-defined-mcu` and `zedboard-net`; `zedboard-net` no longer claims hector can't
  grant the TAP's `NET_ADMIN` (it does, automatically); `docker-runner`'s run
  instructions use the repo's paths; `multi-machine-uart-link` describes itself and
  its shell test has a real name.

### Examples
- `torizon-verdin-imx8mp`: a tlib fix for TLB flushes from generated code, which
  caused an intermittent `Assert not met ... env->current_tb != NULL` abort (likeliest
  after `logLevel 0`). Rebuild the image: `hector prepare`.

## 0.12.0 — 2026-10-27

### Added
- `hector prepare`: run only the `prepare:` steps (no emulation, no tests) for one job;
  exit 1 if one fails. For tools that start the emulation themselves from
  `hector export`, which never runs prepare steps.

### Docs
- README: an Examples index listing every example (seven weren't linked anywhere).

## 0.11.0 — 2026-10-27

### Added
- `examples/torizon-verdin-imx8mp`: the official Torizon OS image booting to its login
  prompt on an emulated Toradex Verdin iMX8M Plus, with a patched Renode built in
  `prepare:`.
- CI job `examples`: runs `hector test` on the quick examples against real Docker and
  Renode, through a Docker-in-Docker service.

### Changed
- **Breaking:** schema version `"0.2"`. A `version: "0.1"` config is an error that lists
  what changed; set `version: "0.2"` after migrating.
- **Breaking:** `requires_sim` is renamed to `requires-machine`; the old key is an error
  with the fix.
- `hector run` writes no reports (no `junit.xml`, no prepare `report.html`); prepare
  output stays in the terminal. Use `hector test` for reports.
- With a remote Docker daemon (`DOCKER_HOST=tcp://…`, e.g. CI's DinD), hector connects
  to the background sim's monitor on that host instead of `localhost`.

### Fixed
- `requires-machine: true` under `--no-docker` crashed (the monitor port was passed to
  the environment as a number).

## 0.10.0 — 2026-10-27

### Added
- `--skip-prepare` on `hector run` and `hector test`: skip the `prepare:` steps and
  reuse what an earlier run prepared.
- `docker-flags:` on `shell` tests and `prepare:` steps (with an `image:`): extra
  `docker run` flags (mounts, `--device`, env, …) for that test's or step's
  containers only.
- `renode.docker-flags` / `--renode-docker-flags`: flags for the Renode containers
  only (the emulation, robot tests, the background sim, module builds).

### Changed
- **Breaking:** `renode` is a section: `renode:` with `image:` (a version or any Docker
  image) and optional `docker-flags:` under it. The string form `renode: "1.16.1"` is
  a config error that shows the fix. `--renode` is now `--renode-image`.
- **Breaking:** the top-level `docker_args:` and `--docker-args`, which reached every
  container, are removed; `docker_args:` is a config error pointing to
  `renode.docker-flags` and the per-test/step `docker-flags:`.
- `examples/docker-runner` passes its expected sum to a test through `docker-flags`.

## 0.9.0 — 2026-10-27

### Added
- `prepare:` — shell steps that run before anything uses the Renode image (module
  builds, the emulation, tests), for `hector run` and `hector test` (not `export`).
  A step without `image:` runs on the host, so it can `docker build` the image that
  `renode:` names; with `image:` it runs in that container. The emulation never runs
  during prepare. Steps stop at the first failure, which skips the run (exit 1), and
  are reported like tests (`type: "prepare"`).
- `renode:` / `--renode` — one field for the Renode to use: a version (`1.16.1` →
  `antmicro/renode:1.16.1`) or any Docker image reference.
- `examples/custom-renode-image`: a prepare step builds the Renode image the run uses.

### Changed
- **Breaking:** `renode_version:` / `renode_image:` and `--renode-version` /
  `--renode-image` are replaced by `renode:` / `--renode`; the old keys are config
  errors.
- **Breaking:** `build:` (removed in 0.8.0) returns as `prepare:`; `build:` / `setup:`
  are config errors pointing to it. A step without `image:` now runs on the host
  instead of in the Renode image.
- The examples fetch or generate their inputs in `prepare:` instead of a first test.

## 0.8.0 — 2026-10-27 (git only, not published to PyPI)

### Added
- `requires_sim: true` on a `shell` test starts the emulation headless in the
  background for the whole test. Steps reach its monitor on
  `localhost:$HECTOR_MONITOR_PORT` and `tcp:` mappings on `localhost:<port>`; Renode's
  log is saved as `renode.log` next to the test's report.
- `examples/background-sim` and `examples/external-firmware-resc`.

### Changed
- **Breaking:** the `build:` section was removed (see 0.9.0 for its return as
  `prepare:`).
- **Breaking:** `shell` tests no longer need the emulation by default
  (`requires_sim` defaults to `false`).

### Fixed
- Relative paths in `platform:`, `firmware:`, `resc:` and `commands:` resolve from the
  hectorfile's folder: the generated resc starts with `path add @<that folder>`.
  Before, they failed under `hector test`, where renode-test starts Renode in its
  install folder.
- `machines.<name>.mappings` were validated but ignored; they are now applied, and the
  machine name may be left out (`usart2 -> tcp:3456`).
- Containers running as a host UID other than 1000 crashed Renode at startup (its
  home folder wasn't writable). Hector now sets `HOME=/tmp` unless your docker args
  set `HOME`.

## 0.7.1 — 2026-10-27

### Fixed
- renode-test runs from the test's results folder, so its reports land in
  `results/` instead of the project root.
- A warning when docker args are given under `--no-docker` (they're ignored).

## 0.7.0 — 2026-10-26

### Changed
- `--workspace-mount` mounts the hectorfile's folder and runs there. The folder hector
  runs from (`.hector/`, `--output`) is also mounted when it's outside it.

## 0.6.0 — 2026-10-26

### Added
- `docker_args:` / `--docker-args`: extra flags (mounts, env) for every `docker run`.

### Changed
- Steps, Renode and renode-test run in the hectorfile's folder, and paths in the
  hectorfile resolve against it.

## 0.5.0 — 2026-10-26

### Changed
- Every container runs with host networking (`--net=host`); the ignored `-p` port
  publishing was dropped.

## 0.4.0 — 2026-10-26

### Added
- `renode_image:` / `--renode-image` to run any Renode Docker image.

## Earlier

Before 0.4.0, changes were tracked only in git history: `hector clean`, the test
suite, inline `repl:`/`resc:`, `--no-start`, Windows support and the first examples.
