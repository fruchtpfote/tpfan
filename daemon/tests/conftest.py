from __future__ import annotations
from pathlib import Path
import pytest


@pytest.fixture
def hwmon_tree(tmp_path: Path) -> Path:
    """Fake /sys/class/hwmon Baum. Tests füllen Dateien selbst."""
    root = tmp_path / "hwmon"
    root.mkdir()
    return root


def make_hwmon(root: Path, idx: int, name: str, temps: dict[str, float] | None = None,
               fans: dict[str, int] | None = None, labels: dict[str, str] | None = None) -> Path:
    """Erzeugt hwmon{idx}/ mit name + temp*_input/_label, fan*_input.

    temps: {"temp1": 42.0, ...} → millicelsius in temp1_input
    fans:  {"fan1": 2800, ...}
    labels: {"temp1": "Tctl", ...}
    """
    d = root / f"hwmon{idx}"
    d.mkdir()
    (d / "name").write_text(name + "\n")
    for k, v in (temps or {}).items():
        (d / f"{k}_input").write_text(f"{int(v * 1000)}\n")
    for k, v in (labels or {}).items():
        (d / f"{k}_label").write_text(v + "\n")
    for k, v in (fans or {}).items():
        (d / f"{k}_input").write_text(f"{v}\n")
    return d
