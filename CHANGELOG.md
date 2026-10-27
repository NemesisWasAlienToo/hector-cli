# Changelog

All notable changes to `hector-cli`. Versions follow [semver](https://semver.org/);
while hector is 0.x, a minor version may contain breaking changes (marked
**Breaking**).

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
