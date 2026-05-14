# User-Presets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** User kann eigene Lüfterkurven im Kurven-Editor unter beliebigem Namen speichern, wieder laden und löschen. Daten landen in `/etc/tpfan/config.toml` unter `[user_presets.*]`.

**Architecture:** Erweiterung in drei Schichten: (1) `Config` bekommt `user_presets: dict[str, CurveCfg]` mit TOML-Roundtrip; (2) `Daemon` bekommt zwei Handler `save_user_preset`/`delete_user_preset` mit Validierung; (3) D-Bus exponiert Property `UserPresets` + Methoden `SaveUserPreset`/`DeleteUserPreset` über neue Polkit-Action `org.tpfan1.manage-presets`. GUI ergänzt im Kurven-Editor einen „Speichern als …"-Button und löschbare User-Preset-Buttons.

**Tech Stack:** Python 3.11+, `tomllib`/manuelles TOML-Serialize (bestehend), `dasbus`, PyQt6, pytest.

**Spec:** `docs/superpowers/specs/2026-05-14-user-presets-design.md`

---

## File Structure

**Modify:**
- `daemon/src/tpfan_daemon/config.py` — `Config.user_presets`, TOML-Read/Write, Namens-Validierung
- `daemon/src/tpfan_daemon/daemon.py` — `save_user_preset` / `delete_user_preset` Handler
- `daemon/src/tpfan_daemon/__main__.py` — `_state_dict` um `user_presets` ergänzen
- `daemon/src/tpfan_daemon/ipc/dbus_service.py` — Property + Methoden + Polkit-Check
- `packaging/org.tpfan1.policy` — neue Polkit-Action
- `gui/src/tpfan_gui/ipc/dbus_client.py` — Client-Methoden
- `gui/src/tpfan_gui/views/curve_editor.py` — UI-Erweiterung
- `gui/src/tpfan_gui/main_window.py` — Sync nach Connect/Änderung

**Modify (Tests):**
- `daemon/tests/test_config.py` — Roundtrip + Validierung
- `daemon/tests/test_daemon_glue.py` — Handler-Tests
- `daemon/tests/test_dbus.py` — D-Bus-Methoden-Tests
- `gui/tests/test_curve_editor.py` — UI-Tests
- `gui/tests/test_dbus_client.py` — Client-Methoden-Tests

---

### Task 1: Config — `user_presets` Datenmodell + Roundtrip

**Files:**
- Modify: `daemon/src/tpfan_daemon/config.py`
- Test: `daemon/tests/test_config.py`

- [ ] **Step 1: Write failing test for roundtrip**

In `daemon/tests/test_config.py` ergänzen:

```python
def test_user_presets_roundtrip(tmp_path: Path):
    p = tmp_path / "c.toml"
    cfg = Config(
        user_presets={
            "Mein Preset": CurveCfg(
                sensors=("CPU", "GPU"),
                points=((42.0, 0), (60.0, 2), (80.0, 7)),
            ),
            "Zweites": CurveCfg(
                sensors=("CPU",),
                points=((40.0, 0), (80.0, 7)),
            ),
        }
    )
    save(p, cfg)
    loaded = load(p)
    assert loaded.user_presets == cfg.user_presets


def test_user_presets_validates_points(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text(
        '''
        mode = "curve"
        manual_level = "3"
        failsafe_temp = 95.0
        [curve]
        sensors = ["CPU"]
        points = [[40, 0], [80, 7]]
        [user_presets."Kaputt"]
        sensors = ["CPU"]
        points = [[70, 4], [55, 2]]
        '''
    )
    with pytest.raises(ValueError, match="monotonic"):
        load(p)
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd /home/matthias/programmieren/tmp-fan && python -m pytest daemon/tests/test_config.py::test_user_presets_roundtrip daemon/tests/test_config.py::test_user_presets_validates_points -v`
Expected: FAIL (Config hat kein `user_presets` Feld).

- [ ] **Step 3: Add `user_presets` to `Config` and parse/serialize**

In `daemon/src/tpfan_daemon/config.py`:

```python
import re

_PRESET_NAME_RE = re.compile(r"^[A-Za-z0-9 _-]{1,64}$")


def validate_preset_name(name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("preset name must be a string")
    if not _PRESET_NAME_RE.match(name):
        raise ValueError(f"invalid preset name: {name!r}")
    return name
```

`Config` erweitern (nach `profiles`):

```python
@dataclass(frozen=True)
class Config:
    mode: str = "curve"
    manual_level: str = "3"
    failsafe_temp: float = 95.0
    curve: CurveCfg = field(default_factory=CurveCfg.from_default)
    profiles: dict[str, CurveCfg] = field(default_factory=dict)
    user_presets: dict[str, CurveCfg] = field(default_factory=dict)
```

