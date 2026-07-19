# NUCLEO-F767ZI (inline platform)

ST **NUCLEO-F767ZI** (STM32F767ZI, Cortex-M7 @ 216 MHz) defined entirely inside
`.hector.yaml` using inline [`repl:` / `resc:`](../../README.md#inline-repl-and-resc).

## Why this board is inline

Renode **1.16.1 ships no `nucleo_f767zi.repl` and no `stm32f767.repl`.** The released
image only has:

```
platforms/cpus/stm32f746.repl
platforms/boards/stm32f7_discovery-bb.repl
platforms/boards/nucleo_h753zi.repl
```

So `platform: [platforms/boards/nucleo_f767zi.repl]` has nothing to point at. The
usual workarounds are to pin the whole project to a Renode master build or vendor a
`.repl` next to the config. Instead, the board is pasted into `repl:` and loaded as-is
against the pinned release image — the config stays self-contained and reproducible.

## What's modelled

| Area | Detail |
|---|---|
| Core | Cortex-M7, NVIC (`systickFrequency: 216000000`) |
| Memory | 2 MB flash @ `0x08000000` (+ ITCM alias @ `0x00200000`), 512 KB SRAM @ `0x20000000` |
| Console | `usart3` — the ST-LINK virtual COM port (PD8/PD9), same as Zephyr's `nucleo_f767zi` target |
| GPIO | Ports A–H via `syscfg` → `exti` |
| Board I/O | LD1 green `PB0`, LD2 blue `PB7`, LD3 red `PB14`, B1 user button `PC13` |
| Connectivity | Ethernet MAC, I2C1, SPI1, DMA1/2, timers, RCC/RTC/RNG |

`resc:` carries the setup lines a board `.resc` would run — the DWT tag and
`ApplySVD`. (The F7x7 SVD isn't published; the F7x6 one is register-compatible for
everything modelled here.)

## Run it

The example ships with `BIN: "none"`, so the platform builds and can be inspected
without any firmware:

```bash
hector test        # verifies the platform instantiates and the board wiring responds
hector run         # interactive Renode monitor
```

Bring your own ELF to actually boot something:

```bash
hector test --set BIN=path/to/zephyr.elf
hector run  --set BIN=build/zephyr/zephyr.elf
```

Console output appears on `usart3` (`showAnalyzer usart3` is already in `commands:`).

## Adapting it

To track a newer Renode, replace the `repl:` block with the upstream
`nucleo_f767zi.repl` once it lands in a release — or drop the block and switch to
`platform:` at that point. Nothing else in the config changes.
