from __future__ import annotations
import os, shutil, signal, subprocess, time, pytest
from pathlib import Path


@pytest.fixture
def session_bus(tmp_path: Path):
    if shutil.which("dbus-daemon") is None:
        pytest.skip("dbus-daemon not available")
    conf = tmp_path / "session.conf"
    conf.write_text(f"""<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <type>session</type>
  <listen>unix:tmpdir={tmp_path}</listen>
  <policy context="default"><allow send_destination="*"/><allow own="*"/><allow receive_sender="*"/></policy>
</busconfig>
""")
    addr_file = tmp_path / "addr"
    f = open(addr_file, "wb")
    proc = subprocess.Popen([
        "dbus-daemon", f"--config-file={conf}",
        "--print-address=1", "--nofork",
    ], stdout=f)
    try:
        time.sleep(0.4)
        f.close()
        addr = addr_file.read_text().strip()
        if not addr:
            pytest.skip("could not read session bus address")
        os.environ["DBUS_SESSION_BUS_ADDRESS"] = addr
        yield addr
    finally:
        if not f.closed:
            f.close()
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def test_fans_property_distinguishes_auto_disengaged_numeric():
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
    from tpfan_daemon.ipc.dbus_service import TpfanService
    state = {"fans": [(2000, "disengaged"), (2100, "auto"), (2200, "5")]}
    svc = TpfanService(state_getter=lambda: state, command_handler=lambda *a, **k: None)
    assert svc.Fans == [(2000, 0xFE), (2100, 0xFF), (2200, 5)]


def test_curve_getter_handles_missing_state():
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
    from tpfan_daemon.ipc.dbus_service import TpfanService
    svc = TpfanService(state_getter=lambda: {}, command_handler=lambda *a, **k: None)
    assert svc.Curve == []


def test_user_presets_property_exposes_state():
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
    from tpfan_daemon.ipc.dbus_service import TpfanService
    from tpfan_daemon.config import CurveCfg
    state = {
        "user_presets": {
            "A": CurveCfg(sensors=("CPU",), points=((40.0, 0), (80.0, 7))),
        }
    }
    svc = TpfanService(state_getter=lambda: state, command_handler=lambda *a, **k: None)
    result = svc.UserPresets
    assert "A" in result
    points, sensors = result["A"]
    assert points == [(40.0, 0), (80.0, 7)]
    assert sensors == ["CPU"]


def test_save_user_preset_dispatches_command():
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
    from tpfan_daemon.ipc.dbus_service import TpfanService
    calls = []
    svc = TpfanService(state_getter=lambda: {},
                       command_handler=lambda *a, **k: calls.append(a))
    svc.SaveUserPreset("P", [(40.0, 0), (80.0, 7)], ["CPU"],
                       call_info={"sender": ":1.42"})
    assert calls == [("save_user_preset", "P", [(40.0, 0), (80.0, 7)], ["CPU"])]


def test_delete_user_preset_dispatches_command():
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
    from tpfan_daemon.ipc.dbus_service import TpfanService
    calls = []
    svc = TpfanService(state_getter=lambda: {},
                       command_handler=lambda *a, **k: calls.append(a))
    svc.DeleteUserPreset("P", call_info={"sender": ":1.42"})
    assert calls == [("delete_user_preset", "P")]


def test_save_user_preset_checks_polkit():
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
    from tpfan_daemon.ipc.dbus_service import TpfanService
    seen = []
    svc = TpfanService(
        state_getter=lambda: {},
        command_handler=lambda *a, **k: None,
        authorizer=lambda sender, action: seen.append((sender, action)),
    )
    svc.SaveUserPreset("P", [(40.0, 0), (80.0, 7)], ["CPU"],
                       call_info={"sender": ":1.42"})
    assert seen == [(":1.42", "org.tpfan1.manage-presets")]


