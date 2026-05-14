.PHONY: dev test test-daemon test-gui install uninstall clean dist

VENV ?= .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip

VERSION := $(shell sed -n 's/^__version__ = "\(.*\)"/\1/p' daemon/src/tpfan_daemon/__init__.py)
DIST_DIR := dist
TARBALL  := $(DIST_DIR)/tpfan-$(VERSION).tar.gz

$(VENV)/bin/activate:
	python3 -m venv $(VENV)
	$(PIP) install --upgrade pip

dev: $(VENV)/bin/activate
	$(PIP) install -e ./daemon[dev]
	$(PIP) install -e ./gui[dev]

test: test-daemon test-gui

test-daemon:
	$(PY) -m pytest daemon/tests -q

test-gui:
	$(PY) -m pytest gui/tests -q

install:
	install -D -m 0755 packaging/tpfan-daemon-launcher /usr/local/bin/tpfan-daemon
	install -D -m 0755 packaging/tpfan-gui-launcher    /usr/local/bin/tpfan-gui
	install -D -m 0644 packaging/tpfan-daemon.service  /etc/systemd/system/tpfan-daemon.service
	install -D -m 0644 packaging/org.tpfan1.conf       /etc/dbus-1/system.d/org.tpfan1.conf
	install -D -m 0644 packaging/org.tpfan1.service    /usr/share/dbus-1/system-services/org.tpfan1.service
	install -D -m 0644 packaging/org.tpfan1.policy     /usr/share/polkit-1/actions/org.tpfan1.policy
	install -D -m 0644 packaging/tpfan-modprobe.conf   /etc/modprobe.d/tpfan.conf
	install -D -m 0644 packaging/tpfan-gui.desktop     /usr/share/applications/tpfan-gui.desktop
	systemctl daemon-reload

uninstall:
	rm -f /usr/local/bin/tpfan-daemon /usr/local/bin/tpfan-gui
	rm -f /etc/systemd/system/tpfan-daemon.service
	rm -f /etc/dbus-1/system.d/org.tpfan1.conf
	rm -f /usr/share/dbus-1/system-services/org.tpfan1.service
	rm -f /usr/share/polkit-1/actions/org.tpfan1.policy
	rm -f /etc/modprobe.d/tpfan.conf
	rm -f /usr/share/applications/tpfan-gui.desktop
	systemctl daemon-reload

clean:
	rm -rf $(VENV) .pytest_cache $(DIST_DIR)
	find . -name '*.egg-info' -type d -exec rm -rf {} +

# Schnürt ein selbstständig installierbares Archiv mit allen Files,
# die scripts/install.sh braucht. Name: tpfan-<VERSION>.tar.gz.
dist:
	@test -n "$(VERSION)" || (echo "konnte VERSION nicht ermitteln" >&2; exit 1)
	@echo "packe Release-Archiv für Version $(VERSION)"
	mkdir -p $(DIST_DIR)
	tar --owner=0 --group=0 \
	    --transform 's,^,tpfan-$(VERSION)/,' \
	    --exclude='__pycache__' \
	    --exclude='*.egg-info' \
	    --exclude='.coverage' \
	    --exclude='build' \
	    --exclude='dist' \
	    -czf $(TARBALL) \
	    daemon/pyproject.toml daemon/src daemon/tests \
	    gui/pyproject.toml gui/src gui/tests \
	    packaging scripts Makefile README.md
	@echo "Archiv: $(TARBALL)"
