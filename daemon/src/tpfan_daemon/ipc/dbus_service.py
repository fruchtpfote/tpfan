from typing import Callable, Optional
from dasbus.server.interface import dbus_interface, dbus_signal
from dasbus.typing import Str, Double, UInt32, List, Tuple, Dict, Byte
from .. import __version__

BUS_NAME = "org.tpfan1"
OBJECT_PATH = "/org/tpfan1"
IFACE = "org.tpfan1"


@dbus_interface(IFACE)
class TpfanService:
    """state_getter() liefert ein Dict mit Live-Daten;
    command_handler(name, *args) behandelt schreibende Calls."""

    def __init__(self, state_getter: Callable[[], dict], command_handler: Callable,
                 authorizer: Optional[Callable] = None,
                 sender_getter: Optional[Callable[[], str]] = None):
        self._state = state_getter
        self._cmd = command_handler
        self._authz = authorizer
        self._sender = sender_getter

    def _check(self, action: str) -> None:
        if self._authz is None:
            return
        sender = self._sender() if self._sender else ""
        self._authz(sender, action)

    # --- Properties ---
    @property
    def Sensors(self) -> Dict[Str, Tuple[Double, Str, Str]]:
        out = {}
        for name, (val, label, source) in self._state().get("sensor_describe", {}).items():
            out[name] = (val, label, source)
        if not out:
            for name, val in self._state().get("temps", {}).items():
                out[name] = (val, name, name)
        return out

    @property
    def Fans(self) -> List[Tuple[UInt32, UInt32]]:
        fans = self._state().get("fans", [])
        out: list[tuple[int, int]] = []
        for rpm, lvl in fans:
            try:
                lvl_n = int(lvl) if str(lvl).isdigit() else 0xFF
            except (ValueError, TypeError):
                lvl_n = 0xFF
            out.append((int(rpm), lvl_n))
        return out

    @property
    def Mode(self) -> Str:
        return self._state().get("mode", "auto")

    @property
    def CurrentLevel(self) -> Str:
        return self._state().get("level", "auto")

    @property
    def Curve(self) -> List[Tuple[Double, Byte]]:
        return [(float(t), int(l)) for t, l in self._state().get("curve").points]

    @property
    def CurveSensors(self) -> List[Str]:
        return list(self._state().get("curve_sensors", []))

    @property
    def FailsafeTemp(self) -> Double:
        return float(self._state().get("failsafe_temp", 95.0))

    @property
    def DaemonVersion(self) -> Str:
        return __version__

    # --- Methoden ---
    def SetMode(self, mode: Str) -> None:
        self._check("org.tpfan1.set-mode")
        self._cmd("set_mode", mode)

    def SetCurve(self, points: List[Tuple[Double, Byte]], sensors: List[Str]) -> None:
        self._check("org.tpfan1.set-curve")
        self._cmd("set_curve", [(float(t), int(l)) for t, l in points], list(sensors))

    def SetManualLevel(self, level: Str) -> None:
        self._check("org.tpfan1.set-manual-level")
        self._cmd("set_manual_level", level)

    def SetFailsafeTemp(self, temp: Double) -> None:
        self._check("org.tpfan1.set-failsafe-temp")
        self._cmd("set_failsafe_temp", float(temp))

    def ReloadConfig(self) -> None:
        self._check("org.tpfan1.reload-config")
        self._cmd("reload_config")

    # --- Signale ---
    @dbus_signal
    def Tick(self, temps: Dict[Str, Double], fans: List[Tuple[UInt32, UInt32]], level: Str):
        pass

    @dbus_signal
    def EmergencyTriggered(self, temp: Double, sensor: Str):
        pass
