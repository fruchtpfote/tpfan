from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Callable, Iterable
import logging
import time

log = logging.getLogger(__name__)

# Nicht jeder hwmon-Treiber ist gleich billig: k10temp/amdgpu lesen aus einem
# Register (~0,05 ms), spd5118 geht über den I2C-Bus und nvme/thinkpad über
# die NVMe-Admin-Queue bzw. ACPI (0,5–2 ms pro Read, grösstenteils Kernel-Zeit).
# Bei 1 Hz summiert sich das zu dauerhafter CPU-Last, obwohl nur die Sensoren
# der aktiven Kurve wirklich sekündlich gebraucht werden. Darum werden die
# trägen Treiber beim Start ausgemessen und danach nur noch im langsamen
# Intervall gepollt; ihre letzten Werte liefert der Cache.
#
# Die Schwelle liegt in der Lücke zwischen den beiden Gruppen (~0,05 ms gegen
# ≥0,3 ms), damit die Einstufung nicht am Messrauschen kippt.
SLOW_SENSOR_THRESHOLD_S = 0.00025
SLOW_POLL_INTERVAL_S = 5.0
CALIBRATION_SAMPLES = 5

# Mapping: (hwmon-name, label-substring or None) -> semantischer Name.
# Reihenfolge bestimmt Prioritaet bei doppelten Hits.
_MAP: list[tuple[str, str | None, str]] = [
    ("k10temp",     "Tctl",       "CPU"),
    ("coretemp",    "Package id", "CPU"),
    ("amdgpu",      "edge",       "GPU"),
    ("nouveau",     None,         "GPU"),
    ("nvidia",      None,         "GPU"),
    ("nvme",        "Composite",  "NVMe"),
    ("nvme",        "Sensor 1",   "NVMe-S1"),
    ("nvme",        "Sensor 2",   "NVMe-S2"),
    ("thinkpad",    "CPU",        "MB-CPU"),
    ("thinkpad",    "GPU",        "MB-GPU"),
    ("thinkpad",    None,         "MB"),
    ("spd5118",     None,         "RAM"),
    ("mt7921_phy0", None,         "WLAN"),
    ("acpitz",      None,         "ACPI"),
]


@dataclass(frozen=True)
class SensorRef:
    name: str
    path: Path
    source: str


