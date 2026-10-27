# Blackpill board defined entirely in YAML

The machine `blackpill` is a complete STM32F103 plus the board's user button on PC13,
written as `peripherals:` in `.hector.yaml` — a faithful translation of Renode's
`platforms/cpus/stm32f103.repl`, with no `.repl` file.

The header of [`.hector.yaml`](.hector.yaml) explains the layout:

- peripherals can be nested to group them (here under `mcu`), but the generated
  `.repl` is flat, so names like `nvic` or `gpioPortC` resolve regardless;
- `connections:` and `init:` belong to the machine, not to a peripheral;
- hex literals are quoted so they stay hex in the generated `.repl`.

## Run it

```bash
hector test      # boots the Zephyr button demo, presses the button, checks usart2
```

For a shorter version of the same idea, see [`yaml-defined-mcu`](../yaml-defined-mcu).