In `load(path)` nach den `profiles`-Zeilen ergänzen:

```python
    user_presets = {
        validate_preset_name(k): _validate_curve(v)
        for k, v in raw.get("user_presets", {}).items()
    }
    return Config(mode=mode, manual_level=manual_level,
                  failsafe_temp=failsafe_temp, curve=curve,
                  profiles=profiles, user_presets=user_presets)
```

In `_serialize(cfg)` direkt nach der `profiles`-Schleife:

```python
    for name, c in cfg.user_presets.items():
        # TOML-Quoted-Keys, damit Leerzeichen erlaubt sind
        out.append(f'[user_presets."{name}"]')
        out.append(_curve(c))
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd /home/matthias/programmieren/tmp-fan && python -m pytest daemon/tests/test_config.py -v`
Expected: PASS für alle Tests.

- [ ] **Step 5: Commit**

```bash
git add daemon/src/tpfan_daemon/config.py daemon/tests/test_config.py
git commit -m "feat(config): user_presets field with TOML roundtrip and name validation"
```

---

### Task 2: Daemon-Handler `save_user_preset` / `delete_user_preset`

**Files:**
- Modify: `daemon/src/tpfan_daemon/daemon.py`
- Test: `daemon/tests/test_daemon_glue.py`

- [ ] **Step 1: Write failing tests**

In `daemon/tests/test_daemon_glue.py` ergänzen:

```python
def test_save_user_preset_persists(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    d = Daemon(config_path=cfg_path, sensors=StubSensors(), fan=StubFan())
    d.handle("save_user_preset", "Mein Preset", [(42.0, 0), (80.0, 7)], ["CPU"])
    assert "Mein Preset" in d.loop.config.user_presets
    assert d.loop.config.user_presets["Mein Preset"].points == ((42.0, 0), (80.0, 7))
    assert "Mein Preset" in load(cfg_path).user_presets


def test_save_user_preset_overwrites(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    d = Daemon(config_path=cfg_path, sensors=StubSensors(), fan=StubFan())
    d.handle("save_user_preset", "X", [(40.0, 0), (80.0, 7)], ["CPU"])
    d.handle("save_user_preset", "X", [(50.0, 1), (90.0, 7)], ["CPU"])
    assert d.loop.config.user_presets["X"].points == ((50.0, 1), (90.0, 7))


def test_save_user_preset_rejects_bad_name(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    d = Daemon(config_path=cfg_path, sensors=StubSensors(), fan=StubFan())
    with pytest.raises(ValueError):
        d.handle("save_user_preset", "", [(40.0, 0), (80.0, 7)], ["CPU"])
    with pytest.raises(ValueError):
        d.handle("save_user_preset", "bad/name", [(40.0, 0), (80.0, 7)], ["CPU"])
    with pytest.raises(ValueError):
        d.handle("save_user_preset", "x" * 65, [(40.0, 0), (80.0, 7)], ["CPU"])


def test_save_user_preset_rejects_bad_points(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    d = Daemon(config_path=cfg_path, sensors=StubSensors(), fan=StubFan())
    with pytest.raises(ValueError):
        d.handle("save_user_preset", "P", [(70.0, 4), (55.0, 2)], ["CPU"])  # nicht monoton


def test_save_user_preset_rejects_unknown_sensor(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    d = Daemon(config_path=cfg_path, sensors=StubSensors(), fan=StubFan())
    with pytest.raises(ValueError):
        d.handle("save_user_preset", "P", [(40.0, 0), (80.0, 7)], ["NOPE"])


def test_save_user_preset_rejects_empty_sensors(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    d = Daemon(config_path=cfg_path, sensors=StubSensors(), fan=StubFan())
    with pytest.raises(ValueError):
        d.handle("save_user_preset", "P", [(40.0, 0), (80.0, 7)], [])


def test_delete_user_preset(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    d = Daemon(config_path=cfg_path, sensors=StubSensors(), fan=StubFan())
    d.handle("save_user_preset", "P", [(40.0, 0), (80.0, 7)], ["CPU"])
    d.handle("delete_user_preset", "P")
    assert "P" not in d.loop.config.user_presets
    assert "P" not in load(cfg_path).user_presets


def test_delete_user_preset_unknown(tmp_path: Path):
    cfg_path = tmp_path / "config.toml"
    d = Daemon(config_path=cfg_path, sensors=StubSensors(), fan=StubFan())
    with pytest.raises(ValueError, match="unknown preset"):
        d.handle("delete_user_preset", "nope")
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd /home/matthias/programmieren/tmp-fan && python -m pytest daemon/tests/test_daemon_glue.py -v`
Expected: FAIL — `unknown command: save_user_preset`.

