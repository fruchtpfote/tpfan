from __future__ import annotations
from tpfan_daemon.ipc.polkit import authorize, PolkitError
from gi.repository import GLib
import pytest


class FakeBus:
    """Beantwortet CheckAuthorization asynchron über den GLib-Main-Context,
    wie der echte polkit-Proxy (callback statt Rückgabewert)."""

    def __init__(self, allowed: bool, defer: bool = True):
        self.allowed = allowed
        self.defer = defer
        self.calls: list = []

    def get_proxy(self, *a, **kw):
        bus = self

        class P:
            def CheckAuthorization(self, subject, action_id, details, flags,
                                   cancel_id, *, callback):
                bus.calls.append((action_id, flags))
                result = (bus.allowed, False, {})

                def deliver():
                    callback(lambda: result)
                    return False

                if bus.defer:
                    GLib.idle_add(deliver)
                else:
                    deliver()
        return P()


def test_authorize_allowed():
    bus = FakeBus(True)
    authorize(bus, sender=":1.42", action="org.tpfan1.set-mode")
    assert bus.calls[0][0] == "org.tpfan1.set-mode"


def test_authorize_uses_interactive_flag():
    bus = FakeBus(True)
    authorize(bus, sender=":1.42", action="org.tpfan1.set-mode")
    # flags=1 == AllowUserInteraction (interaktiver Auth-Dialog erlaubt)
    assert bus.calls[0][1] == 1


def test_authorize_denied_raises():
    bus = FakeBus(False)
    with pytest.raises(PolkitError):
        authorize(bus, sender=":1.42", action="org.tpfan1.set-mode")


class UnreachableBus:
    def get_proxy(self, *a, **kw):
        raise RuntimeError("bus connection lost")


def test_authorize_authority_unreachable_fails_closed():
    with pytest.raises(PolkitError):
        authorize(UnreachableBus(), sender=":1.42", action="org.tpfan1.set-mode")


class ErrorReplyBus:
    """CheckAuthorization-Reply wirft eine Exception (D-Bus-Fehler)."""

    def get_proxy(self, *a, **kw):
        class P:
            def CheckAuthorization(self, *a, callback, **kw):
                def boom():
                    raise RuntimeError("dbus error on reply")
                GLib.idle_add(lambda: (callback(boom), False)[1])
        return P()


def test_authorize_reply_error_fails_closed():
    with pytest.raises(PolkitError):
        authorize(ErrorReplyBus(), sender=":1.42", action="org.tpfan1.set-mode")


def test_authorize_pumps_main_loop_while_pending():
    """Regression: Während auf die polkit-Antwort gewartet wird, muss der
    Default-GLib-Main-Context weiterlaufen. Sonst feuert der Daemon-Tick nicht
    mehr, das systemd-Watchdog-Heartbeat verhungert und systemd killt den
    Daemon per SIGABRT ('Remote peer disconnected' in der GUI)."""
    ticks = {"n": 0}

    def heartbeat():
        ticks["n"] += 1
        return True

    hb_id = GLib.timeout_add(5, heartbeat)

    class SlowBus:
        def get_proxy(self, *a, **kw):
            class P:
                def CheckAuthorization(self, subject, action_id, details, flags,
                                       cancel_id, *, callback):
                    # Antwort erst nach ~40 ms -> der Loop muss in der
                    # Zwischenzeit ticken, damit das Heartbeat läuft.
                    GLib.timeout_add(
                        40,
                        lambda: (callback(lambda: (True, False, {})), False)[1],
                    )
            return P()

    try:
        authorize(SlowBus(), sender=":1.7", action="org.tpfan1.set-curve")
    finally:
        GLib.source_remove(hb_id)

    assert ticks["n"] >= 1, "Main-Loop wurde während der Autorisierung nicht gepumpt"
