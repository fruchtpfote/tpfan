from __future__ import annotations

from tpfan_gui.__main__ import TraySync


class FakeClient:
    def __init__(self, values=None, raises=None):
        # Kein `values or ...`: ein leeres Dict ist ein gültiger Fall (Daemon
        # liefert nichts) und darf nicht auf die Defaults zurückfallen.
        if values is None:
            values = {"Mode": "curve", "Curve": [(40.0, 0), (80.0, 7)]}
        self.values = values
        self.raises = raises or set()
        self.reads: list[str] = []

    def get(self, name: str):
        self.reads.append(name)
        if name in self.raises:
            raise RuntimeError("daemon weg")
        return self.values.get(name)


class FakeTray:
    def __init__(self):
        self.ticks: list[object] = []
        self.modes: list[str] = []
        self.curves: list[object] = []
        self.connected: list[bool] = []

    def apply_tick(self, p): self.ticks.append(p)
    def apply_mode(self, m): self.modes.append(m)
    def apply_curve(self, c): self.curves.append(c)
    def set_connected(self, ok): self.connected.append(ok)


def test_on_tick_does_not_read_properties():
    # Jeder Property-Read löst im Daemon einen Sensor-Sweep über I2C/ACPI aus;
    # bei 1 Hz war das die Hälfte seiner Idle-CPU-Last.
    client, tray = FakeClient(), FakeTray()
    sync = TraySync(client, tray)

    sync.on_tick("payload")

    assert tray.ticks == ["payload"]
    assert client.reads == []


def test_on_props_resyncs_for_mode_and_curve():
    client, tray = FakeClient(), FakeTray()
    sync = TraySync(client, tray)

    sync.on_props({"Mode": "manual"})

    assert client.reads == ["Mode", "Curve"]
    assert tray.modes == ["curve"]
    assert tray.curves == [[(40.0, 0), (80.0, 7)]]


def test_on_props_ignores_unrelated_properties():
    client, tray = FakeClient(), FakeTray()
    sync = TraySync(client, tray)

    sync.on_props({"LevelRpmStats": {}})

    assert client.reads == []


def test_on_connected_resyncs_only_when_connected():
    client, tray = FakeClient(), FakeTray()
    sync = TraySync(client, tray)

    sync.on_connected(False)
    assert tray.connected == [False]
    assert client.reads == []

    sync.on_connected(True)
    assert tray.connected == [False, True]
    assert client.reads == ["Mode", "Curve"]


def test_resync_falls_back_to_empty_curve_on_error():
    client, tray = FakeClient(raises={"Curve"}), FakeTray()
    sync = TraySync(client, tray)

    sync.resync()

    assert tray.curves == [[]]


def test_resync_keeps_mode_untouched_when_daemon_returns_nothing():
    client, tray = FakeClient(values={}), FakeTray()
    sync = TraySync(client, tray)

    sync.resync()

    assert tray.modes == []
    assert tray.curves == [[]]