- [ ] **Step 3: Implement handlers**

In `daemon/src/tpfan_daemon/daemon.py` Imports erweitern:

```python
from .config import CurveCfg, DEFAULT, load, save, _validate_points, VALID_LEVELS, validate_preset_name
```

In `Daemon.handle` vor dem `else`-Zweig zwei neue Branches einfügen:

```python
        elif cmd == "save_user_preset":
            name, points, sensors_ = args
            validate_preset_name(name)
            if not sensors_:
                raise ValueError("save_user_preset requires at least one sensor")
            pts = _validate_points([list(p) for p in points])
            known = set(self.sensors.read_all().keys())
            for s in sensors_:
                if s not in known:
                    raise ValueError(f"unknown sensor: {s}")
            new_presets = {**self.loop.config.user_presets,
                           name: CurveCfg(sensors=tuple(sensors_), points=pts)}
            self.loop.set_config(replace(self.loop.config, user_presets=new_presets))
            self._save()
        elif cmd == "delete_user_preset":
            name = args[0]
            if name not in self.loop.config.user_presets:
                raise ValueError(f"unknown preset: {name}")
            new_presets = {k: v for k, v in self.loop.config.user_presets.items() if k != name}
            self.loop.set_config(replace(self.loop.config, user_presets=new_presets))
            self._save()
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd /home/matthias/programmieren/tmp-fan && python -m pytest daemon/tests/test_daemon_glue.py -v`
Expected: PASS für alle neuen Tests, kein Regress.

- [ ] **Step 5: Commit**

```bash
git add daemon/src/tpfan_daemon/daemon.py daemon/tests/test_daemon_glue.py
git commit -m "feat(daemon): save_user_preset and delete_user_preset handlers"
```

---

### Task 3: D-Bus — Property + Methoden + state-getter

**Files:**
- Modify: `daemon/src/tpfan_daemon/ipc/dbus_service.py`
- Modify: `daemon/src/tpfan_daemon/__main__.py`
- Test: `daemon/tests/test_dbus.py`

- [ ] **Step 1: Inspect existing dbus test patterns**

Run: `cd /home/matthias/programmieren/tmp-fan && grep -n "def test_\|_state_getter\|TpfanService\|Curve\|SetCurve" daemon/tests/test_dbus.py | head -40`

Lies aus dem Output, wie bestehende Property/Method-Tests `TpfanService` instanziieren (via `state_getter` + `command_handler` Lambdas). Verwende dasselbe Muster für die neuen Tests.

- [ ] **Step 2: Write failing tests**

In `daemon/tests/test_dbus.py` ergänzen (Pattern aus existierenden Tests in der Datei übernehmen):

```python
def test_user_presets_property_exposes_state():
    state = {
        "user_presets": {
            "A": __import__("tpfan_daemon.config", fromlist=["CurveCfg"]).CurveCfg(
                sensors=("CPU",), points=((40.0, 0), (80.0, 7))),
        }
    }
    svc = TpfanService(state_getter=lambda: state, command_handler=lambda *a, **k: None)
    result = svc.UserPresets
    assert "A" in result
    points, sensors = result["A"]
    assert points == [(40.0, 0), (80.0, 7)]
    assert sensors == ["CPU"]


def test_save_user_preset_dispatches_command():
    calls = []
    svc = TpfanService(state_getter=lambda: {},
                       command_handler=lambda *a, **k: calls.append(a))
    svc.SaveUserPreset("P", [(40.0, 0), (80.0, 7)], ["CPU"],
                       call_info={"sender": ":1.42"})
    assert calls == [("save_user_preset", "P", [(40.0, 0), (80.0, 7)], ["CPU"])]


def test_delete_user_preset_dispatches_command():
    calls = []
    svc = TpfanService(state_getter=lambda: {},
                       command_handler=lambda *a, **k: calls.append(a))
    svc.DeleteUserPreset("P", call_info={"sender": ":1.42"})
    assert calls == [("delete_user_preset", "P")]


def test_save_user_preset_checks_polkit():
    seen = []
    svc = TpfanService(
        state_getter=lambda: {},
        command_handler=lambda *a, **k: None,
        authorizer=lambda sender, action: seen.append((sender, action)),
    )
    svc.SaveUserPreset("P", [(40.0, 0), (80.0, 7)], ["CPU"],
                       call_info={"sender": ":1.42"})
    assert seen == [(":1.42", "org.tpfan1.manage-presets")]
```

