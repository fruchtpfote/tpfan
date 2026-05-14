# tpfan — Manuelle Test-Checkliste

Voraussetzungen:
- Fedora 44 oder kompatibles System auf einem ThinkPad E14 Gen 7.
- `sudo make install` ausgeführt.
- `sudo modprobe -r thinkpad_acpi && sudo modprobe thinkpad_acpi` oder Reboot,
  damit `fan_control=1` aktiv ist.
- `systemctl enable --now tpfan-daemon.service`

Smoke-Tests:

- [ ] `systemctl status tpfan-daemon` zeigt `active (running)`.
- [ ] `journalctl -u tpfan-daemon -n 20 --no-pager` zeigt „READY=1" und keine Tracebacks.
- [ ] `busctl --system introspect org.tpfan1 /org/tpfan1` listet `Sensors`, `Fans`, `Mode`, Methoden.
- [ ] `tpfan-gui` startet, zeigt Live-Werte für CPU/GPU/NVMe/RAM/WLAN (Latenz < 1 s).
- [ ] Modus „Auto" → `cat /proc/acpi/ibm/fan` zeigt `level: auto`.
- [ ] Modus „Manuell" → Level 5 klicken → `level: 5`.
- [ ] Modus „Kurve" mit CPU-Last (`stress-ng --cpu 4 --timeout 60`) → Level steigt sichtbar.
- [ ] Kurveneditor: Punkt verschieben → „Anwenden" → polkit-Prompt → Wirkung sichtbar.
- [ ] Profil „Quiet" anwenden → Lüfter bei Idle leiser.
- [ ] Failsafe-Test: Failsafe auf 50 °C setzen, CPU-Last erzeugen → GUI-Dialog erscheint,
  `level: disengaged` sichtbar, journald loggt `EmergencyTriggered`.
- [ ] `systemctl stop tpfan-daemon` → nach Stop bleibt `level: auto`.
- [ ] GUI ohne Daemon: GUI zeigt Statusbar „Daemon nicht erreichbar", reconnects beim Start.
