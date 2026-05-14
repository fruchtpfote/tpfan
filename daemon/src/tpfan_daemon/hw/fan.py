from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import os
import time
import logging

log = logging.getLogger(__name__)

VALID_LEVELS = {"0", "1", "2", "3", "4", "5", "6", "7", "auto", "disengaged"}


@dataclass(frozen=True)
class FanState:
    speed_rpm: int
    level: str
    enabled: bool


@dataclass
class Fan:
    path: Path = Path("/proc/acpi/ibm/fan")
    _writer: Callable[[str], None] | None = None
    _sleep: Callable[[float], None] = time.sleep
    retries: int = 3
    retry_delay_s: float = 0.1

    def writable(self) -> bool:
        return os.access(self.path, os.W_OK)

    def read(self) -> FanState:
        speed = 0
        level = "unknown"
        enabled = False
        for line in self.path.read_text().splitlines():
            if line.startswith("speed:"):
                try:
                    speed = int(line.split(":", 1)[1].strip())
                except ValueError:
                    speed = 0
            elif line.startswith("level:"):
                level = line.split(":", 1)[1].strip()
            elif line.startswith("status:"):
                enabled = line.split(":", 1)[1].strip() == "enabled"
        return FanState(speed_rpm=speed, level=level, enabled=enabled)

    def set_level(self, level: str) -> None:
        if level not in VALID_LEVELS:
            raise ValueError(f"invalid fan level: {level!r}")
        cmd = f"level {level}"
        writer = self._writer or self._default_writer
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                writer(cmd)
                return
            except OSError as e:
                last = e
                log.warning("fan write attempt %d failed: %s", attempt + 1, e)
                self._sleep(self.retry_delay_s)
        assert last is not None
        raise last

    def _default_writer(self, cmd: str) -> None:
        with self.path.open("w") as f:
            f.write(cmd)
