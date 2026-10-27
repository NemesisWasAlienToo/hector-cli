# Zedboard Linux bridged to the host over a TAP

A Zynq-7000 (Zedboard) running Linux with working Ethernet. The emulated NIC (`gem0`)
is plugged into a TAP interface on your host, so the guest looks like a machine on a
point-to-point link to your host and ordinary sockets work across it.

`hector test` only checks that Linux boots and `eth0` comes up. For the TAP, hector
gives the Renode container `NET_ADMIN`, `/dev/net/tun` and root by itself (when the
host has `/dev/net/tun`). Configuring the host side and exchanging data are manual:
the header of [`.hector.yaml`](.hector.yaml) has the host and guest commands
(addresses, an `nc` / `telnet` stream, file transfer over HTTP).

## Run it

```bash
hector test      # boots Linux and brings eth0 up (about 30 s)
hector run       # then follow the steps in .hector.yaml's header
```

For networking without host privileges, see [`network-ping`](../network-ping).
