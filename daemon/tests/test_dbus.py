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


def test_curve_getter_handles_missing_state():
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
    from tpfan_daemon.ipc.dbus_service import TpfanService
    svc = TpfanService(state_getter=lambda: {}, command_handler=lambda *a, **k: None)
    assert svc.Curve == []


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

        from dasbus.connection import SessionMessageBus
        from tpfan_daemon.ipc.dbus_service import BUS_NAME, OBJECT_PATH
        client_bus = SessionMessageBus()
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
