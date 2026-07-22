"""Unit tests for hector.core.Registry and RuntimeOptions — the extension mechanism
and the execution-environment requirements components declare."""

import pytest

from hector.core import Registry, RuntimeOptions


def test_register_and_get():
    reg = Registry("widget")

    @reg.register("foo")
    class Foo:
        pass

    assert reg.get("foo") is Foo
    assert "foo" in reg
    assert list(reg.keys()) == ["foo"]


def test_duplicate_registration_raises():
    reg = Registry("widget")
    reg.register("foo")(object)
    with pytest.raises(ValueError, match="already registered"):
        reg.register("foo")(object)


def test_unknown_key_raises_helpful_keyerror():
    reg = Registry("widget")
    reg.register("foo")(object)
    reg.register("bar")(object)
    with pytest.raises(KeyError) as exc:
        reg.get("baz")
    # The message lists what IS available (sorted), so a typo is self-diagnosing.
    assert "bar, foo" in str(exc.value)


def test_empty_registry_reports_none_available():
    reg = Registry("widget")
    with pytest.raises(KeyError, match="\\(none\\)"):
        reg.get("anything")


def test_contains_false_for_missing():
    assert "missing" not in Registry("widget")


# ---- RuntimeOptions ----

def test_merge_unions_caps_and_devices():
    a = RuntimeOptions(capabilities={"NET_ADMIN"}, devices={"/dev/net/tun"})
    b = RuntimeOptions(capabilities={"SYS_PTRACE"}, devices={"/dev/kvm"})
    a.merge(b)
    assert a.capabilities == {"NET_ADMIN", "SYS_PTRACE"}
    assert a.devices == {"/dev/net/tun", "/dev/kvm"}


def test_merge_root_is_sticky_or():
    a = RuntimeOptions(root=False)
    a.merge(RuntimeOptions(root=True))
    assert a.root is True
    # Once true, a later false merge cannot clear it.
    a.merge(RuntimeOptions(root=False))
    assert a.root is True


def test_merge_none_is_noop():
    a = RuntimeOptions(capabilities={"NET_ADMIN"}, root=True)
    assert a.merge(None) is a
    assert a.capabilities == {"NET_ADMIN"} and a.root is True


def test_default_runtime_is_empty():
    r = RuntimeOptions()
    assert r.capabilities == set() and r.devices == set() and r.root is False