- [ ] **Step 3: Run tests, verify they fail**

Run: `cd /home/matthias/programmieren/tmp-fan && python -m pytest daemon/tests/test_dbus.py -v -k user_preset`
Expected: FAIL — Property/Methoden existieren nicht.

- [ ] **Step 4: Add property and methods**

In `daemon/src/tpfan_daemon/ipc/dbus_service.py` nach der `CurveSensors`-Property einfügen:

```python
    @property
    def UserPresets(self) -> Dict[Str, Tuple[List[Tuple[Double, Byte]], List[Str]]]:
        out: dict[str, tuple[list[tuple[float, int]], list[str]]] = {}
        for name, cv in self._state().get("user_presets", {}).items():
            out[str(name)] = (
                [(float(t), int(l)) for t, l in cv.points],
                list(cv.sensors),
            )
        return out
```

Im Methoden-Bereich nach `SetFailsafeTemp` ergänzen:

```python
    @accepts_additional_arguments
    def SaveUserPreset(self, name: Str, points: List[Tuple[Double, Byte]],
                       sensors: List[Str], *, call_info) -> None:
        self._check("org.tpfan1.manage-presets", call_info.get("sender", ""))
        self._cmd("save_user_preset", str(name),
                  [(float(t), int(l)) for t, l in points], list(sensors))

    @accepts_additional_arguments
    def DeleteUserPreset(self, name: Str, *, call_info) -> None:
        self._check("org.tpfan1.manage-presets", call_info.get("sender", ""))
        self._cmd("delete_user_preset", str(name))
```

In `daemon/src/tpfan_daemon/__main__.py` Funktion `_state_dict` um eine Zeile erweitern (direkt vor dem schließenden `}`):

```python
        "user_presets": d.loop.config.user_presets,
```

- [ ] **Step 5: Run tests, verify they pass**

Run: `cd /home/matthias/programmieren/tmp-fan && python -m pytest daemon/tests/test_dbus.py -v`
Expected: PASS, kein Regress.

- [ ] **Step 6: Commit**

```bash
git add daemon/src/tpfan_daemon/ipc/dbus_service.py daemon/src/tpfan_daemon/__main__.py daemon/tests/test_dbus.py
git commit -m "feat(dbus): UserPresets property and Save/Delete methods"
```

---

### Task 4: Polkit-Policy `manage-presets`

**Files:**
- Modify: `packaging/org.tpfan1.policy`

- [ ] **Step 1: Add action**

In `packaging/org.tpfan1.policy` vor `</policyconfig>` einfügen:

```xml
  <action id="org.tpfan1.manage-presets">
    <description>Eigene Lüfter-Presets verwalten</description>
    <message>Authentifizierung erforderlich, um eigene Presets zu speichern oder zu löschen.</message>
    <defaults>
      <allow_active>auth_admin_keep</allow_active>
      <allow_inactive>auth_admin</allow_inactive>
      <allow_any>no</allow_any>
    </defaults>
  </action>
```

- [ ] **Step 2: Syntax-Check**

Run: `cd /home/matthias/programmieren/tmp-fan && xmllint --noout packaging/org.tpfan1.policy && echo OK`
Expected: `OK`. (Falls `xmllint` fehlt: `python -c "import xml.etree.ElementTree as ET; ET.parse('packaging/org.tpfan1.policy'); print('OK')"`.)

- [ ] **Step 3: Commit**

```bash
git add packaging/org.tpfan1.policy
git commit -m "feat(packaging): polkit action manage-presets"
```

---

### Task 5: GUI-Client — `save_user_preset` / `delete_user_preset`

**Files:**
- Modify: `gui/src/tpfan_gui/ipc/dbus_client.py`
- Test: `gui/tests/test_dbus_client.py`

- [ ] **Step 1: Write failing tests**

In `gui/tests/test_dbus_client.py` ergänzen (Pattern aus existierenden `set_curve`-Tests übernehmen). Falls die Datei `_FakeProxy`/Stub-Klasse benutzt, dieselbe Klasse nutzen:

