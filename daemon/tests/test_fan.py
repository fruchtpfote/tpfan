from __future__ import annotations
from pathlib import Path
import pytest
from tpfan_daemon.hw.fan import Fan, FanState


FAKE_PROC = """status:\t\tenabled
speed:\t\t2754
level:\t\tauto
commands:\tlevel <level> (<level> is 0-7, auto, disengaged, full-speed)
"""


def _write_fan(tmp: Path, content: str) -> Path:
    p = tmp / "fan"
    p.write_text(content)
    return p


def test_read_state(tmp_path: Path):
    p = _write_fan(tmp_path, FAKE_PROC)
    fan = Fan(path=p)
    st = fan.read()
    assert st == FanState(speed_rpm=2754, level="auto", enabled=True)


def test_set_level_writes_command(tmp_path: Path):
    p = _write_fan(tmp_path, FAKE_PROC)
    written: list[str] = []
    fan = Fan(path=p, _writer=lambda s: written.append(s))
    fan.set_level("3")
    assert written == ["level 3"]


def test_set_level_rejects_invalid(tmp_path: Path):
    p = _write_fan(tmp_path, FAKE_PROC)
    fan = Fan(path=p, _writer=lambda s: None)
    with pytest.raises(ValueError):
        fan.set_level("99")
    with pytest.raises(ValueError):
        fan.set_level("full-speed")


def test_set_level_retries_on_oserror(tmp_path: Path):
    p = _write_fan(tmp_path, FAKE_PROC)
    calls = {"n": 0}

    def flaky(s: str) -> None:
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("EBUSY")

    fan = Fan(path=p, _writer=flaky, _sleep=lambda _: None)
    fan.set_level("2")
    assert calls["n"] == 3


def test_writable_uses_access_not_append(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Regression: procfs rejects open(..., "a") with EINVAL even when writable.
    # writable() must use os.access(W_OK) instead.
    p = _write_fan(tmp_path, FAKE_PROC)

    import builtins
    real_open = builtins.open

    def no_append(path, mode="r", *a, **kw):
        if "a" in mode:
            raise OSError(22, "Invalid argument")
        return real_open(path, mode, *a, **kw)

    monkeypatch.setattr(builtins, "open", no_append)
    fan = Fan(path=p)
    assert fan.writable() is True


def test_writable_false_when_readonly(tmp_path: Path):
    p = _write_fan(tmp_path, FAKE_PROC)
    p.chmod(0o444)
    fan = Fan(path=p)
    assert fan.writable() is False


def test_set_level_gives_up_after_three(tmp_path: Path):
    p = _write_fan(tmp_path, FAKE_PROC)

    def always_fail(s: str) -> None:
        raise OSError("EBUSY")

    fan = Fan(path=p, _writer=always_fail, _sleep=lambda _: None)
    with pytest.raises(OSError):
        fan.set_level("2")
