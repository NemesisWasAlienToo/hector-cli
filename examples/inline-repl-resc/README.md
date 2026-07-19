# Inline `repl:` / `resc:`

Uses a board defined **entirely inside `.hector.yaml`** — no external `.repl` file and
no reliance on what the Renode image happens to ship.

## Why

`platform:` takes *paths* to `.repl` files, which only works for boards the released
Renode image already contains. When the board you need exists only on Renode's
**master branch** (or lives in your own fork, or isn't upstream at all), there's no
path to point at.

`repl:` and `resc:` solve that by taking the **contents** verbatim: copy the platform
description off master, paste it in, and it runs against the pinned release image.

## How it works

| Section | Takes | Becomes |
|---|---|---|
| `repl:` | `.repl` platform-description text | written to `.hector/repl/job_<n>_<node>.inline.repl`, then `machine LoadPlatformDescription @<that file>` |
| `resc:` | `.resc` monitor-script text | emitted verbatim into the machine's block, after the platform + firmware load |

Emission order inside a machine is:

```
mach create "<node>"
machine LoadPlatformDescription @<platform: files>    # paths, if any
machine LoadPlatformDescription @<inline repl:>       # this example
sysbus LoadELF @<firmware:>
<resc:>                                               # verbatim script
<commands:>                                           # your own additions last
```

So `repl:` composes with `platform:` — list the released board under `platform:` and
use `repl:` to patch or extend it.

> **Don't put `mach create` in `resc:`** — hector already creates the machine. Use
> `resc:` for the setup lines that follow it (`sysbus ApplySVD`, `sysbus Tag`, macros,
> extra `LoadPlatformDescription`, …).

## Run it

```bash
hector test        # boots the firmware, presses the button, checks UART output
hector run         # interactive Renode monitor
```

The platform here mirrors `platforms/cpus/stm32f103.repl` from the Renode tree, so it
boots the same Zephyr button firmware as the [`yaml-defined-mcu`](../yaml-defined-mcu)
example — which builds the identical machine out of YAML `peripherals:` instead. Use
that one when you want hector to generate the platform; use this one when you already
have `.repl` text and just want it loaded as-is.
