"""Unit tests for hector.hubs — cross-machine connection media and the HUBS registry."""

import pytest

from hector.core import RuntimeOptions
from hector.hubs import HUBS


def test_registry_has_expected_media():
    for name in ("uart", "can", "ethernet", "gpio"):
        assert name in HUBS


def test_symmetric_flags():
    assert HUBS.get("uart").symmetric is True
    assert HUBS.get("can").symmetric is True
    assert HUBS.get("ethernet").symmetric is True
    assert HUBS.get("gpio").symmetric is False


def test_emit_create_uses_class_verb():
    assert HUBS.get("uart").emit_create("link") == ['emulation CreateUARTHub "link"']
    assert HUBS.get("ethernet").emit_create("sw") == ['emulation CreateSwitch "sw"']


def test_symmetric_emit_connect():
    spec = {"node": "mcu", "periph": "usart1", "hub": "link"}
    assert HUBS.get("uart").emit_connect(spec) == [
        'mach set "mcu"',
        "connector Connect sysbus.usart1 link",
    ]


def test_default_runtime_options_empty():
    r = HUBS.get("uart").runtime_options({"node": "m", "periph": "u", "hub": "h"})
    assert isinstance(r, RuntimeOptions)
    assert r.capabilities == set() and r.devices == set() and r.root is False


def test_gpio_build_spec_requires_pin():
    gpio = HUBS.get("gpio")
    ep_plain = {"kind": "plain", "name": "gpioA"}
    with pytest.raises(ValueError):
        gpio.build_spec("mcu", "gpioA", "gpio_link", ep_plain,
                        hub_on_left=False, line="mcu.gpioA -> gpio_link")


def test_gpio_build_spec_accepts_pin():
    gpio = HUBS.get("gpio")
    ep_pin = {"kind": "pin", "name": "gpioA", "pin": 3}
    spec = gpio.build_spec("mcu", "gpioA", "gpio_link", ep_pin,
                           hub_on_left=False, line="mcu.gpioA@3 -> gpio_link")
    assert spec["node"] == "mcu" and spec["periph"] == "gpioA"
