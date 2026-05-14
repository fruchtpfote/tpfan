#!/usr/bin/env bash
#
# tpfan — System-Installer für ThinkPad E14 Gen 7
#
# Voll-Setup auf Fedora-artigen Distros:
#   1. Prüft root
#   2. Installiert System-Abhängigkeiten via dnf
#   3. Installiert daemon + GUI Python-Pakete systemweit
#   4. Kopiert Packaging-Dateien (systemd, D-Bus, polkit, modprobe, desktop)
#   5. Lädt thinkpad_acpi mit fan_control=1 neu
#   6. Aktiviert und startet tpfan-daemon.service
#   7. Smoke-Check (BusName + systemd-Status)
#
# Benutzung:
#   sudo ./scripts/install.sh           # Installation
#   sudo ./scripts/install.sh --uninstall   # Deinstallation
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PACKAGING="$REPO_DIR/packaging"

PY=${TPFAN_PY:-/usr/bin/python3}
PIP_FLAGS=${TPFAN_PIP_FLAGS:---break-system-packages}

DNF_DEPS=(python3-pip python3-gobject dbus-daemon polkit)

log()  { printf '\033[1;34m[tpfan]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[tpfan]\033[0m %s\n' "$*" >&2; }
err()  { printf '\033[1;31m[tpfan]\033[0m %s\n' "$*" >&2; }

require_root() {
    if [[ $EUID -ne 0 ]]; then
        err "muss als root laufen (sudo verwenden)"
        exit 1
    fi
}

detect_distro() {
    if [[ -r /etc/os-release ]]; then
        . /etc/os-release
        echo "${ID:-unknown}"
    else
        echo "unknown"
    fi
}

