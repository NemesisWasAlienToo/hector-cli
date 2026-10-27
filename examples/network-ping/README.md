# Two Linux machines pinging over an emulated switch

Two Zynq-7000 (Zedboard) machines running Linux, both plugged into one Ethernet
switch hub, ping each other:

```
zed1.gem0 (192.168.1.1)  <->  lan (switch)  <->  zed2.gem0 (192.168.1.2)
```

Unlike [`zedboard-net`](../zedboard-net), which bridges to the host over a TAP, this
needs no host privileges or setup, so it runs anywhere `hector test` does. It mirrors
Renode's own two-Zedboard ping test. With a hub present, hector sets the global
quantum so cross-machine traffic is deterministic.

## Run it

```bash
hector test      # boots both (about 2 minutes), assigns IPs, pings zed1 -> zed2
```
