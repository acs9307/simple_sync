"""Tests for configuration directory helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from simple_sync import config


class TestConfigPathResolution(unittest.TestCase):
    """Ensure platform-specific config directories resolve correctly."""

    def test_base_dir_posix(self):
        fake_home = Path("/tmp/fakehome")
        with mock.patch("simple_sync.config.Path.home", return_value=fake_home), mock.patch(
            "simple_sync.config.is_windows", return_value=False
        ):
            base = config.get_base_config_dir()
        self.assertEqual(base, fake_home / ".config" / config.CONFIG_DIR_NAME)

    def test_base_dir_windows_uses_appdata(self):
        fake_appdata = Path("C:/Users/test/AppData/Roaming")
        with mock.patch("simple_sync.config.is_windows", return_value=True), mock.patch.dict(
            "simple_sync.config.os.environ", {"APPDATA": str(fake_appdata)}
        ):
            base = config.get_base_config_dir()
        self.assertEqual(base, fake_appdata / config.CONFIG_DIR_NAME)

    def test_base_dir_windows_without_appdata(self):
        fake_home = Path("C:/Users/test")
        with mock.patch("simple_sync.config.is_windows", return_value=True), mock.patch(
            "simple_sync.config.Path.home", return_value=fake_home
        ), mock.patch.dict(
            "simple_sync.config.os.environ", {}, clear=True
        ):
            base = config.get_base_config_dir()
        self.assertEqual(base, fake_home / "AppData" / "Roaming" / config.CONFIG_DIR_NAME)


class TestEnsureConfigStructure(unittest.TestCase):
    """Ensure directory scaffolding is created as expected."""

    def test_ensure_structure_creates_subdirectories(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "config_root"
            resolved = config.ensure_config_structure(base)
            self.assertEqual(resolved, base)
            for sub in config.SUBDIRECTORIES:
                self.assertTrue((base / sub).exists())


if __name__ == "__main__":
    unittest.main()
