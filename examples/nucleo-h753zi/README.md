# NUCLEO-H753ZI + Hubris

ST **NUCLEO-H753ZI** (STM32H753ZI, Cortex-M7) booting
[Hubris](https://hubris.oxide.computer/), Oxide Computer Company's embedded OS.

## The contrast with `nucleo-f767zi`

This board **does** ship in the released Renode image:

```
platforms/cpus/stm32h753.repl
platforms/boards/nucleo_h753zi.repl
scripts/single-node/nucleo_h753zi_hubris.resc
```

So there's no need to paste a platform in — unlike
[`nucleo-f767zi`](../nucleo-f767zi), where Renode 1.16.1 ships nothing for the board.
Here inline `repl:` is used for a different reason: to **patch** the released board.

## Why `using` instead of `platform:`

Hubris needs the NVIC's full 8-bit priority field, so `priorityMask` must be widened
from the board default. The obvious approach — list the board under `platform:` and
override from `repl:` — **does not work**:

```yaml
platform:
  - platforms/boards/nucleo_h753zi.repl
repl: |
  nvic:
      priorityMask: 0xFF        # E35: Constructor attribute within entry
                                #      for variable that is not created
```

Every `LoadPlatformDescription` is its own **description scope**. `priorityMask` is a
*constructor* attribute, and those can only be set in the scope that creates the
entry. Since `platform:` loads the board as a separate file, `nvic` isn't created in
the inline scope.

The fix is to pull the board into the same scope from inside `repl:`:

```yaml
repl: |
  using "platforms/boards/nucleo_h753zi.repl"

  nvic:
      priorityMask: 0xFF        # works
```

This is exactly what Renode's own `nucleo_h753zi_hubris.resc` does with
`LoadPlatformDescriptionFromString`.

## What `resc:` carries

The board bring-up lines from Renode's Hubris script — the vector table offset and
the PWR register tags Hubris polls during clock/power init:

```
cpu VectorTableOffset 0x8000000
sysbus Tag <0x58024800 4> "PWR_CR1_DBP_SET" 0x100
sysbus Tag <0x58024804 4> "PWR_CSR1" 0x2000
sysbus Tag <0x58024808 4> "PWR_CR2_BREN_SET" 0x1
```

## Run it

```bash
hector test        # boots Hubris and round-trips a line through its uartecho task
hector run         # interactive monitor; console on usart2
```

The firmware is fetched automatically. The test asserts the board peripherals exist
**and** that Hubris scheduled its `uartecho` task — a line written to `usart2` comes
back — so it proves execution, not just that the platform constructed.

## Hubris tasks in this build

`sys`, `jefe`, `hiffy`, `uartecho` (USART2 echo), `user_leds` (blinking LED),
`user_button` (button toggles an LED), `net`, `udpecho`, `udprpc`.

The UDP tasks need host networking. Renode's script sets that up with a TAP:

```
emulation CreateTap "tap0" "tap" true
connector Connect host.tap switch
```

In hector that's an `ethernet` hub plus a `tap:` mapping — see
[mappings](../../README.md#mappings-global). It needs `NET_ADMIN` and `/dev/net/tun`,
so it's left out of this example.