```python
def test_save_user_preset_calls_proxy():
    from tpfan_gui.ipc.dbus_client import _ProxyOps

    class Fake:
        def __init__(self): self.calls = []
        def SaveUserPreset(self, name, points, sensors):
            self.calls.append(("save", name, points, sensors))
        def DeleteUserPreset(self, name):
            self.calls.append(("delete", name))

    class Ops(_ProxyOps):
        def __init__(self, proxy): self._proxy = proxy

    fake = Fake()
    ops = Ops(fake)
    ops.save_user_preset("P", [(40.0, 0), (80.0, 7)], ["CPU"])
    ops.delete_user_preset("P")
    assert fake.calls == [
        ("save", "P", [(40.0, 0), (80.0, 7)], ["CPU"]),
        ("delete", "P"),
    ]


def test_save_user_preset_raises_when_disconnected():
    from tpfan_gui.ipc.dbus_client import _ProxyOps, DaemonNotConnected

    class Ops(_ProxyOps):
        def __init__(self): self._proxy = None

    ops = Ops()
    import pytest
    with pytest.raises(DaemonNotConnected):
        ops.save_user_preset("P", [(40.0, 0), (80.0, 7)], ["CPU"])
    with pytest.raises(DaemonNotConnected):
        ops.delete_user_preset("P")
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `cd /home/matthias/programmieren/tmp-fan && python -m pytest gui/tests/test_dbus_client.py -v -k user_preset`
Expected: FAIL — Methoden fehlen.

- [ ] **Step 3: Add client methods**

In `gui/src/tpfan_gui/ipc/dbus_client.py` in `_ProxyOps` direkt nach `set_curve` ergänzen:

```python
    def save_user_preset(self, name: str, points, sensors):
        self._require_proxy().SaveUserPreset(name, points, sensors)
    def delete_user_preset(self, name: str):
        self._require_proxy().DeleteUserPreset(name)
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `cd /home/matthias/programmieren/tmp-fan && python -m pytest gui/tests/test_dbus_client.py -v`
Expected: PASS, kein Regress.

- [ ] **Step 5: Commit**

```bash
git add gui/src/tpfan_gui/ipc/dbus_client.py gui/tests/test_dbus_client.py
git commit -m "feat(gui/ipc): save_user_preset and delete_user_preset client methods"
```

---

### Task 6: Curve-Editor — „Speichern als …" + User-Preset-Buttons

**Files:**
- Modify: `gui/src/tpfan_gui/views/curve_editor.py`
- Test: `gui/tests/test_curve_editor.py`

- [ ] **Step 1: Inspect existing test patterns**

Run: `cd /home/matthias/programmieren/tmp-fan && grep -n "def test_\|preset_buttons\|apply_preset\|qtbot\|QApplication" gui/tests/test_curve_editor.py | head -30`

Notiere, wie der `make_widget`-Editor in den existierenden Tests aufgebaut wird (QApplication-Fixture vs. qtbot). Falls die Datei `qtbot` benutzt: die folgenden Tests verwenden ebenfalls `qtbot`.

- [ ] **Step 2: Write failing tests**

In `gui/tests/test_curve_editor.py` ergänzen (Fixture-Stil aus bestehenden Tests übernehmen — Tests werden nur ausgeführt, wenn pytest-qt verfügbar; bei `qtbot`-Fehlern bleibt der Test wie auch andere im File errored, das ist akzeptiert).

