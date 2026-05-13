from __future__ import annotations
from pathlib import Path
import pytest
from tpfan_daemon.config import Config, CurveCfg, load, save, DEFAULT


def test_load_default_when_missing(tmp_path: Path):
    cfg = load(tmp_path / "nope.toml")
    assert cfg == DEFAULT


def test_round_trip(tmp_path: Path):
    p = tmp_path / "c.toml"
    save(p, DEFAULT)
    cfg2 = load(p)
    assert cfg2 == DEFAULT


def test_validates_curve_monotonic(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text(
        '''
        mode = "curve"
        manual_level = "3"
        failsafe_temp = 95.0
        [curve]
        sensors = ["CPU"]
        points = [[70, 4], [55, 2]]
        '''
    )
    with pytest.raises(ValueError, match="monotonic"):
        load(p)


def test_validates_level_range(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text(
        '''
        mode = "curve"
        manual_level = "3"
        failsafe_temp = 95.0
        [curve]
        sensors = ["CPU"]
        points = [[40, 0], [80, 9]]
        '''
    )
    with pytest.raises(ValueError, match="level"):
        load(p)


def test_atomic_write_does_not_leave_partial(tmp_path: Path, monkeypatch):
    p = tmp_path / "c.toml"
    save(p, DEFAULT)
    original = p.read_text()

    def boom(*a, **kw):
        raise RuntimeError("disk full")

    monkeypatch.setattr("os.replace", boom)
    with pytest.raises(RuntimeError):
        save(p, CurveCfg.from_default()._wrap_in_config(failsafe_temp=70.0))
    assert p.read_text() == original