def test_authorizer_receives_nonempty_sender(session_bus):
    import sys, textwrap, json
    log_path = session_bus  # reuse tmp dir context via env var below
    code = textwrap.dedent(f"""
        import sys, os
        sys.path.insert(0, {repr(os.path.join(os.path.dirname(__file__), '..', 'src'))})
        from dasbus.connection import SessionMessageBus
        from dasbus.loop import EventLoop
        from tpfan_daemon.ipc.dbus_service import TpfanService, BUS_NAME, OBJECT_PATH

        captured = {{"sender": None, "action": None}}
        def authorizer(sender, action):
            captured["sender"] = sender
            captured["action"] = action
            # write to stderr for parent to observe
            import sys
            sys.stderr.write(f"AUTHZ {{sender}} {{action}}\\n")
            sys.stderr.flush()

        svc = TpfanService(
            state_getter=lambda: {{}},
            command_handler=lambda *a, **k: None,
            authorizer=authorizer,
        )
        bus = SessionMessageBus()
        bus.publish_object(OBJECT_PATH, svc)
        bus.register_service(BUS_NAME)
        print("READY", flush=True)
        EventLoop().run()
    """)
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**os.environ},
    )
    try:
        line = proc.stdout.readline()
        assert b"READY" in line, f"server failed: {line!r} stderr={proc.stderr.read()!r}"
        from dasbus.connection import SessionMessageBus
        from tpfan_daemon.ipc.dbus_service import BUS_NAME, OBJECT_PATH
        client_bus = SessionMessageBus()
        proxy = client_bus.get_proxy(BUS_NAME, OBJECT_PATH)
        proxy.SetMode("auto")
        # give server a moment to write
        time.sleep(0.3)
        proc.send_signal(signal.SIGTERM)
        try:
            _, err = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            _, err = proc.communicate(timeout=5)
        text = err.decode(errors="replace")
        # sender must be a non-empty bus name (":x.y")
        assert "AUTHZ" in text, f"authorizer not called: {text!r}"
        line = [ln for ln in text.splitlines() if ln.startswith("AUTHZ")][0]
        parts = line.split()
        assert len(parts) >= 3
        sender = parts[1]
        assert sender.startswith(":"), f"expected non-empty unique bus name, got {sender!r}"
        assert parts[2] == "org.tpfan1.set-mode"
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def test_service_exposes_properties_and_methods(session_bus):
    import sys, textwrap
    code = textwrap.dedent(f"""
        import sys, os
        sys.path.insert(0, {repr(os.path.join(os.path.dirname(__file__), '..', 'src'))})
        from dasbus.connection import SessionMessageBus
        from dasbus.loop import EventLoop
        from tpfan_daemon.ipc.dbus_service import TpfanService, BUS_NAME, OBJECT_PATH
        from tpfan_daemon.config import DEFAULT

        state = {{
            "mode": "auto",
            "level": "auto",
            "temps": {{"CPU": 42.0, "GPU": 45.0}},
            "sensor_describe": {{"CPU": (42.0, "CPU", "k10temp/Tctl")}},
            "fans": [(2200, "auto"), (2100, "auto")],
            "curve": DEFAULT.curve,
            "curve_sensors": list(DEFAULT.curve.sensors),
            "failsafe_temp": DEFAULT.failsafe_temp,
        }}
        svc = TpfanService(state_getter=lambda: state, command_handler=lambda *a, **k: None)
        bus = SessionMessageBus()
        bus.publish_object(OBJECT_PATH, svc)
        bus.register_service(BUS_NAME)
        print("READY", flush=True)
        EventLoop().run()
    """)
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={**os.environ},
    )
    try:
        # wait for READY
        line = proc.stdout.readline()
        assert b"READY" in line, f"server failed to start: {line!r} stderr={proc.stderr.read()!r}"

        from dasbus.connection import AddressedMessageBus
        from tpfan_daemon.ipc.dbus_service import BUS_NAME, OBJECT_PATH
        client_bus = AddressedMessageBus(session_bus)
        proxy = client_bus.get_proxy(BUS_NAME, OBJECT_PATH)
        assert proxy.Mode == "auto"
        assert proxy.CurrentLevel == "auto"
        assert "CPU" in proxy.Sensors
        assert proxy.DaemonVersion
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_set_mode_emits_properties_changed(session_bus):
    """Die GUI hält Mode/Curve über PropertiesChanged aktuell statt zu pollen.

    Ohne dieses Signal müsste sie die Properties sekündlich lesen, und jeder
    Property-Read kostet den Daemon einen kompletten Sensor-Sweep.
    """
    import sys, textwrap, time
    code = textwrap.dedent(f"""
        import sys, os
        sys.path.insert(0, {repr(os.path.join(os.path.dirname(__file__), '..', 'src'))})
        from dasbus.connection import SessionMessageBus
        from dasbus.loop import EventLoop
        from tpfan_daemon.ipc.dbus_service import TpfanService, BUS_NAME, OBJECT_PATH
        from tpfan_daemon.config import DEFAULT

        state = {{"mode": "auto", "level": "auto", "curve": DEFAULT.curve,
                  "curve_sensors": list(DEFAULT.curve.sensors)}}

        def handler(cmd, *args):
            if cmd == "set_mode":
                state["mode"] = args[0]

        svc = TpfanService(state_getter=lambda: state, command_handler=handler)
        bus = SessionMessageBus()
        bus.publish_object(OBJECT_PATH, svc)
        bus.register_service(BUS_NAME)
        print("READY", flush=True)
        EventLoop().run()
    """)
    proc = subprocess.Popen([sys.executable, "-c", code],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env={**os.environ})
    try:
        line = proc.stdout.readline()
        assert b"READY" in line, f"server failed to start: {line!r} stderr={proc.stderr.read()!r}"

        from gi.repository import GLib
        from dasbus.connection import AddressedMessageBus
        from tpfan_daemon.ipc.dbus_service import BUS_NAME, OBJECT_PATH, IFACE
        client_bus = AddressedMessageBus(session_bus)
        proxy = client_bus.get_proxy(BUS_NAME, OBJECT_PATH)

        seen: list[tuple[str, dict]] = []
        proxy.PropertiesChanged.connect(
            lambda iface, changed, invalid: seen.append((iface, dict(changed))))

        proxy.SetMode("curve")

        ctx = GLib.MainContext.default()
        deadline = time.monotonic() + 5.0
        while not seen and time.monotonic() < deadline:
            ctx.iteration(False)
            time.sleep(0.01)

        assert seen, "kein PropertiesChanged empfangen"
        iface, changed = seen[0]
        assert iface == IFACE
        assert changed["Mode"].get_string() == "curve"
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_set_curve_reports_curve_and_sensors(session_bus):
    import sys, textwrap, time
    code = textwrap.dedent(f"""
        import sys, os
        sys.path.insert(0, {repr(os.path.join(os.path.dirname(__file__), '..', 'src'))})
        from dasbus.connection import SessionMessageBus
        from dasbus.loop import EventLoop
        from tpfan_daemon.ipc.dbus_service import TpfanService, BUS_NAME, OBJECT_PATH
        from tpfan_daemon.config import CurveCfg, DEFAULT

        state = {{"mode": "curve", "curve": DEFAULT.curve,
                  "curve_sensors": list(DEFAULT.curve.sensors)}}

        def handler(cmd, *args):
            if cmd == "set_curve":
                points, sensors = args
                state["curve"] = CurveCfg(sensors=tuple(sensors), points=tuple(points))
                state["curve_sensors"] = list(sensors)

        svc = TpfanService(state_getter=lambda: state, command_handler=handler)
        bus = SessionMessageBus()
        bus.publish_object(OBJECT_PATH, svc)
        bus.register_service(BUS_NAME)
        print("READY", flush=True)
        EventLoop().run()
    """)
    proc = subprocess.Popen([sys.executable, "-c", code],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env={**os.environ})
    try:
        line = proc.stdout.readline()
        assert b"READY" in line, f"server failed to start: {line!r} stderr={proc.stderr.read()!r}"

        from gi.repository import GLib
        from dasbus.connection import AddressedMessageBus
        from tpfan_daemon.ipc.dbus_service import BUS_NAME, OBJECT_PATH
        client_bus = AddressedMessageBus(session_bus)
        proxy = client_bus.get_proxy(BUS_NAME, OBJECT_PATH)

        seen: list[dict] = []
        proxy.PropertiesChanged.connect(
            lambda iface, changed, invalid: seen.append(dict(changed)))

        proxy.SetCurve([(45.0, 1), (85.0, 7)], ["CPU"])

        ctx = GLib.MainContext.default()
        deadline = time.monotonic() + 5.0
        while not seen and time.monotonic() < deadline:
            ctx.iteration(False)
            time.sleep(0.01)

        assert seen, "kein PropertiesChanged empfangen"
        changed = seen[0]
        assert set(changed) == {"Curve", "CurveSensors"}
        assert changed["CurveSensors"].unpack() == ["CPU"]
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
