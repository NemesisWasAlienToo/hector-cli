# SPDX-License-Identifier: AGPL-3.0-or-later
"""
HUBS  -  cross-machine connection media (emulation-level objects).

==========================================================================
HOW TO ADD A NEW HUB TYPE
==========================================================================
1. Subclass `Hub`.
2. Decorate it with `@HUBS.register("<yaml-type-name>")`.
3. Set `create_command` (the `emulation <X> "name"` verb) and `symmetric`.
4. If it is asymmetric (needs source/dest roles + pins), override `build_spec`
   and `emit_connect` (see GpioConnector below for the template).

That is the whole change. `connections.py` and `engine.py` are generic over this
registry, so nothing else needs editing. Example — adding a SPI connector:

    @HUBS.register("spi")
    class SpiConnector(Hub):
        create_command = "CreateSPIConnector"   # whatever Renode calls it
        symmetric = False
        # ... override build_spec/emit_connect if it needs pins/roles ...

The YAML then immediately accepts:   hubs:\n  mylink: { type: spi }
==========================================================================
"""

from .core import Registry, RuntimeOptions

HUBS = Registry("hub type")


class Hub:
    """Base class for a cross-machine connection medium.

    A symmetric hub (uart/can/ethernet) is wired with '<->' and every endpoint is
    equal. An asymmetric connector (gpio) is wired with '->' and each endpoint has a
    role (source/destination) plus a pin.
    """
    create_command = None     # the `emulation <create_command> "name"` verb
    symmetric = True          # True -> '<->'; False -> directional '->'

    @classmethod
    def emit_create(cls, name):
        """resc line(s) that instantiate the hub."""
        return [f'emulation {cls.create_command} "{name}"']

    @classmethod
    def build_spec(cls, node, periph, hub_name, ep, hub_on_left, line):
        """Validate one connection endpoint and return a spec dict for the resc.
        Default: symmetric medium, no role/pin."""
        return {"node": node, "periph": periph, "hub": hub_name}

    @classmethod
    def emit_connect(cls, spec):
        """resc lines connecting one endpoint (one spec) to this hub."""
        return [f'mach set "{spec["node"]}"',
                f'connector Connect sysbus.{spec["periph"]} {spec["hub"]}']

    @classmethod
    def runtime_options(cls, spec):
        """Execution-environment needs this connection imposes on the Renode run
        (docker caps/devices/root). Default: none. Override for a medium that needs,
        e.g., a host device or NET_ADMIN."""
        return RuntimeOptions()

    @classmethod
    def describe(cls, spec):
        return f'{spec["node"]}.{spec["periph"]} <-> {spec["hub"]}'


# -------------------- symmetric media --------------------
@HUBS.register("uart")
class UartHub(Hub):
    create_command = "CreateUARTHub"
    symmetric = True


@HUBS.register("can")
class CanHub(Hub):
    create_command = "CreateCANHub"
    symmetric = True


@HUBS.register("ethernet")
class EthernetSwitch(Hub):
    create_command = "CreateSwitch"
    symmetric = True


# -------------------- asymmetric connectors --------------------
@HUBS.register("gpio")
class GpioConnector(Hub):
    create_command = "CreateGPIOConnector"
    symmetric = False

    @classmethod
    def build_spec(cls, node, periph, hub_name, ep, hub_on_left, line):
        if ep["kind"] != "pin":
            raise ValueError(
                f"Connection '{line}': gpio connections need a pin, e.g. "
                f"{node}.{periph}@<n>."
            )
        # arrow direction relative to the hub picks the role:
        #   periph -> hub   => this port is the SOURCE
        #   hub -> periph   => this port is the DESTINATION
        role = "dest" if hub_on_left else "source"
        return {"node": node, "periph": periph, "hub": hub_name,
                "role": role, "pin": ep["pin"]}

    @classmethod
    def emit_connect(cls, spec):
        sel = "SelectSourcePin" if spec["role"] == "source" else "SelectDestinationPin"
        return [f'mach set "{spec["node"]}"',
                f'connector Connect sysbus.{spec["periph"]} {spec["hub"]}',
                f'{spec["hub"]} {sel} sysbus.{spec["periph"]} {spec["pin"]}']

    @classmethod
    def describe(cls, spec):
        return f'{spec["node"]}.{spec["periph"]}@{spec["pin"]} ({spec["role"]}) -> {spec["hub"]}'


# -------------------- USB connector --------------------
@HUBS.register("usb")
class UsbConnector(Hub):
    """Asymmetric USB connector. The device side uses `connector Connect`;
    the controller side uses `RegisterInController`.

    In connections:
      mcu.usb   -> usblink      # mcu is the USB DEVICE  (periph->hub)
      usblink   -> host.usb     # host is the USB CONTROLLER  (hub->periph)

    Docs: https://renode.readthedocs.io/en/latest/tutorials/usbip.html
    """
    create_command = "CreateUSBConnector"
    symmetric = False

    @classmethod
    def build_spec(cls, node, periph, hub_name, ep, hub_on_left, line):
        # periph -> hub  =>  device;   hub -> periph  =>  controller
        role = "controller" if hub_on_left else "device"
        return {"node": node, "periph": periph, "hub": hub_name, "role": role}

    @classmethod
    def emit_connect(cls, spec):
        if spec["role"] == "device":
            return [f'mach set "{spec["node"]}"',
                    f'connector Connect sysbus.{spec["periph"]} {spec["hub"]}']
        else:  # controller
            return [f'mach set "{spec["node"]}"',
                    f'{spec["hub"]} RegisterInController sysbus.{spec["periph"]}']

    @classmethod
    def describe(cls, spec):
        return f'{spec["node"]}.{spec["periph"]} ({spec["role"]}) <-> {spec["hub"]}'


@HUBS.register("wireless")
class WirelessMedium(Hub):
    """IEEE 802.15.4 wireless medium (ZigBee / Thread / 6LoWPAN / Matter).

    Connects radio interfaces across machines. All connected interfaces receive all
    packets by default; use SetMediumFunction to model range / packet loss.

    Docs: https://renode.readthedocs.io/en/latest/networking/wireless.html
    """
    create_command = "CreateIEEE802_15_4Medium"
    symmetric = True


@HUBS.register("ble")
class BLEMedium(Hub):
    """Bluetooth Low Energy medium.

    Connects BLE radio interfaces across machines. Same positioning and range/loss
    model as the IEEE 802.15.4 medium — see the wireless hub for details.

    Docs: https://renode.readthedocs.io/en/latest/networking/wireless.html
         https://renode.readthedocs.io/en/latest/tutorials/ble-simulation.html
    """
    create_command = "CreateBLEMedium"
    symmetric = True


@HUBS.register("wisun")
class WiSUNMedium(Hub):
    """Wi-SUN (Wireless Smart Utility Network) medium — IEEE 802.11ah-based mesh.

    Used for large-scale IoT mesh networks (smart meters, grid infrastructure).
    All connected radio interfaces receive all packets by default.
    Supports the same SetPosition / SetMediumFunction range-loss model as the
    IEEE 802.15.4 and BLE mediums.

    Docs: https://renode.readthedocs.io/en/latest/networking/wireless.html
    """
    create_command = "CreateWiSUNMedium"
    symmetric = True