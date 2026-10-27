# Firmware loaded from `resc:`

The firmware comes from **outside** the generated resc: the first test (`type: shell`)
downloads it into `fw/` next to `.hector.yaml`, and the machine's `resc:` loads it itself with a
path relative to the hectorfile:

```yaml
resc: |
  sysbus LoadELF @fw/button.elf
```

No `firmware:` field is involved, so hector passes the line to Renode unchanged and
Renode resolves the path.

## How the path resolves

Renode looks up a relative `@path` in its working folder, then in its search path.
Under `hector test`, renode-test starts Renode in its install folder, so on its own
`@fw/button.elf` would not be found. Hector therefore starts every generated resc with

```
path add @<this folder>
```

which puts the hectorfile's folder first in Renode's search path. The same line makes
`hector run` and `--no-docker` behave identically. Paths that ship with Renode, such as
`platforms/cpus/stm32f103.repl` used here, are still found after it.

## Run it

```bash
hector test        # fetches the ELF, boots it, checks its symbols are loaded
hector run         # interactive Renode monitor (needs fw/ from a `hector test` run)
```

`fw/`, `.hector/` and `results/` are generated; don't commit them.
