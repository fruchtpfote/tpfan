# Boot-Grace für Daemon — Design

## Ziel

Während der ersten 30 s nach Daemon-Start hält der Control-Loop den Lüfter auf `auto`, damit Boot-Spikes nicht sofort die konfigurierte Kurve triggern. Failsafe bleibt aktiv.

## Komponenten

`daemon/src/tpfan_daemon/control/loop.py`:

- Modul-Konstante `BOOT_GRACE_SECONDS = 30.0`.
- `ControlLoop` erhält zwei neue Felder:
  - `clock: Callable[[], float] = time.monotonic` — injizierbar für Tests.
  - `_started_at: float` — gesetzt in `__post_init__` via `clock()`.
- In `tick()`: **nach** dem Failsafe-Block (Temp ≥ `failsafe_temp` setzt unverändert `disengaged`), aber **vor** der Mode-Dispatch-Logik (`m == "auto" / "manual" / curve`), wird geprüft: `clock() - _started_at < BOOT_GRACE_SECONDS` → `target = "auto"`, normaler Schreibpfad (nur wenn `target != current`).

## Verhalten

- Failsafe → `disengaged` greift sofort, auch in der Grace-Phase.
- Sensor-Read-Fehler / Fan-Read-Fehler → bisheriger Fallback auf `auto` greift unverändert.
- Nach Ablauf: normaler Curve/Manual/Auto-Pfad.
- `set_config` setzt die Grace **nicht** zurück; sie ist Daemon-Lifetime-gebunden.

## Tests

`daemon/tests/test_loop.py`:

1. **`test_boot_grace_forces_auto_during_grace`**: Curve-Mode mit „heißem" Sensor (z. B. CPU 70 °C, Kurve „Sehr ruhig"), stehende `clock` bei t=0 → `target == "auto"`.
2. **`test_boot_grace_releases_after_window`**: gleiche Konfiguration, `clock` liefert `t=31.0` → `target == "2"` (Kurvenlogik greift).
3. **`test_boot_grace_does_not_block_failsafe`**: Temp = `failsafe_temp`, `clock` bei t=0 → `target == "disengaged"`, `emergency` gesetzt.

## Scope-Abgrenzung

- Hardcoded 30 s, keine Config-Option.
- Kein Reset bei Mode/Curve-Wechsel.
- Keine UI-Anzeige des Grace-Status.
