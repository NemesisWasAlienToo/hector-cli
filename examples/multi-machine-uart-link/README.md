# Two machines over a UART hub, with a Verilator peripheral

An STM32F103 and a Linux vexpress (Cortex-A9) joined by a UART hub:

```
stm32f103.usart1  <->  uart_link (hub)  <->  vexpress.uart1
```

- **`modules:`** builds `uartlite`, a Verilated UART from the
  renode-verilator-integration samples, and places it on the STM32 at `0x70000000`.
  The first run clones the Renode source and the integration repo into `.hector/`
  and compiles the module (about 2 minutes); later runs reuse them.
- **`matrix:`** has one variable, `NUM`, which the last test echoes. Pick a job with
  `--job NUM=1`.

## Run it

```bash
hector test
```

The tests press the STM32's button and check its UART output, boot Linux on the
vexpress and write through the UART link, and run a shell test with the matrix value.
