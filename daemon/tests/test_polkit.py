from __future__ import annotations
from tpfan_daemon.ipc.polkit import authorize, PolkitError
import pytest


class FakeBus:
    def __init__(self, allowed: bool):
        self.allowed = allowed
        self.calls: list = []

    def get_proxy(self, *a, **kw):
        bus = self

        class P:
            def CheckAuthorization(self, subject, action_id, details, flags, cancel_id):
                bus.calls.append((action_id,))
                return (bus.allowed, False, {})
        return P()


def test_authorize_allowed():
    bus = FakeBus(True)
    authorize(bus, sender=":1.42", action="org.tpfan1.set-mode")
    assert bus.calls[0][0] == "org.tpfan1.set-mode"


def test_authorize_denied_raises():
    bus = FakeBus(False)
    with pytest.raises(PolkitError):
        authorize(bus, sender=":1.42", action="org.tpfan1.set-mode")
