import os
import sys
import tempfile
from pathlib import Path

import pytest

# settings.py reads CONFIG_DIR at import time: point it to a throwaway folder first.
os.environ.setdefault("CONFIG_DIR", tempfile.mkdtemp(prefix="quizzarr-test-"))
os.environ.setdefault("TZ", "Europe/Brussels")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import settings  # noqa: E402


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(settings, "CONNECTIONS_FILE", tmp_path / "connections.json")
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    return tmp_path