install_system_deps() {
    local distro
    distro=$(detect_distro)
    case "$distro" in
        fedora|rhel|centos)
            local missing=()
            for pkg in "${DNF_DEPS[@]}"; do
                rpm -q "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
            done
            if [[ ${#missing[@]} -eq 0 ]]; then
                log "System-Abhängigkeiten bereits installiert: ${DNF_DEPS[*]}"
                return 0
            fi
            log "installiere fehlende System-Abhängigkeiten via dnf: ${missing[*]}"
            dnf install -y --setopt=install_weak_deps=False "${missing[@]}"
            ;;
        *)
            warn "Distro '$distro' nicht direkt unterstützt — überspringe System-Deps"
            warn "stelle sicher dass python3-pip, python3-gobject (gi), dbus-daemon und polkit installiert sind"
            ;;
    esac
}

install_python_packages() {
    log "installiere tpfan-daemon und tpfan-gui systemweit via pip"
    "$PY" -m pip install $PIP_FLAGS "$REPO_DIR/daemon"
    "$PY" -m pip install $PIP_FLAGS "$REPO_DIR/gui"
}

install_packaging() {
    log "kopiere Packaging-Dateien"
    install -D -m 0755 "$PACKAGING/tpfan-daemon-launcher" /usr/local/bin/tpfan-daemon
    install -D -m 0755 "$PACKAGING/tpfan-gui-launcher"    /usr/local/bin/tpfan-gui
    install -D -m 0644 "$PACKAGING/tpfan-daemon.service"  /etc/systemd/system/tpfan-daemon.service
    install -D -m 0644 "$PACKAGING/org.tpfan1.conf"       /etc/dbus-1/system.d/org.tpfan1.conf
    install -D -m 0644 "$PACKAGING/org.tpfan1.service"    /usr/share/dbus-1/system-services/org.tpfan1.service
    install -D -m 0644 "$PACKAGING/org.tpfan1.policy"     /usr/share/polkit-1/actions/org.tpfan1.policy
    install -D -m 0644 "$PACKAGING/tpfan-modprobe.conf"   /etc/modprobe.d/tpfan.conf
    install -D -m 0644 "$PACKAGING/tpfan-gui.desktop"     /usr/share/applications/tpfan-gui.desktop
    install -D -m 0644 "$PACKAGING/tpfan.svg"             /usr/share/icons/hicolor/scalable/apps/tpfan.svg
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache --quiet /usr/share/icons/hicolor 2>/dev/null || true
    fi
    systemctl daemon-reload
}

FAN_CONTROL_ACTIVE=0

fan_control_is_active() {
    local p=/sys/module/thinkpad_acpi/parameters/fan_control
    [[ -r $p ]] && [[ "$(cat "$p")" == "Y" ]]
}

reload_kernel_module() {
    log "lade thinkpad_acpi mit fan_control=1 neu"
    if lsmod | grep -q '^thinkpad_acpi'; then
        if ! modprobe -r thinkpad_acpi 2>/dev/null; then
            warn "konnte thinkpad_acpi nicht entladen (in Benutzung) — Reboot nötig"
            return 0
        fi
    fi
    modprobe thinkpad_acpi || warn "modprobe thinkpad_acpi fehlgeschlagen"

    if fan_control_is_active; then
        FAN_CONTROL_ACTIVE=1
        log "  fan_control=1 ist aktiv"
    else
        warn "  fan_control=1 NICHT aktiv (vermutlich wurde das Modul auto-reloaded ohne neue Optionen)"
        warn "  Reboot durchführen, dann greift /etc/modprobe.d/tpfan.conf"
    fi
}

enable_service() {
    if [[ $FAN_CONTROL_ACTIVE -eq 1 ]]; then
        log "aktiviere und starte tpfan-daemon.service"
        systemctl enable --now tpfan-daemon.service
        # Pickt neuen Code/Service-Unit bei Re-Installs auf; auf der
        # frischen Installation ist der Service gerade erst gestartet,
        # try-restart ist dort idempotent.
        log "lade tpfan-daemon neu, falls bereits aktiv"
        systemctl try-restart tpfan-daemon.service || true
    else
        log "aktiviere tpfan-daemon.service (Start verschoben bis nach Reboot)"
        systemctl enable tpfan-daemon.service
        warn ""
        warn "WICHTIG: Reboot erforderlich, damit fan_control=1 wirksam wird."
        warn "Nach dem Reboot startet der Service automatisch."
        warn ""
    fi
}

smoke_check() {
    if [[ $FAN_CONTROL_ACTIVE -ne 1 ]]; then
        log "Smoke-Check übersprungen (Reboot ausstehend)"
        return 0
    fi
    log "Smoke-Check"
    sleep 1
    if systemctl is-active --quiet tpfan-daemon.service; then
        log "  systemd: active"
    else
        err "  systemd: NICHT aktiv — siehe 'journalctl -u tpfan-daemon -n 30'"
        return 1
    fi
    if busctl --system list 2>/dev/null | grep -q '^org\.tpfan1 '; then
        log "  D-Bus: org.tpfan1 registriert"
    else
        warn "  D-Bus: org.tpfan1 noch nicht sichtbar (kann beim Erststart verzögert sein)"
    fi
}

uninstall_python_packages() {
    log "deinstalliere tpfan-daemon und tpfan-gui Python-Pakete"
    "$PY" -m pip uninstall -y $PIP_FLAGS tpfan-gui tpfan-daemon || true
}

uninstall_packaging() {
    log "entferne Packaging-Dateien"
    rm -f /usr/local/bin/tpfan-daemon
    rm -f /usr/local/bin/tpfan-gui
    rm -f /etc/systemd/system/tpfan-daemon.service
    rm -f /etc/dbus-1/system.d/org.tpfan1.conf
    rm -f /usr/share/dbus-1/system-services/org.tpfan1.service
    rm -f /usr/share/polkit-1/actions/org.tpfan1.policy
    rm -f /etc/modprobe.d/tpfan.conf
    rm -f /usr/share/applications/tpfan-gui.desktop
    rm -f /usr/share/icons/hicolor/scalable/apps/tpfan.svg
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache --quiet /usr/share/icons/hicolor 2>/dev/null || true
    fi
    systemctl daemon-reload
}

do_install() {
    require_root
    install_system_deps
    install_python_packages
    install_packaging
    reload_kernel_module
    enable_service
    smoke_check
    log "fertig. GUI starten mit: tpfan-gui"
}

remove_config() {
    if [[ -e /etc/tpfan ]]; then
        log "entferne Config-Verzeichnis /etc/tpfan"
        rm -rf /etc/tpfan
    fi
}

remove_state() {
    if [[ -e /var/lib/tpfan ]]; then
        log "entferne State-Verzeichnis /var/lib/tpfan (RPM-Statistik)"
        rm -rf /var/lib/tpfan
    fi
}

reload_module_without_fan_control() {
    log "lade thinkpad_acpi neu (ohne fan_control=1)"
    if lsmod | grep -q '^thinkpad_acpi'; then
        if modprobe -r thinkpad_acpi 2>/dev/null; then
            modprobe thinkpad_acpi || warn "modprobe thinkpad_acpi fehlgeschlagen"
        else
            warn "konnte thinkpad_acpi nicht entladen (in Benutzung) — Reboot durchführen"
        fi
    fi
}

do_uninstall() {
    require_root
    log "stoppe und deaktiviere Service"
    systemctl disable --now tpfan-daemon.service 2>/dev/null || true
    uninstall_packaging
    uninstall_python_packages
    remove_config
    remove_state
    reload_module_without_fan_control
    log "fertig."
}

case "${1:-install}" in
    install)   do_install ;;
    --uninstall|uninstall) do_uninstall ;;
    -h|--help)
        cat <<EOF
tpfan-Installer

Usage:
  sudo $0              # Voll-Installation
  sudo $0 --uninstall  # Deinstallation
  sudo $0 --help       # diese Hilfe

Umgebungsvariablen:
  TPFAN_PY=/path/to/python3   # alternativer Python-Interpreter (default: /usr/bin/python3)
  TPFAN_PIP_FLAGS="..."       # pip-Flags (default: --break-system-packages)
EOF
        ;;
    *)
        err "unbekanntes Argument: $1 (siehe --help)"
        exit 2
        ;;
esac
