"""Tests for the daemon runner scheduling logic."""

from __future__ import annotations

import signal
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from simple_sync import config
from simple_sync.daemon.runner import DaemonRunner


def _write_profile(base: Path, name: str, enabled: bool) -> None:
    profile = config.ProfileConfig(
        profile=config.ProfileBlock(name=name, description="test"),
        endpoints={
            "A": config.EndpointBlock(name="A", type="local", path=str(base / f"{name}_a")),
            "B": config.EndpointBlock(name="B", type="local", path=str(base / f"{name}_b")),
        },
        conflict=config.ConflictBlock(policy="newest"),
        ignore=config.IgnoreBlock(),
        schedule=config.ScheduleBlock(enabled=enabled, interval_seconds=1, run_on_start=True),
        ssh=config.SshBlock(),
    )
    config.ensure_config_structure(base)
    path = base / "profiles" / f"{name}.toml"
    path.write_text(config.profile_to_toml(profile))


class TestDaemonRunner(unittest.TestCase):
    def test_loads_scheduled_profiles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            _write_profile(base, "enabled", True)
            _write_profile(base, "disabled", False)
            runner = DaemonRunner(config_dir=tmpdir)
            profiles = runner._load_scheduled_profiles()
        self.assertIn("enabled", profiles)
        self.assertNotIn("disabled", profiles)

    def test_run_forever_once_triggers_sync(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            _write_profile(base, "enabled", True)
            runner = DaemonRunner(config_dir=tmpdir)
            with mock.patch("simple_sync.cli.SyncRunner") as mock_runner, mock.patch(
                "simple_sync.daemon.runner.time"
            ) as mock_time:
                mock_time.time.side_effect = [0, 0, 1]
                mock_runner.return_value.run.return_value = None
                runner.run_forever(run_once=True)
        mock_runner.return_value.run.assert_called_once_with(profile_name="enabled", dry_run=False)

    def test_handle_signal_stop_and_reload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runner = DaemonRunner(config_dir=tmpdir)
            runner._handle_signal(signal.SIGHUP, None)
            self.assertTrue(runner._reload)
            runner._handle_signal(signal.SIGTERM, None)
            self.assertTrue(runner._stop)


if __name__ == "__main__":
    unittest.main()