```python
def test_set_user_presets_creates_buttons(qtbot):
    from tpfan_gui.views.curve_editor import CurveModel, make_widget, PRESETS
    model = CurveModel(points=[(40.0, 0), (80.0, 7)])
    w = make_widget(model, on_change=lambda pts: None)
    qtbot.addWidget(w)
    w.set_user_presets({
        "Meins": ([(42.0, 0), (80.0, 7)], ["CPU"]),
    })
    names = [b.text() for b in w.user_preset_buttons]
    assert names == ["Meins"]
    # Built-ins bleiben unverändert
    assert [b.text() for b in w.preset_buttons] == [n for n, _ in PRESETS]


def test_user_preset_button_loads_points(qtbot):
    from tpfan_gui.views.curve_editor import CurveModel, make_widget
    model = CurveModel(points=[(40.0, 0), (80.0, 7)])
    w = make_widget(model, on_change=lambda pts: None)
    qtbot.addWidget(w)
    w.set_user_presets({"Meins": ([(42.0, 0), (60.0, 3), (80.0, 7)], ["CPU"])})
    w.user_preset_buttons[0].click()
    assert model.points == [(42.0, 0), (60.0, 3), (80.0, 7)]


def test_save_as_button_invokes_callback(qtbot, monkeypatch):
    from tpfan_gui.views.curve_editor import CurveModel, make_widget
    from PyQt6 import QtWidgets
    monkeypatch.setattr(QtWidgets.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Mein Name", True)))
    saved = []
    model = CurveModel(points=[(45.0, 0), (80.0, 7)])
    w = make_widget(model, on_change=lambda pts: None,
                    on_save_preset=lambda name, pts: saved.append((name, list(pts))))
    qtbot.addWidget(w)
    w.save_as_btn.click()
    assert saved == [("Mein Name", [(45.0, 0), (80.0, 7)])]


def test_save_as_cancelled_does_nothing(qtbot, monkeypatch):
    from tpfan_gui.views.curve_editor import CurveModel, make_widget
    from PyQt6 import QtWidgets
    monkeypatch.setattr(QtWidgets.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("", False)))
    saved = []
    model = CurveModel(points=[(45.0, 0), (80.0, 7)])
    w = make_widget(model, on_change=lambda pts: None,
                    on_save_preset=lambda name, pts: saved.append(name))
    qtbot.addWidget(w)
    w.save_as_btn.click()
    assert saved == []


def test_save_as_rejects_builtin_collision(qtbot, monkeypatch):
    from tpfan_gui.views.curve_editor import CurveModel, make_widget
    from PyQt6 import QtWidgets
    monkeypatch.setattr(QtWidgets.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Sehr ruhig", True)))
    warned = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "warning",
                        staticmethod(lambda *a, **k: warned.append(a)))
    saved = []
    model = CurveModel(points=[(45.0, 0), (80.0, 7)])
    w = make_widget(model, on_change=lambda pts: None,
                    on_save_preset=lambda name, pts: saved.append(name))
    qtbot.addWidget(w)
    w.save_as_btn.click()
    assert saved == []
    assert warned  # Warnung wurde gezeigt


def test_user_preset_delete_button_invokes_callback(qtbot, monkeypatch):
    from tpfan_gui.views.curve_editor import CurveModel, make_widget
    from PyQt6 import QtWidgets
    monkeypatch.setattr(QtWidgets.QMessageBox, "question",
                        staticmethod(lambda *a, **k: QtWidgets.QMessageBox.StandardButton.Yes))
    deleted = []
    model = CurveModel(points=[(40.0, 0), (80.0, 7)])
    w = make_widget(model, on_change=lambda pts: None,
                    on_delete_preset=lambda name: deleted.append(name))
    qtbot.addWidget(w)
    w.set_user_presets({"Meins": ([(42.0, 0), (80.0, 7)], ["CPU"])})
    w.user_preset_delete_buttons[0].click()
    assert deleted == ["Meins"]
```

- [ ] **Step 3: Run tests, verify they fail**

Run: `cd /home/matthias/programmieren/tmp-fan && python -m pytest gui/tests/test_curve_editor.py -v -k "user_preset or save_as"`
Expected: FAIL — Methoden/Buttons fehlen.

- [ ] **Step 4: Extend `make_widget`**

In `gui/src/tpfan_gui/views/curve_editor.py` die Signatur von `make_widget` erweitern:

```python
def make_widget(model: CurveModel, on_change, parent=None,
                on_save_preset=None, on_delete_preset=None):
```

In `CurveEditor.__init__` direkt nach dem Block, der `preset_row` mit den Built-in-Buttons aufbaut, hinzufügen:

```python
            self.user_preset_row = QHBoxLayout()
            self.user_preset_row.addWidget(QLabel("Eigene:"))
            self.user_preset_buttons: list[QPushButton] = []
            self.user_preset_delete_buttons: list[QPushButton] = []
            self._user_presets: dict[str, tuple[list[tuple[float, int]], list[str]]] = {}
            lay.addLayout(self.user_preset_row)
```

Im Button-Row für „Anwenden" ergänzen:

```python
            self.save_as_btn = QPushButton("Speichern als …")
            self.save_as_btn.clicked.connect(self._on_save_as)
            row.addWidget(self.save_as_btn)
```

`_BUILTIN_NAMES` als Modul-Konstante (oben in der Datei nach `PRESETS`):

```python
_BUILTIN_NAMES = frozenset(name for name, _ in PRESETS)
```

Neue Methoden in `CurveEditor`:

