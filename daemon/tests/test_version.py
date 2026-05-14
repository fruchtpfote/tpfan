from __future__ import annotations
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_pyproject_version(path: Path) -> str:
    text = path.read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, flags=re.M)
    assert m, f"no version in {path}"
    return m.group(1)


def test_daemon_init_matches_daemon_pyproject():
    from tpfan_daemon import __version__ as daemon_v
    assert daemon_v == _read_pyproject_version(REPO_ROOT / "daemon" / "pyproject.toml")


def test_gui_pyproject_matches_daemon_pyproject():
    assert _read_pyproject_version(REPO_ROOT / "daemon" / "pyproject.toml") \
        == _read_pyproject_version(REPO_ROOT / "gui" / "pyproject.toml")


def test_gui_init_matches_pyproject():
    """Liest gui/__init__.py textuell — gui ist hier nicht importierbar
    ohne PyQt6, also ohne Import auskommen."""
    text = (REPO_ROOT / "gui" / "src" / "tpfan_gui" / "__init__.py").read_text()
    m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    assert m
    assert m.group(1) == _read_pyproject_version(REPO_ROOT / "gui" / "pyproject.toml")
