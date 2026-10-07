from typing import Callable, Optional
from dasbus.server.interface import dbus_interface, dbus_signal, accepts_additional_arguments
from dasbus.server.property import PropertiesInterface, emits_properties_changed
from dasbus.typing import Str, Double, UInt32, List, Tuple, Dict, Byte, Bool
from .. import __version__

BUS_NAME = "org.tpfan1"
OBJECT_PATH = "/org/tpfan1"
IFACE = "org.tpfan1"

# Byte-Sentinels für nicht-numerische Fan-Level über D-Bus.
LEVEL_AUTO = 0xFF
LEVEL_DISENGAGED = 0xFE


def level_str_to_byte(s: str) -> int:
    """Mappt textuelle Fan-Level auf Byte-Codes für D-Bus.

    'auto' -> 0xFF, 'disengaged' -> 0xFE, numerisch -> int(s), sonst 0xFF.
    """
    try:
        s = str(s)
    except Exception:
        return LEVEL_AUTO
    if s == "auto":
        return LEVEL_AUTO
    if s == "disengaged":
        return LEVEL_DISENGAGED
    if s.isdigit():
        try:
            return int(s)
        except ValueError:
            return LEVEL_AUTO
    return LEVEL_AUTO


@dbus_interface(IFACE)
class TpfanService(PropertiesInterface):
    """state_getter() liefert ein Mapping mit Live-Daten;
    command_handler(name, *args) behandelt schreibende Calls.

    Schreibende Methoden melden die geänderten Properties per
    PropertiesChanged. Ohne das müssten Clients Mode/Curve pollen, und jeder
    Property-Read kostet den Daemon einen kompletten Sensor-Sweep.
    """

    def __init__(self, state_getter: Callable[[], dict], command_handler: Callable,
                 authorizer: Optional[Callable] = None):
        super().__init__()
        self._state = state_getter
        self._cmd = command_handler
        self._authz = authorizer

    def _report(self, *names: str) -> None:
        for n in names:
            self.report_changed_property(n)

    def _check(self, action: str, sender: str) -> None:
        if self._authz is None:
            return
        self._authz(sender, action)

    # --- Properties ---
    @property
    def Sensors(self) -> Dict[Str, Tuple[Double, Str, Str]]:
        # Ein einziger _state()-Aufruf: jeder liest die Hardware-Sensoren neu.
        state = self._state()
        out = {}
        for name, (val, label, source) in state.get("sensor_describe", {}).items():
            out[name] = (val, label, source)
        if not out:
            for name, val in state.get("temps", {}).items():
                out[name] = (val, name, name)
        return out

    @property
    def Fans(self) -> List[Tuple[UInt32, UInt32]]:
        fans = self._state().get("fans", [])
        out: list[tuple[int, int]] = []
        for rpm, lvl in fans:
            out.append((int(rpm), level_str_to_byte(lvl)))
        return out

    @property
    def Mode(self) -> Str:
        return self._state().get("mode", "auto")

    @property
    def CurrentLevel(self) -> Str:
        return self._state().get("level", "auto")

    @property
    def Curve(self) -> List[Tuple[Double, Byte]]:
        cv = self._state().get("curve")
        return [(float(t), int(l)) for t, l in cv.points] if cv else []

    @property
    def CurveSensors(self) -> List[Str]:
        return list(self._state().get("curve_sensors", []))

    @property
    def UserPresets(self) -> Dict[Str, Tuple[List[Tuple[Double, Byte]], List[Str]]]:
        out: dict[str, tuple[list[tuple[float, int]], list[str]]] = {}
        for name, cv in self._state().get("user_presets", {}).items():
            out[str(name)] = (
                [(float(t), int(l)) for t, l in cv.points],
                list(cv.sensors),
            )
        return out

    @property
    def BootGraceRemaining(self) -> Double:
        return float(self._state().get("boot_grace_remaining", 0.0))

    @property
    def FailsafeTemp(self) -> Double:
        return float(self._state().get("failsafe_temp", 95.0))

    @property
    def DaemonVersion(self) -> Str:
        return __version__

    @property
    def RpmStatsEnabled(self) -> Bool:
        return bool(self._state().get("rpm_stats_enabled", True))

    @property
    def LevelRpmStats(self) -> Dict[Str, Tuple[UInt32, UInt32, UInt32, UInt32]]:
        stats = self._state().get("rpm_stats") or {}
        out: dict[str, tuple[int, int, int, int]] = {}
        for lvl, vals in stats.items():
            try:
                last, mn, mx, n = vals
                out[str(lvl)] = (int(last), int(mn), int(mx), int(n))
            except (TypeError, ValueError):
                continue
        return out

    # --- Methoden ---
    @emits_properties_changed
    @accepts_additional_arguments
    def SetMode(self, mode: Str, *, call_info) -> None:
        self._check("org.tpfan1.set-mode", call_info.get("sender", ""))
        self._cmd("set_mode", mode)
        self._report("Mode")

    @emits_properties_changed
    @accepts_additional_arguments
    def SetCurve(self, points: List[Tuple[Double, Byte]], sensors: List[Str], *, call_info) -> None:
        self._check("org.tpfan1.set-curve", call_info.get("sender", ""))
        self._cmd("set_curve", [(float(t), int(l)) for t, l in points], list(sensors))
        self._report("Curve", "CurveSensors")

    @accepts_additional_arguments
    def SetManualLevel(self, level: Str, *, call_info) -> None:
        self._check("org.tpfan1.set-manual-level", call_info.get("sender", ""))
        self._cmd("set_manual_level", level)

    @emits_properties_changed
    @accepts_additional_arguments
    def SetFailsafeTemp(self, temp: Double, *, call_info) -> None:
        self._check("org.tpfan1.set-failsafe-temp", call_info.get("sender", ""))
        self._cmd("set_failsafe_temp", float(temp))
        self._report("FailsafeTemp")

    @emits_properties_changed
    @accepts_additional_arguments
    def SaveUserPreset(self, name: Str, points: List[Tuple[Double, Byte]],
                       sensors: List[Str], *, call_info) -> None:
        self._check("org.tpfan1.manage-presets", call_info.get("sender", ""))
        self._cmd("save_user_preset", str(name),
                  [(float(t), int(l)) for t, l in points], list(sensors))
        self._report("UserPresets")

    @emits_properties_changed
    @accepts_additional_arguments
    def DeleteUserPreset(self, name: Str, *, call_info) -> None:
        self._check("org.tpfan1.manage-presets", call_info.get("sender", ""))
        self._cmd("delete_user_preset", str(name))
        self._report("UserPresets")

    @emits_properties_changed
    @accepts_additional_arguments
    def ReloadConfig(self, *, call_info) -> None:
        self._check("org.tpfan1.reload-config", call_info.get("sender", ""))
        self._cmd("reload_config")
        # Die Datei kann alles geändert haben.
        self._report("Mode", "Curve", "CurveSensors", "FailsafeTemp",
                     "UserPresets", "RpmStatsEnabled")

    @emits_properties_changed
    @accepts_additional_arguments
    def SetRpmStatsEnabled(self, enabled: Bool, *, call_info) -> None:
        self._check("org.tpfan1.set-rpm-stats-enabled", call_info.get("sender", ""))
        self._cmd("set_rpm_stats_enabled", bool(enabled))
        self._report("RpmStatsEnabled")

    @emits_properties_changed
    @accepts_additional_arguments
    def ResetLevelRpmStats(self, *, call_info) -> None:
        self._check("org.tpfan1.reset-rpm-stats", call_info.get("sender", ""))
        self._cmd("reset_rpm_stats")
        self._report("LevelRpmStats")

    # --- Signale ---
    @dbus_signal
    def Tick(self, temps: Dict[Str, Double], fans: List[Tuple[UInt32, UInt32]], level: Str):
        pass

    @dbus_signal
    def EmergencyTriggered(self, temp: Double, sensor: Str):
        pass