@dataclass
class Sensors:
    root: Path = Path("/sys/class/hwmon")
    refs: list[SensorRef] = field(default_factory=list)
    # Namen der Sensoren, deren Treiber beim Start als träge gemessen wurde.
    slow: set[str] = field(default_factory=set)
    slow_poll_interval_s: float = SLOW_POLL_INTERVAL_S
    slow_threshold_s: float = SLOW_SENSOR_THRESHOLD_S
    clock: Callable[[], float] = time.monotonic
    timer: Callable[[], float] = time.perf_counter
    # Sensornamen, für die bereits eine 'unreadable'-Warnung geloggt wurde;
    # verhindert Journal-Flooding bei dauerhaft unlesbaren Slots (z. B. ENXIO).
    _warned: set[str] = field(default_factory=set, repr=False)
    _cache: dict[str, float] = field(default_factory=dict, repr=False)
    _slow_due_at: float = field(default=0.0, repr=False)

    def discover(self) -> None:
        self.refs = []
        self._warned.clear()
        self._cache.clear()
        self._slow_due_at = 0.0
        taken: set[str] = set()
        for d in sorted(self.root.iterdir()):
            if not d.is_dir():
                continue
            name_file = d / "name"
            if not name_file.exists():
                continue
            try:
                drv = name_file.read_text().strip()
            except OSError:
                continue
            for input_path in sorted(d.glob("temp*_input")):
                idx = input_path.name[len("temp"):-len("_input")]
                label_path = d / f"temp{idx}_label"
                label = label_path.read_text().strip() if label_path.exists() else None
                sem = self._classify(drv, label, idx)
                if sem is None:
                    sem = self._generic_name(drv, label, idx)
                sem = self._dedupe(sem, taken)
                taken.add(sem)
                src = f"{drv}/{label or f'temp{idx}'}"
                self.refs.append(SensorRef(sem, input_path, src))
        self._calibrate()

    def _calibrate(self) -> None:
        """Misst die Sensoren aus und merkt sich die trägen Treiber.

        Gemessen wird in Sweeps über alle Sensoren, nicht mehrfach am selben:
        manche Treiber (thinkpad_acpi) cachen intern, direkt aufeinander
        folgende Reads wären also künstlich billig. Der Median über die Sweeps
        glättet einzelne Scheduling-Ausreisser.
        """
        samples: dict[str, list[float]] = {r.name: [] for r in self.refs}
        for _ in range(CALIBRATION_SAMPLES):
            for r in self.refs:
                samples[r.name].append(self._time_read(r))
        self.slow = {name for name, xs in samples.items()
                     if median(xs) >= self.slow_threshold_s}
        log.info("%d of %d sensors classified slow: %s",
                 len(self.slow), len(self.refs), ", ".join(sorted(self.slow)) or "-")

    def _time_read(self, r: SensorRef) -> float:
        # Unlesbare Sensoren schlagen hier nicht durch: discover() darf nicht
        # an einem einzelnen toten Slot scheitern, und die 'unreadable'-Warnung
        # gehört in den ersten echten Read, nicht in die Kalibrierung.
        t0 = self.timer()
        try:
            self._read_raw(r)
        except (OSError, ValueError):
            pass
        return self.timer() - t0

    @staticmethod
    def _generic_name(drv: str, label: str | None, idx: str) -> str:
        # Generischer Fallback für Hardware, die nicht in _MAP steht.
        # Erlaubt Nutzern auf anderen ThinkPads, alle Sensoren in der GUI
        # zu sehen und in der Curve zu verwenden.
        if label:
            return f"{drv}-{label}"
        return f"{drv}-temp{idx}"

    @staticmethod
    def _dedupe(name: str, taken: set[str]) -> str:
        if name not in taken:
            return name
        i = 2
        while f"{name}#{i}" in taken:
            i += 1
        return f"{name}#{i}"

    def _classify(self, drv: str, label: str | None, idx: str) -> str | None:
        for d, lbl, sem in _MAP:
            if d != drv:
                continue
            if lbl is None:
                if drv == "thinkpad":
                    return f"MB-temp{idx}"
                return sem
            if label and lbl in label:
                return sem
        return None

    @staticmethod
    def _read_raw(r: SensorRef) -> float:
        return int(r.path.read_text().strip()) / 1000.0

    def _read_one(self, r: SensorRef) -> float | None:
        """Liest einen Sensor; None bei Fehler, Warnung einmal pro Ausfallphase."""
        try:
            v = self._read_raw(r)
        except (OSError, ValueError) as e:
            if r.name not in self._warned:
                log.warning("sensor %s unreadable: %s", r.name, e)
                self._warned.add(r.name)
            return None
        self._warned.discard(r.name)
        return v

    def read_all(self) -> dict[str, float]:
        """Liest alle Sensoren frisch — für D-Bus-Abfragen und Validierung."""
        out: dict[str, float] = {}
        for r in self.refs:
            v = self._read_one(r)
            if v is not None:
                out[r.name] = v
        self._cache = dict(out)
        return out

    def read_for_control(self, required: Iterable[str] = ()) -> dict[str, float]:
        """Liest für den Regelkreis: schnelle Sensoren frisch, träge gecacht.

        Träge Treiber werden nur alle `slow_poll_interval_s` angefasst, ihre
        Werte sind entsprechend bis zu diesem Intervall alt. Sensoren in
        `required` — die der aktiven Kurve — gelten immer als schnell, damit
        die Regelung auf aktuellen Werten rechnet.
        """
        now = self.clock()
        slow_due = now >= self._slow_due_at
        if slow_due:
            self._slow_due_at = now + self.slow_poll_interval_s
        req = set(required)
        for r in self.refs:
            if r.name in self.slow and not slow_due and r.name not in req:
                continue
            v = self._read_one(r)
            if v is None:
                self._cache.pop(r.name, None)
            else:
                self._cache[r.name] = v
        return dict(self._cache)

    def describe(self) -> dict[str, tuple[float, str, str]]:
        out: dict[str, tuple[float, str, str]] = {}
        for r in self.refs:
            v = self._read_one(r)
            if v is None:
                continue
            out[r.name] = (v, r.name, r.source)
        return out
