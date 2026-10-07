from __future__ import annotations
import logging, os, signal, sys
from collections.abc import Mapping
from pathlib import Path
from typing import Callable

from gi.repository import GLib
from dasbus.connection import SystemMessageBus

from .daemon import Daemon
from .hw.sensors import Sensors
from .hw.fan import Fan
from .ipc.dbus_service import TpfanService, BUS_NAME, OBJECT_PATH, level_str_to_byte
from .ipc.polkit import authorize
from .rpm_stats import RpmStatsTracker, load_stats, save_stats

CONFIG_PATH = Path(os.environ.get("TPFAN_CONFIG", "/etc/tpfan/config.toml"))
RPM_STATS_PATH = Path(os.environ.get("TPFAN_RPM_STATS", "/var/lib/tpfan/rpm_stats.json"))
RPM_STATS_SAVE_EVERY = 60  # ticks (≈ 1 min)


def _setup_logging():
    level = os.environ.get("TPFAN_LOG", "info").upper()
    logging.basicConfig(level=getattr(logging, level, logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        stream=sys.stderr)


def _sd_notify(msg: str) -> None:
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return
    import socket
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        if addr.startswith("@"):
            addr = "\0" + addr[1:]
        s.sendto(msg.encode(), addr)
    finally:
        s.close()


def main() -> int:
    _setup_logging()
    log = logging.getLogger("tpfan-daemon")

    sensors = Sensors()
    sensors.discover()
    fan = Fan()
    if not fan.writable():
        log.error("/proc/acpi/ibm/fan not writable — load thinkpad_acpi with fan_control=1")
        return 1

    daemon = Daemon(CONFIG_PATH, sensors, fan)
    rpm_stats = load_stats(RPM_STATS_PATH)
    bus = SystemMessageBus()

    def authorizer(sender: str, action: str) -> None:
        authorize(bus, sender, action)

    def handle_cmd(cmd: str, *args):
        if cmd == "reset_rpm_stats":
            rpm_stats.reset()
            save_stats(RPM_STATS_PATH, rpm_stats)
            return
        return daemon.handle(cmd, *args)

    service = TpfanService(
        state_getter=lambda: _state_dict(daemon, sensors, rpm_stats),
        command_handler=handle_cmd,
        authorizer=authorizer,
    )

    bus.publish_object(OBJECT_PATH, service)
    bus.register_service(BUS_NAME)

    _sd_notify("READY=1")
    main_loop = GLib.MainLoop()

    def shutdown(*_):
        log.info("shutdown — resetting fan to auto")
        try:
            fan.set_level("auto")
        except Exception:
            log.exception("failed to reset fan to auto on shutdown")
        save_stats(RPM_STATS_PATH, rpm_stats)
        main_loop.quit()

    for s in (signal.SIGTERM, signal.SIGINT):
        signal.signal(s, shutdown)

    tick_counter = [0]

    def tick():
        try:
            # tr.fan_speed stammt aus dem fan.read() in loop.tick() — kein
            # zweiter Read von /proc/acpi/ibm/fan pro Sekunde.
            tr = daemon.loop.tick()
            fans_payload = [(tr.fan_speed, _lvl_to_int(tr.target_level))]
            service.Tick(tr.temps, fans_payload, tr.target_level)
            if tr.emergency:
                service.EmergencyTriggered(tr.emergency[0], tr.emergency[1])
            if daemon.loop.config.rpm_stats_enabled and not tr.fallback_to_auto:
                rpm_stats.record(tr.target_level, int(tr.fan_speed))
                tick_counter[0] += 1
                if tick_counter[0] % RPM_STATS_SAVE_EVERY == 0:
                    save_stats(RPM_STATS_PATH, rpm_stats)
        except Exception:
            log.exception("tick failed")
            return True
        _sd_notify("WATCHDOG=1")
        return True

    GLib.timeout_add_seconds(1, tick)
    main_loop.run()
    return 0


class _LazyState(Mapping):
    """State-Mapping, das teure Werte erst beim Zugriff berechnet.

    Properties wie Mode oder Curve brauchen keine Sensordaten. Wertete man den
    State eifrig aus, löste jeder dieser Property-Reads einen kompletten
    Sensor-Sweep über I2C/ACPI aus — bei einem sekündlich pollenden Client
    war das die Hälfte der Idle-CPU-Last des Daemons.
    """

    def __init__(self, eager: dict, lazy: dict[str, Callable[[], object]]):
        self._eager = eager
        self._lazy = lazy

    def __getitem__(self, key):
        if key in self._eager:
            return self._eager[key]
        if key in self._lazy:
            return self._lazy[key]()
        raise KeyError(key)

    def __iter__(self):
        yield from self._eager
        yield from self._lazy

    def __len__(self) -> int:
        return len(self._eager) + len(self._lazy)


def _state_dict(d: Daemon, sensors: Sensors, rpm_stats: RpmStatsTracker) -> Mapping:
    # describe() liefert Wert, Label und Quelle in einem Durchgang; temps wird
    # daraus abgeleitet, statt mit read_all() ein zweites Mal über den Bus zu
    # gehen. Pro State-Instanz wird höchstens einmal gelesen.
    cached: dict[str, dict] = {}

    def describe() -> dict:
        if "desc" not in cached:
            cached["desc"] = sensors.describe()
        return cached["desc"]

    return _LazyState(
        eager={
            "mode": d.loop.config.mode,
            "level": d.loop.last_level,
            "fans": [],
            "curve": d.loop.config.curve,
            "curve_sensors": list(d.loop.config.curve.sensors),
            "failsafe_temp": d.loop.config.failsafe_temp,
            "rpm_stats": rpm_stats.as_dict(),
            "rpm_stats_enabled": d.loop.config.rpm_stats_enabled,
            "user_presets": d.loop.config.user_presets,
            "boot_grace_remaining": d.loop.boot_grace_remaining(),
        },
        lazy={
            "sensor_describe": describe,
            "temps": lambda: {name: val for name, (val, _, _) in describe().items()},
        },
    )


def _lvl_to_int(lvl: str) -> int:
    return level_str_to_byte(lvl)


if __name__ == "__main__":
    sys.exit(main())
