from __future__ import annotations
import pytest

pytest.importorskip("pytestqt")


class _FakeClient:
    """Minimal fake DBus client exposing the signals/methods MainWindow needs."""
    def __init__(self):
        from PyQt6.QtCore import QObject, pyqtSignal

        class _Signals(QObject):
            tickReceived = pyqtSignal(object)
            emergency = pyqtSignal(float, str)
            connected = pyqtSignal(bool)

        self._s = _Signals()
        self.tickReceived = self._s.tickReceived
        self.emergency = self._s.emergency
        self.connected = self._s.connected
        self.mode_calls: list[str] = []
        self.manual_calls: list[str] = []
        self.failsafe_calls: list[float] = []
        self.curve_calls: list = []

    def set_mode(self, m: str): self.mode_calls.append(m)
    def set_manual_level(self, v: str): self.manual_calls.append(v)
    def set_failsafe_temp(self, t: float): self.failsafe_calls.append(t)
    def set_curve(self, points, sensors): self.curve_calls.append((list(points), list(sensors)))


def test_mode_request_propagates_state(qtbot):
    from tpfan_gui.main_window import MainWindow
    client = _FakeClient()
    win = MainWindow(client)
    qtbot.addWidget(win)

    win.modes.modeRequested.emit("manual")
    assert client.mode_calls == ["manual"]
    assert all(b.isEnabled() for b in win.modes._manual_buttons)

    win.modes.modeRequested.emit("auto")
    assert client.mode_calls == ["manual", "auto"]
    assert all(not b.isEnabled() for b in win.modes._manual_buttons)


def test_reconnect_resets_t0(qtbot):
    from tpfan_gui.main_window import MainWindow
    client = _FakeClient()
    win = MainWindow(client)
    qtbot.addWidget(win)

    win._t0 = 123.0
    win._on_connected(False)
    assert win._t0 == 123.0
    win._on_connected(True)
    assert win._t0 is None


def test_friendly_error_maps_polkit_and_disconnected():
    from tpfan_gui.main_window import MainWindow
    assert "polkit" in MainWindow._friendly_error(RuntimeError("AccessDenied: blah")).lower() \
        or "Berechtigung" in MainWindow._friendly_error(RuntimeError("AccessDenied: blah"))
    assert MainWindow._friendly_error(RuntimeError("polkit denied")) == "Keine Berechtigung (polkit verweigert)"
    assert MainWindow._friendly_error(RuntimeError("daemon not connected")) == "Daemon nicht verbunden"
    assert MainWindow._friendly_error(RuntimeError("something else")) == "something else"
