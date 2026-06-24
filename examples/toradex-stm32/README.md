# Example: Linux board + STM32F103 UART link

ARM Cortex-A9 (Versatile Express) running Linux connected to an STM32F103
microcontroller over a hardware UART hub. The Linux console is forwarded to
TCP:5555 so VS Code can reach it; the STM32 UART appears inside the Linux shell
as `/dev/ttyAMA1`.

> **Toradex note:** Versatile Express is used as a simulation stand-in because
> its PL011 UARTs (`ttyAMAx`) are reliably accessible from Linux userspace with
> the available kernel/rootfs. For real Toradex hardware, replace
> `platforms/boards/vexpress.repl` with the appropriate Colibri/Verdin `.repl`,
> update the firmware URLs and boot args, and swap `/dev/ttyAMA1` for whatever
> serial port your BSP exposes (typically `/dev/ttymxcX` on iMX-based boards).

---

## Architecture

```
┌──────────────────────┐             ┌──────────────────────────────┐
│  STM32F103           │  uart_link  │  ARM Cortex-A9 (Linux)       │
│  Zephyr firmware     │             │                              │
│                      │────────────►│  uart1 (/dev/ttyAMA1)        │
│  usart2 ─ Zephyr log │             │  uart0 (/dev/ttyAMA0)        │
│    "Button pressed"  │             │    └── TCP:5555 (console)    │
└──────────────────────┘             └──────────────────────────────┘
```

- **`uart_link` hub** wires `stm32f103.usart2` ↔ `vexpress.uart1`. The Zephyr
  firmware writes its log output (including button-press events) to `usart2`,
  which flows through the hub and arrives on `/dev/ttyAMA1` inside Linux.
- **Linux console** (`uart0 / ttyAMA0`) is forwarded to TCP:5555 so you can
  open a Linux shell from any terminal without a physical serial adapter.

---

## Requirements

- Docker
- Python 3.9+, pyyaml: `pip install -r ../../requirements.txt`

---

## Run

```bash
# from this directory
hector run      # start the simulation
hector test     # run all three automated tests
```

---

## Step-by-step: connect and communicate

### 1 — Open the Linux console in VS Code

In a VS Code terminal (or any terminal):

```bash
nc localhost 5555
```

You will see the Linux boot log followed by a login prompt:

```
Versatile Express minimal

vexpress login:
```

Log in as **root** (no password).

### 2 — Mount sysfs and create device nodes

`proc` is already mounted by the init process, but `sysfs` is not.
`mdev -s` needs sysfs to discover which devices the kernel has registered:

```bash
mkdir /sys
mount -t sysfs sysfs /sys
mdev -s
ls /dev/ttyAMA*
# /dev/ttyAMA0  /dev/ttyAMA1  /dev/ttyAMA2  /dev/ttyAMA3
```

`/dev/ttyAMA1` is now the live UART link to the STM32.

### 3 — Configure the port and read STM32 output

```bash
stty -F /dev/ttyAMA1 115200 raw -echo
cat /dev/ttyAMA1
```

`cat` blocks and prints whatever arrives from the STM32.

### 4 — Trigger the STM32 button

Press and release the button from the Renode monitor (or let `hector test` do it):

```
sysbus.gpioPortC.button Press
sysbus.gpioPortC.button Release
```

The Zephyr firmware sends `Button pressed at <tick>` on `usart2`, which flows
through the `uart_link` hub and appears on `/dev/ttyAMA1`:

```
Button pressed at 12345
```

Any Linux application reads `/dev/ttyAMA1` like a normal serial port — the same
API used against a real Toradex UART device.

---

## Automated tests

```bash
hector test
```

| Test | What it checks |
|---|---|
| Linux boots | vexpress reaches login prompt within 120 s |
| STM32 button press | GPIO toggle produces UART output on usart2 (analyzer) |
| STM32 → Linux | Button press triggers output on usart2; message arrives on vexpress uart1 |

---

## VS Code Remote – SSH (full image)

The minimal busybox rootfs does not ship `sshd` or Docker. To use VS Code
Remote – SSH for real application development:

1. Replace `LINUX_BIN` / `LINUX_ROOTFS` with a full image (TorizonCore, Debian,
   Yocto) that includes `sshd` and Docker.

2. Add a TAP mapping so the Linux VM has host network access:

```yaml
# in .hector.yaml mappings:
mappings: |
  vexpress.smc91x -> tap:tap0
  vexpress.uart0  -> tcp:5555
```

3. Create the TAP interface on the host:

```bash
sudo ip tuntap add tap0 mode tap
sudo ip addr add 192.168.10.1/24 dev tap0
sudo ip link set tap0 up
```

4. Inside the Linux shell, bring up the interface and start SSH:

```bash
ip addr add 192.168.10.2/24 dev eth0
ip link set eth0 up
/usr/sbin/sshd
```

5. Open VS Code → **Remote – SSH** → connect to `root@192.168.10.2`.

From there, deploy Docker containers to the board and use `/dev/ttyAMA1` from
within your containerised application to talk to the STM32 — the same path
that would be `/dev/ttymxc0` (or similar) on real Toradex hardware.
