"""Tests for SSH agent/pre-connect hook handling."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from simple_sync import cli, config


def _write_profile(config_dir: Path, src: Path, dst: Path, *, include_preconnect: bool) -> None:
    profile_cfg = config.ProfileConfig(
        profile=config.ProfileBlock(name="demo", description="Demo profile"),
        endpoints={
            "A": config.EndpointBlock(name="A", type="local", path=str(src)),
            "B": config.EndpointBlock(name="B", type="local", path=str(dst)),
        },
        conflict=config.ConflictBlock(policy="newest"),
        ignore=config.IgnoreBlock(patterns=[]),
        schedule=config.ScheduleBlock(),
        ssh=config.SshBlock(
            pre_connect_command="echo setup" if include_preconnect else None,
            ssh_command="ssh",
            use_agent=True,
            env={"SSH_AUTH_SOCK": "/tmp/fake.sock"} if include_preconnect else {},
        ),
    )
    base = config.ensure_config_structure(config_dir)
    (base / "profiles" / "demo.toml").write_text(config.profile_to_toml(profile_cfg))


class TestPreconnectHook(unittest.TestCase):
    """Ensure SSH pre-connect hook is honored and only runs once."""

    def test_preconnect_runs_once_and_merges_env(self):
        with tempfile.TemporaryDirectory() as cfg_tmp, tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            config_dir = Path(cfg_tmp)
            src = Path(src_tmp)
            dst = Path(dst_tmp)
            (src / "hello.txt").write_text("hello")
            _write_profile(config_dir, src, dst, include_preconnect=True)

            runner = cli.SyncRunner(config_dir=str(config_dir))
            with mock.patch.dict(os.environ, {"ORIGINAL": "keep"}), mock.patch(
                "subprocess.run",
                return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            ) as mock_run:
                runner.run(profile_name="demo", dry_run=False)
                runner.run(profile_name="demo", dry_run=False)

            # Called only once despite two runs on the same SyncRunner
            self.assertEqual(mock_run.call_count, 1)
            env = mock_run.call_args.kwargs["env"]
            self.assertEqual(env["SSH_AUTH_SOCK"], "/tmp/fake.sock")
            self.assertEqual(env["ORIGINAL"], "keep")

    def test_failing_preconnect_bubbles_error(self):
        with tempfile.TemporaryDirectory() as cfg_tmp, tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            config_dir = Path(cfg_tmp)
            src = Path(src_tmp)
            dst = Path(dst_tmp)
            (src / "hello.txt").write_text("hello")
            _write_profile(config_dir, src, dst, include_preconnect=True)

            runner = cli.SyncRunner(config_dir=str(config_dir))
            with mock.patch(
                "subprocess.run",
                return_value=subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="agent missing"),
            ):
                with self.assertRaises(RuntimeError):
                    runner.run(profile_name="demo", dry_run=False)


if __name__ == "__main__":
    unittest.main()