```python
        def set_user_presets(self, presets: dict) -> None:
            from PyQt6.QtWidgets import QPushButton
            # Bestehende Buttons entfernen
            for b in self.user_preset_buttons + self.user_preset_delete_buttons:
                self.user_preset_row.removeWidget(b)
                b.deleteLater()
            self.user_preset_buttons = []
            self.user_preset_delete_buttons = []
            self._user_presets = dict(presets)
            for name, (pts, _sensors) in presets.items():
                b = QPushButton(name)
                b.setToolTip(f"Eigenes Preset '{name}' laden")
                b.clicked.connect(lambda _=False, p=list(pts): self.apply_preset(p))
                self.user_preset_row.addWidget(b)
                self.user_preset_buttons.append(b)
                d = QPushButton("×")
                d.setToolTip(f"Preset '{name}' löschen")
                d.setMaximumWidth(24)
                d.clicked.connect(lambda _=False, n=name: self._on_delete(n))
                self.user_preset_row.addWidget(d)
                self.user_preset_delete_buttons.append(d)

        def _on_save_as(self) -> None:
            from PyQt6.QtWidgets import QInputDialog, QMessageBox
            name, ok = QInputDialog.getText(self, "Preset speichern", "Name:")
            if not ok or not name:
                return
            if name in _BUILTIN_NAMES:
                QMessageBox.warning(self, "tpfan",
                    f"'{name}' ist ein vordefiniertes Preset und kann nicht überschrieben werden.")
                return
            if on_save_preset is not None:
                on_save_preset(name, list(model.points))

        def _on_delete(self, name: str) -> None:
            from PyQt6.QtWidgets import QMessageBox
            answer = QMessageBox.question(self, "Preset löschen",
                f"Preset '{name}' wirklich löschen?")
            if answer != QMessageBox.StandardButton.Yes:
                return
            if on_delete_preset is not None:
                on_delete_preset(name)
```

- [ ] **Step 5: Run tests, verify they pass**

Run: `cd /home/matthias/programmieren/tmp-fan && python -m pytest gui/tests/test_curve_editor.py -v`
Expected: Neue Tests PASS (pre-existing errored qtbot-Tests bleiben wie zuvor; siehe Memory-Eintrag zu Reviewer-Polish).

- [ ] **Step 6: Commit**

```bash
git add gui/src/tpfan_gui/views/curve_editor.py gui/tests/test_curve_editor.py
git commit -m "feat(gui): user presets — save-as dialog and per-preset delete button"
```

---

### Task 7: Main-Window — User-Presets vom Daemon syncen

**Files:**
- Modify: `gui/src/tpfan_gui/main_window.py`
- Test: `gui/tests/test_main_window.py`

- [ ] **Step 1: Inspect existing test pattern**

Run: `cd /home/matthias/programmieren/tmp-fan && cat gui/tests/test_main_window.py`

Notiere, wie der MainWindow-Test einen Stub-Client baut (typischerweise mit `get`-Methode, `set_curve`, Signals). Verwende dasselbe Stub-Schema für die neuen Tests.

- [ ] **Step 2: Write failing test**

In `gui/tests/test_main_window.py` ergänzen (Stub-Pattern aus existierendem Test in der Datei kopieren):

```python
def test_main_window_syncs_user_presets_on_connect(qtbot):
    from tpfan_gui.main_window import MainWindow
    from PyQt6.QtCore import QObject, pyqtSignal

    class StubClient(QObject):
        tickReceived = pyqtSignal(object)
        emergency = pyqtSignal(float, str)
        connected = pyqtSignal(bool)
        propertiesChanged = pyqtSignal(dict)

        def __init__(self):
            super().__init__()
            self.props = {
                "Curve": [(40.0, 0), (80.0, 7)],
                "UserPresets": {"Meins": ([(42.0, 0), (80.0, 7)], ["CPU"])},
            }
            self.save_calls = []
            self.delete_calls = []

        def get(self, name): return self.props.get(name)
        def set_curve(self, points, sensors): pass
        def set_mode(self, m): pass
        def set_manual_level(self, lvl): pass
        def set_failsafe_temp(self, t): pass
        def save_user_preset(self, name, points, sensors):
            self.save_calls.append((name, list(points), list(sensors)))
        def delete_user_preset(self, name):
            self.delete_calls.append(name)

    client = StubClient()
    w = MainWindow(client)
    qtbot.addWidget(w)
    client.connected.emit(True)
    names = [b.text() for b in w.curve_editor.user_preset_buttons]
    assert names == ["Meins"]


def test_main_window_save_preset_calls_client(qtbot, monkeypatch):
    from tpfan_gui.main_window import MainWindow
    from PyQt6.QtCore import QObject, pyqtSignal
    from PyQt6 import QtWidgets

    class StubClient(QObject):
        tickReceived = pyqtSignal(object)
        emergency = pyqtSignal(float, str)
        connected = pyqtSignal(bool)
        propertiesChanged = pyqtSignal(dict)

        def __init__(self):
            super().__init__()
            self.save_calls = []
        def get(self, name):
            if name == "UserPresets": return {}
            if name == "Curve": return [(40.0, 0), (80.0, 7)]
            return None
        def set_curve(self, points, sensors): pass
        def set_mode(self, m): pass
        def set_manual_level(self, lvl): pass
        def set_failsafe_temp(self, t): pass
        def save_user_preset(self, name, points, sensors):
            self.save_calls.append((name, list(points), list(sensors)))
        def delete_user_preset(self, name): pass

    monkeypatch.setattr(QtWidgets.QInputDialog, "getText",
                        staticmethod(lambda *a, **k: ("Mein", True)))
    client = StubClient()
    w = MainWindow(client)
    qtbot.addWidget(w)
    client.connected.emit(True)
    w.curve_editor.save_as_btn.click()
    assert len(client.save_calls) == 1
    name, pts, sensors = client.save_calls[0]
    assert name == "Mein"
    assert sensors == ["CPU", "GPU", "NVMe"]
```

