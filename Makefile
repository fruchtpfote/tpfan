.PHONY: dev test test-daemon test-gui install uninstall clean

VENV ?= .venv
PY   := $(VENV)/bin/python
PIP  := $(VENV)/bin/pip

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
	rm -rf $(VENV) .pytest_cache
	find . -name '*.egg-info' -type d -exec rm -rf {} +
