from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import logging

log = logging.getLogger(__name__)

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
    # Sensornamen, für die bereits eine 'unreadable'-Warnung geloggt wurde;
    # verhindert Journal-Flooding bei dauerhaft unlesbaren Slots (z. B. ENXIO).
    _warned: set[str] = field(default_factory=set, repr=False)

    def discover(self) -> None:
        self.refs = []
        self._warned.clear()
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

    def read_all(self) -> dict[str, float]:
        out: dict[str, float] = {}
        for r in self.refs:
            try:
                raw = r.path.read_text().strip()
                out[r.name] = int(raw) / 1000.0
                self._warned.discard(r.name)
            except (OSError, ValueError) as e:
                if r.name not in self._warned:
                    log.warning("sensor %s unreadable: %s", r.name, e)
                    self._warned.add(r.name)
        return out

    def describe(self) -> dict[str, tuple[float, str, str]]:
        out: dict[str, tuple[float, str, str]] = {}
        for r in self.refs:
            try:
                v = int(r.path.read_text().strip()) / 1000.0
            except (OSError, ValueError):
                continue
            out[r.name] = (v, r.name, r.source)
        return out
