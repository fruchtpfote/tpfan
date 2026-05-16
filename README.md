# tpfan

Lüfter-Steuerung und Temperatur-Anzeige für ThinkPad-Notebooks (entwickelt
und getestet auf einem ThinkPad E14 Gen 7) unter Linux. Steuert den Lüfter
über das `thinkpad_acpi`-Kernelmodul (`fan_control=1`) und bietet eine
Qt-basierte GUI mit Tray-Icon, Statusanzeige und Lüfterkurven-Editor.

## Komponenten

- **`tpfan-daemon`** — System-Service, liest Temperaturen und steuert das
  Fan-Level über `/proc/acpi/ibm/fan`. Stellt eine D-Bus-API
  (`org.tpfan1`, System-Bus) zur Verfügung.
- **`tpfan-gui`** — User-Anwendung mit Hauptfenster und System-Tray.
  Spricht mit dem Daemon ausschließlich über D-Bus.
- **Packaging** — systemd-Service, D-Bus-Service- und Policy-Files,
  polkit-Action, modprobe-Snippet (`fan_control=1`), Desktop-Entry und
  Icon.

## Voraussetzungen

- Linux mit `thinkpad_acpi`-Modul (wird beim Install mit `fan_control=1`
  neu geladen).
- Python ≥ 3.11.
- D-Bus-System-Bus, polkit, PyGObject (`gi`, für die GUI-Integration).
- Der Installer kümmert sich auf Fedora/RHEL (`dnf`), Debian/Ubuntu/Mint
  (`apt`) und Arch/Manjaro (`pacman`) selbst um die nötigen Pakete
  (pip, venv, PyGObject, D-Bus, polkit).

## Installation

Komfort-Skript (Fedora-, Debian- und Arch-basierte Distros):

    sudo ./scripts/install.sh

Das Skript:

1. installiert fehlende System-Abhängigkeiten via `dnf`, `apt` oder
   `pacman` (je nach erkannter Distro-Familie),
2. legt unter `/opt/tpfan/venv` ein dediziertes venv an
   (`--system-site-packages`, damit das system-eigene `python3-gobject`
   nutzbar bleibt) und installiert `tpfan-daemon` + `tpfan-gui` dort hinein,
3. kopiert alle Packaging-Dateien (systemd, D-Bus, polkit, modprobe,
   Desktop-Entry, Icon),
4. lädt `thinkpad_acpi` mit `fan_control=1` neu (Reboot nötig, falls das
   Modul gerade benutzt wird),
5. aktiviert und startet `tpfan-daemon.service`,
6. führt einen Smoke-Check aus (systemd active, D-Bus-Name registriert).

GUI starten:

    tpfan-gui

Deinstallation (entfernt venv, Packaging, Config unter `/etc/tpfan` und
State unter `/var/lib/tpfan`):

    sudo ./scripts/install.sh --uninstall

Umgebungsvariablen für den Installer:

- `TPFAN_PY` — alternativer Python-Interpreter zum Erzeugen des venv
  (Default `/usr/bin/python3`).
- `TPFAN_VENV` — Zielverzeichnis des venv (Default `/opt/tpfan/venv`).

## Bedienung

- **Tray-Icon**: zeigt die aktuelle Maximaltemperatur auf einem farbigen
  Kreis (grün = Level 0–2, gelb = 3–5, rot = 6–7/disengaged). Linksklick
  öffnet bzw. schließt das Fenster, Rechtsklick öffnet das Menü mit
  Modus-Umschaltung (Auto/Kurve/Manuell) und manueller Level-Wahl.
- **Hauptfenster**: Tabs für Status, Kurven-Editor und allgemeine
  Einstellungen.

## Logs

    journalctl -u tpfan-daemon -f         # Daemon-Logs
    TPFAN_LOG=debug tpfan-gui             # GUI mit Debug-Ausgabe

## Entwicklung

    make dev           # editable installs in .venv
    make test          # alle Unit-Tests
    make test-daemon   # nur Daemon
    make test-gui      # nur GUI

Architektur und API: `docs/superpowers/specs/2026-05-10-tpfan-design.md`.
Implementierungsplan: `docs/superpowers/plans/2026-05-13-tpfan-implementation.md`.
Manueller End-to-End-Test: `docs/manual-test.md`.

## Entstehung

tpfan wurde mit [Claude Code](https://www.claude.com/product/claude-code)
(Anthropic) entwickelt — Design, Implementierung, Tests und Packaging
sind in Kollaboration mit dem KI-Assistenten entstanden.

## Lizenz

tpfan steht unter der **GNU General Public License v3.0 oder neuer**
(`GPL-3.0-or-later`). Der vollständige Lizenztext liegt in `LICENSE`.

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
    GNU General Public License for more details.
