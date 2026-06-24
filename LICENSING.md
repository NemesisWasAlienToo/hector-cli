# Licensing

The **hector CLI** (this `cli/` package) is licensed under the **GNU Affero General
Public License, version 3 or later (AGPL-3.0-or-later)**. The full text is in
[LICENSE](LICENSE). Each source file also carries an
`SPDX-License-Identifier: AGPL-3.0-or-later` header.

## What the AGPL means for you

- **Use it freely** — run hector to build, simulate, and test your firmware, privately
  or commercially, at no cost.
- **Modify and redistribute** — you may change hector and pass it on, as long as you do
  so under the AGPL and make your modified source available to its recipients.
- **Network use (§13)** — if you run a *modified* hector as a network-accessible service
  (e.g. a hosted CI offering), you must offer that service's users the corresponding
  source of your modified hector.

### Your firmware and configs are **not** affected

Using hector does **not** place your code under the AGPL. hector invokes Renode and
Verilator as **separate processes/containers** and merely **reads** your `.hector.yaml`,
firmware, and platform files — none of which become derivative works of hector. The
copyleft applies to hector's own source, not to the inputs you run through it or the
firmware you test with it.

## Commercial license

For organizations that cannot accept the AGPL's terms — or that want to embed a modified
hector in a closed-source product or hosted service without §13 obligations — a separate
**commercial license** is available (Hector Enterprise), which also includes enterprise
features and support.

> Commercial licensing: **info@hector-ci.com** · <https://hector-ci.com>

The AGPL and the commercial license are offered under a dual-licensing model: the same
code, your choice of terms.

## Contributing

hector is **not accepting external contributions at this time.** All copyright is held
by the project, which keeps the dual-licensing model clean (the project can offer the
commercial license without needing rights from outside contributors).

If this changes, a Contributor License Agreement (CLA) — or the DCO plus copyright
assignment — will be required *before* any outside contribution is merged, so that
contributed code can also be offered under the commercial license.

## Third-party components

hector depends on, but does not bundle or statically link, these tools — so their
licenses do not extend to hector or to your firmware:

| Component | License | How hector uses it |
|---|---|---|
| Renode | MIT | Run as a separate binary, from the `antmicro/renode` Docker image |
| Verilator | LGPL-3.0 / Artistic | Invoked to build co-simulation modules in a container |
| PyYAML | MIT | Imported by the CLI (AGPL-compatible) |

## Scope

This AGPL grant covers the **hector CLI** only. Other components in this repository
(e.g. the CI backend and dashboard under `ci/`) may be licensed separately; see their
own license files if/when present.
