# Shell test against a background emulation

A `shell` test with `requires-machine: true` runs while the emulation is up. Hector starts
Renode headless in the background, loads the generated resc, runs the test's steps,
then stops Renode.

```
background-sim/
├── .hector.yaml        # one machine + one requires-machine: true shell test
└── checks/monitor.py   # tiny Renode monitor client (stdlib only)
```

The steps reach the emulation through Renode's monitor on `$HECTOR_MONITOR_PORT`
(host network, so `localhost` works from inside the test's container):

```bash
python3 checks/monitor.py 'mach set "mcu"' 'sysbus GetSymbolAddress "main"'
```

`checks/monitor.py` sends a newline first: only the first client to connect gets a
banner, so a reconnecting client has to ask for the prompt.

The machine's console (`usart2`) is exposed with a per-machine mapping,
`usart2 -> tcp:3456:raw`, so a step can read and write it on `localhost:3456` (with
`nc`, a Python socket, pyserial's `socket://localhost:3456`, or `socat` for a pty).
The firmware is already running when the steps start, so output it printed before a
step connects (the boot banner) isn't there to read.

## Run it

```bash
hector test
```

The test checks that the firmware's symbols are loaded, that the CPU has executed
instructions, and that the console port accepts a connection. Renode's log ends up in `results/test_0_<name>/renode.log`.

To see the failure path, point the machine at firmware that doesn't exist:

```bash
hector test --set BIN=missing.elf     # fails before any step runs, with Renode's error
```
