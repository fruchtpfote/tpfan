from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import json
import logging
import tempfile
import os

log = logging.getLogger(__name__)

# Bekannte Level-Strings, die wir tracken. Alles andere (unknown, leer,
# kaputte Kernel-Werte) wird ignoriert, damit die JSON nicht durch
# unerwartete Keys aufgebläht wird.
ALLOWED_LEVELS = frozenset(["0", "1", "2", "3", "4", "5", "6", "7",
                            "auto", "disengaged", "full-speed"])

# Obergrenze für den Sample-Zähler. Verhindert UInt32-Overflow auf dem
# D-Bus und hält die JSON-Werte klein. Bei einer Sample/Sekunde reichen
# 10 Mio. für ~116 Tage Dauerbetrieb pro Level — danach wird der Zähler
# eingefroren, last/min/max bleiben weiterhin aktuell.
COUNT_CAP = 10_000_000


@dataclass
class RpmStatsTracker:
    """Beobachtet die tatsächliche Lüfterdrehzahl pro Level-Stufe.

    Pro Level werden zuletzt gesehener Wert, Minimum, Maximum und Anzahl
    der Samples gesammelt. Die Daten werden im Daemon geführt, damit sie
    auch ohne laufende GUI auflaufen, und auf Platte persistiert.
    """

    last: dict[str, int] = field(default_factory=dict)
    minv: dict[str, int] = field(default_factory=dict)
    maxv: dict[str, int] = field(default_factory=dict)
    count: dict[str, int] = field(default_factory=dict)

    def record(self, level: str, rpm: int) -> None:
        if level not in ALLOWED_LEVELS or rpm < 0:
            return
        self.last[level] = int(rpm)
        n = self.count.get(level, 0)
        if n < COUNT_CAP:
            self.count[level] = n + 1
        if level not in self.minv or rpm < self.minv[level]:
            self.minv[level] = int(rpm)
        if level not in self.maxv or rpm > self.maxv[level]:
            self.maxv[level] = int(rpm)

    def reset(self) -> None:
        self.last.clear()
        self.minv.clear()
        self.maxv.clear()
        self.count.clear()

    def as_dict(self) -> dict[str, tuple[int, int, int, int]]:
        out: dict[str, tuple[int, int, int, int]] = {}
        for lvl, last in self.last.items():
            out[lvl] = (last, self.minv[lvl], self.maxv[lvl], self.count[lvl])
        return out

    def to_json(self) -> dict:
        return {
            "version": 1,
            "levels": {
                lvl: {
                    "last": last,
                    "min": self.minv[lvl],
                    "max": self.maxv[lvl],
                    "count": self.count[lvl],
                }
                for lvl, last in self.last.items()
            },
        }

    @classmethod
    def from_json(cls, raw: dict) -> "RpmStatsTracker":
        t = cls()
        for lvl, v in (raw.get("levels") or {}).items():
            if lvl not in ALLOWED_LEVELS:
                continue
            try:
                t.last[lvl] = int(v["last"])
                t.minv[lvl] = int(v["min"])
                t.maxv[lvl] = int(v["max"])
                t.count[lvl] = min(int(v["count"]), COUNT_CAP)
            except (KeyError, TypeError, ValueError):
                continue
        return t


def load_stats(path: Path) -> RpmStatsTracker:
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError:
        return RpmStatsTracker()
    except (OSError, json.JSONDecodeError) as e:
        log.warning("rpm stats unreadable (%s) — starting fresh", e)
        return RpmStatsTracker()
    return RpmStatsTracker.from_json(raw)


def save_stats(path: Path, tracker: RpmStatsTracker) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".rpm_stats.", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(tracker.to_json(), f)
            os.replace(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError as e:
        log.warning("could not persist rpm stats to %s: %s", path, e)
