# STM32F103 defined in YAML

An STM32F103 defined with `peripherals:` in `.hector.yaml` instead of a `.repl` file.
The layout mirrors `platforms/cpus/stm32f103.repl` from the Renode tree: memory, CPU
and NVIC, EXTI and its combiners, GPIO ports, USARTs, timers.

## Run it

```bash
hector test      # boots the Zephyr button demo, presses the button, checks usart2
```

[`stm32f103-full`](../stm32f103-full) is the complete version, with the board around
the MCU.