- [ ] **Step 3: Run test, verify it fails**

Run: `cd /home/matthias/programmieren/tmp-fan && python -m pytest gui/tests/test_main_window.py -v -k user_preset`
Expected: FAIL.

- [ ] **Step 4: Wire MainWindow to user presets**

In `gui/src/tpfan_gui/main_window.py` die `make_curve_editor`-Zeile in `__init__` anpassen:

```python
        self.curve_editor = make_curve_editor(
            self.curve_model, self._send_curve,
            on_save_preset=self._save_user_preset,
            on_delete_preset=self._delete_user_preset,
        )
```

Neue Methoden ergänzen (nach `_send_curve`):

```python
    def _save_user_preset(self, name: str, points):
        sensors = ["CPU", "GPU", "NVMe"]
        try:
            self.client.save_user_preset(name, list(points), sensors)
            self._sync_user_presets_from_daemon()
        except Exception as e:
            QMessageBox.warning(self, "tpfan", self._friendly_error(e))

    def _delete_user_preset(self, name: str):
        try:
            self.client.delete_user_preset(name)
            self._sync_user_presets_from_daemon()
        except Exception as e:
            QMessageBox.warning(self, "tpfan", self._friendly_error(e))

    def _sync_user_presets_from_daemon(self) -> None:
        try:
            presets = self.client.get("UserPresets")
        except Exception:
            return
        if presets is None:
            return
        normalized = {}
        for name, val in dict(presets).items():
            try:
                points, sensors = val
                normalized[str(name)] = (
                    [(float(t), int(l)) for t, l in points],
                    [str(s) for s in sensors],
                )
            except (TypeError, ValueError):
                continue
        setter = getattr(self.curve_editor, "set_user_presets", None)
        if callable(setter):
            setter(normalized)
```

In `_on_connected` nach dem bestehenden `self._sync_curve_from_daemon()` ergänzen:

```python
            self._sync_user_presets_from_daemon()
```

- [ ] **Step 5: Run tests, verify they pass**

Run: `cd /home/matthias/programmieren/tmp-fan && python -m pytest gui/tests/test_main_window.py -v`
Expected: PASS, kein Regress.

- [ ] **Step 6: Commit**

```bash
git add gui/src/tpfan_gui/main_window.py gui/tests/test_main_window.py
git commit -m "feat(gui): wire MainWindow to save/load/delete user presets"
```

---

### Task 8: Full Test Suite + Manual Smoke

**Files:** keine — Verifikation.

- [ ] **Step 1: Run full daemon tests**

Run: `cd /home/matthias/programmieren/tmp-fan && python -m pytest daemon/tests -v`
Expected: alle PASS.

- [ ] **Step 2: Run full GUI tests**

Run: `cd /home/matthias/programmieren/tmp-fan && python -m pytest gui/tests -v`
Expected: neue Tests PASS; pre-existing qtbot-Errors in `test_curve_editor.py::test_apply_*` bleiben wie vorher (Pre-Condition).

- [ ] **Step 3: Manual smoke test (vom User auszuführen)**

Dem User mitteilen:

> Bitte daemon + GUI neustarten: `sudo systemctl restart tpfan-daemon && pkill -f tpfan-gui ; tpfan-gui &`
>
> Im Kurven-Editor:
> 1. Punkte anpassen → „Speichern als …" → Name z. B. „TestPreset" → Polkit-Auth → Button erscheint in Zeile „Eigene:".
> 2. Anderen Punkten zuweisen → User-Preset-Button klicken → Punkte werden geladen.
> 3. „×" neben „TestPreset" → bestätigen → Button verschwindet.
> 4. Test mit Name „Sehr ruhig" → GUI-Warnung „… vordefiniertes Preset …", kein Daemon-Call.
> 5. `cat /etc/tpfan/config.toml` → `[user_presets."TestPreset"]` ist nach Save da bzw. nach Delete weg.

- [ ] **Step 4: Final no-op commit if needed**

Wenn alles grün ist und keine Änderungen offen sind, keine weitere Aktion. Andernfalls hier dokumentieren.
