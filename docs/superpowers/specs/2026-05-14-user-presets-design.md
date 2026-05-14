# Eigene Lüfterkurven-Presets — Design

## Ziel

Der User kann im Kurven-Editor selbst erstellte Kurven unter eigenem Namen speichern, später wieder laden und bei Bedarf löschen. Built-in-Presets („Sehr ruhig" … „Sehr kühl") bleiben unverändert.

## Datenmodell

Erweiterung von `Config` in `daemon/src/tpfan_daemon/config.py`:

```python
user_presets: dict[str, CurveCfg] = field(default_factory=dict)
```

TOML-Format, parallel zu `[profiles.*]`:

```toml
[user_presets."Mein Preset"]
sensors = ["CPU", "GPU", "NVMe"]
points = [[42.0, 0], [58.0, 2], [72.0, 4], [82.0, 7]]
```

Begründung der Separation von `profiles`: Profile sind Laufzeit-Modi (`mode = "profile:<name>"`); User-Presets sind Editor-Vorlagen, die nach Anwendung in `mode = "curve"` enden. Semantisch verschieden, daher eigener Schlüssel.

## Namens-Validierung (Daemon)

- nicht leer, max. 64 Zeichen
- Zeichen: `[A-Za-z0-9 _-]` (inkl. Leerzeichen, ohne Punkte/Anführungszeichen, damit TOML-Keys sauber bleiben)
- darf nicht mit einem Built-in-Preset-Namen kollidieren (Liste kommt aus dem GUI; Daemon kennt sie nicht, daher GUI-seitige Prüfung *zusätzlich* zur Daemon-Validierung von Format/Länge)

## D-Bus-API

Erweiterung von `daemon/src/tpfan_daemon/ipc/dbus_service.py`:

**Property**
```
UserPresets: Dict[Str, Tuple[List[Tuple[Double, Byte]], List[Str]]]
```
Map `name → (points, sensors)`. Änderungen lösen `PropertiesChanged` aus.

**Methoden**
```
SaveUserPreset(name: Str, points: List[Tuple[Double, Byte]], sensors: List[Str])
DeleteUserPreset(name: Str)
```

Beide gehen über `_cmd("save_user_preset", …)` / `_cmd("delete_user_preset", …)` an den `Daemon`-Dispatcher.

## Polkit

Neue Action `org.tpfan1.manage-presets` in `packaging/org.tpfan1.policy`:
- `allow_active = auth_admin_keep`
- `allow_inactive = auth_admin`
- `allow_any = no`

(gleiche Stufe wie `set-curve`).

Beide Methoden prüfen diese Action via bestehendes `self._check(...)`.

## Daemon-Handler

In `daemon/src/tpfan_daemon/daemon.py`:

- `save_user_preset(name, points, sensors)`:
  - Name-Validierung (Format/Länge)
  - `_validate_points` für die Kurve
  - Sensoren gegen `self.sensors.read_all().keys()` prüfen
  - `replace(self.loop.config, user_presets={**cfg.user_presets, name: CurveCfg(...)})`
  - `self._save()`
- `delete_user_preset(name)`:
  - `KeyError` → `ValueError("unknown preset: …")`
  - sonst Eintrag entfernen, `_save()`

Beide propagieren `UserPresets`-Property via bestehender `PropertiesChanged`-Mechanik (state-getter im `dbus_service.py` ergänzt um `user_presets`).

## GUI

`gui/src/tpfan_gui/views/curve_editor.py`:

- Preset-Zeile zeigt jetzt: Built-ins (unverändert) gefolgt von User-Presets.
- User-Preset-Button trägt zusätzlich ein kleines „×" (eigenes `QPushButton` rechts neben dem Namens-Button) zum Löschen mit `QMessageBox.question`-Bestätigung.
- Neuer Button **„Speichern als …"** neben „Anwenden". Öffnet `QInputDialog.getText`, validiert lokal gegen Built-in-Namen (Kollision → Hinweis), ruft dann `client.save_user_preset(name, points, sensors)`.
- `CurveEditor` erhält Setter `set_user_presets(dict)`, der die User-Preset-Buttons neu aufbaut.

`gui/src/tpfan_gui/main_window.py`:

- `_sync_curve_from_daemon` erweitert: liest auch `UserPresets` und ruft `curve_editor.set_user_presets(...)`.
- `propertiesChanged`-Slot reagiert auf `UserPresets`-Änderungen und ruft erneut den Setter.

`gui/src/tpfan_gui/ipc/dbus_client.py`:

- `save_user_preset(name, points, sensors)` → `self._require_proxy().SaveUserPreset(...)`
- `delete_user_preset(name)` → `self._require_proxy().DeleteUserPreset(...)`

## Fehlerbehandlung

- Daemon-Validierungsfehler → bestehender `_friendly_error`-Pfad in `main_window.py` zeigt `QMessageBox.warning`.
- Polkit-Verweigerung → bestehende Übersetzung „Keine Berechtigung".
- Namens-Kollision mit Built-in: zuerst GUI-Vorabprüfung (sofortiges Feedback ohne Roundtrip), Daemon kennt diese Liste nicht.

## Tests

**daemon/tests/test_config.py**
- Roundtrip: `Config` mit zwei `user_presets` durch `save`/`load`.
- Ungültige Punkte in `user_presets` → `ValueError` beim Laden.

**daemon/tests/test_daemon_glue.py**
- `save_user_preset` Happy-Path → erscheint in `config.user_presets`, Datei geschrieben.
- `save_user_preset` mit ungültigem Namen (leer, zu lang, Sonderzeichen) → `ValueError`, keine Datei-Änderung.
- `save_user_preset` mit ungültigen Punkten → `ValueError`.
- `delete_user_preset` Happy-Path und unknown-Key → `ValueError`.

**gui/tests/test_curve_editor.py**
- „Speichern als …" mit gemocktem Dialog ruft `save_user_preset` mit Editor-Punkten und Sensors.
- „×"-Button auf User-Preset ruft `delete_user_preset` nach Bestätigung.
- `set_user_presets({...})` baut entsprechende Buttons auf.

## Scope-Abgrenzung

- Keine Migration der hardcoded Built-ins in die Config.
- Kein Import/Export von Presets.
- Keine Reihenfolge-Sortierung jenseits von „Built-ins zuerst, User-Presets danach in dict-insertion-order".
