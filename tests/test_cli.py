"""Tests for the argparse CLI skeleton."""

from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from simple_sync import cli, config
from simple_sync.engine import executor


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    """Helper that runs the CLI and captures stdout/stderr."""
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        code = cli.main(argv)
    return code, stdout_buffer.getvalue().strip(), stderr_buffer.getvalue().strip()


@contextmanager
def _silence_parser_output():
    """Suppress argparse's stderr chatter during negative tests."""
    sink = io.StringIO()
    with redirect_stdout(sink), redirect_stderr(sink):
        yield


def _write_local_profile(
    config_dir: Path,
    name: str,
    src: Path,
    dst: Path,
    *,
    conflict_policy: str = "newest",
    conflict_kwargs: dict | None = None,
    ssh_kwargs: dict | None = None,
) -> None:
    """Create a pairwise local profile under the config directory."""
    conflict_kwargs = conflict_kwargs or {}
    ssh_kwargs = ssh_kwargs or {}
    profile_cfg = config.ProfileConfig(
        profile=config.ProfileBlock(name=name, description=f"{name} profile"),
        endpoints={
            "A": config.EndpointBlock(name="A", type="local", path=str(src)),
            "B": config.EndpointBlock(name="B", type="local", path=str(dst)),
        },
        conflict=config.ConflictBlock(
            policy=conflict_policy,
            prefer=conflict_kwargs.get("prefer"),
            manual_behavior=conflict_kwargs.get("manual_behavior"),
        ),
        ignore=config.IgnoreBlock(patterns=[]),
        schedule=config.ScheduleBlock(),
        ssh=config.SshBlock(**ssh_kwargs) if ssh_kwargs else config.SshBlock(),
    )
    base = config.ensure_config_structure(config_dir)
    (base / "profiles" / f"{name}.toml").write_text(config.profile_to_toml(profile_cfg))


class TestCliParser(unittest.TestCase):
    """Parser wiring sanity checks."""

    def test_run_command_requires_profile(self):
        parser = cli.build_parser()
        with self.assertRaises(SystemExit), _silence_parser_output():
            parser.parse_args(["run"])

    def test_conflicts_command_requires_profile(self):
        parser = cli.build_parser()
        with self.assertRaises(SystemExit), _silence_parser_output():
            parser.parse_args(["conflicts"])


class TestCliCommands(unittest.TestCase):
    """Stub command tests ensure outputs make sense."""

    def test_daemon_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("simple_sync.cli.DaemonRunner.run_forever") as mock_run:
                exit_code, stdout, stderr = _run_cli(["--config-dir", tmpdir, "daemon", "start", "--once"])
        self.assertEqual(exit_code, 0)
        mock_run.assert_called_once()

    def test_status_command(self):
        exit_code, stdout, stderr = _run_cli(["status"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout, "")
        self.assertIn("status", stderr.lower())

    def test_quiet_flag_suppresses_info_logs(self):
        exit_code, stdout, stderr = _run_cli(["--quiet", "status"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout, "")
        self.assertEqual("", stderr)


class TestCliProfilesCommand(unittest.TestCase):
    """Tests for the profiles listing command."""

    def test_profiles_command_lists_profiles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            base = config.ensure_config_structure(Path(tmpdir))
            profile_cfg = config.build_profile_template()
            profile_cfg.profile.name = "demo"
            profile_cfg.profile.description = "Demo profile"
            (base / "profiles" / "demo.toml").write_text(config.profile_to_toml(profile_cfg))
            exit_code, stdout, stderr = _run_cli(["--config-dir", tmpdir, "profiles"])
            self.assertEqual(exit_code, 0)
            self.assertIn("demo", stdout)
            self.assertEqual("", stderr.strip())
            exit_code, stdout, stderr = _run_cli(["--config-dir", tmpdir, "conflicts", "demo"])
            self.assertEqual(exit_code, 0)
            self.assertIn("No conflicts", stdout)


class TestCliInitCommand(unittest.TestCase):
    """Integration-level tests for the init command."""

    def test_init_command_creates_profile_file(self):
        responses = iter(
            [
                "Demo profile description",  # description
                "",  # endpoint1 name -> default
                "",  # endpoint1 type -> default local
                "/tmp/source",  # endpoint1 path
                "",  # endpoint2 name -> default remote
                "",  # endpoint2 type -> default ssh
                "example.com",  # endpoint2 host
                "/tmp/remote",  # endpoint2 path
                "y",  # default ignore patterns
            ]
        )

        def fake_input(prompt: str) -> str:
            return next(responses)

        with tempfile.TemporaryDirectory() as tmpdir, mock.patch("builtins.input", side_effect=fake_input):
            exit_code, stdout, stderr = _run_cli(["--config-dir", tmpdir, "init", "demo"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout, "")
            profile_path = Path(tmpdir) / "profiles" / "demo.toml"
            self.assertTrue(profile_path.exists())
            content = profile_path.read_text()
            self.assertIn("demo", content)
            self.assertIn("example.com", content)
            self.assertIn("Profile created", stderr)


class TestCliRunCommand(unittest.TestCase):
    """Integration tests for the run command using real directories."""

    def test_run_copies_files_and_writes_state(self):
        with tempfile.TemporaryDirectory() as config_tmp, tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            config_dir = Path(config_tmp)
            src_root = Path(src_tmp)
            dst_root = Path(dst_tmp)
            (src_root / "hello.txt").write_text("hello")
            _write_local_profile(config_dir, "demo", src_root, dst_root)
            exit_code, stdout, stderr = _run_cli(["--config-dir", config_tmp, "run", "demo"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout, "")
            self.assertTrue((dst_root / "hello.txt").exists())
            state_path = config_dir / "state" / "demo.json"
            self.assertTrue(state_path.exists())
            data = json.loads(state_path.read_text())
            self.assertIn("A", data["endpoints"])
            self.assertIn("hello.txt", data["endpoints"]["A"])
            self.assertIn("Plan summary", stderr)

    def test_dry_run_does_not_modify_destination_or_state(self):
        with tempfile.TemporaryDirectory() as config_tmp, tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            config_dir = Path(config_tmp)
            src_root = Path(src_tmp)
            dst_root = Path(dst_tmp)
            (src_root / "hello.txt").write_text("hello")
            _write_local_profile(config_dir, "demo", src_root, dst_root)
            exit_code, stdout, stderr = _run_cli(
                ["--config-dir", config_tmp, "run", "demo", "--dry-run"]
            )
            self.assertEqual(exit_code, 0)
            self.assertFalse((dst_root / "hello.txt").exists())
            self.assertFalse((config_dir / "state" / "demo.json").exists())
            self.assertIn("Dry-run complete", stderr)

    def test_run_manual_policy_records_conflict(self):
        with tempfile.TemporaryDirectory() as config_tmp, tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            config_dir = Path(config_tmp)
            src_root = Path(src_tmp)
            dst_root = Path(dst_tmp)
            (src_root / "hello.txt").write_text("hello")
            (dst_root / "hello.txt").write_text("world!!")
            _write_local_profile(
                config_dir,
                "demo",
                src_root,
                dst_root,
                conflict_policy="manual",
                conflict_kwargs={"manual_behavior": "copy_both"},
            )
            exit_code, stdout, stderr = _run_cli(["--config-dir", config_tmp, "run", "demo"])
            self.assertEqual(exit_code, 0)
            state_path = config_dir / "state" / "demo.json"
            data = json.loads(state_path.read_text())
            self.assertEqual(len(data.get("conflicts", [])), 1)
            exit_code, stdout, stderr = _run_cli(["--config-dir", config_tmp, "conflicts", "demo"])
            self.assertEqual(exit_code, 0)
            self.assertIn("manual_copy_both", stdout)

    def test_run_executes_preconnect_command(self):
        with tempfile.TemporaryDirectory() as config_tmp, tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            config_dir = Path(config_tmp)
            src_root = Path(src_tmp)
            dst_root = Path(dst_tmp)
            (src_root / "hello.txt").write_text("hello")
            _write_local_profile(
                config_dir,
                "demo",
                src_root,
                dst_root,
                ssh_kwargs={"pre_connect_command": "echo setup"},
            )
            with mock.patch("subprocess.run", return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")) as mock_run:
                exit_code, stdout, stderr = _run_cli(["--config-dir", config_tmp, "run", "demo"])
            self.assertEqual(exit_code, 0)
            self.assertTrue(mock_run.called)

    def test_run_handles_auth_prompt_error(self):
        with tempfile.TemporaryDirectory() as config_tmp, tempfile.TemporaryDirectory() as src_tmp, tempfile.TemporaryDirectory() as dst_tmp:
            config_dir = Path(config_tmp)
            src_root = Path(src_tmp)
            dst_root = Path(dst_tmp)
            (src_root / "hello.txt").write_text("hello")
            _write_local_profile(config_dir, "demo", src_root, dst_root)
            with mock.patch(
                "simple_sync.cli.executor.apply_operations",
                side_effect=executor.ExecutionError("SSH authentication prompt detected; refusing to continue."),
            ):
                exit_code, stdout, stderr = _run_cli(["--config-dir", config_tmp, "run", "demo"])
            self.assertNotEqual(exit_code, 0)
            self.assertIn("authentication prompt", stderr.lower())


if __name__ == "__main__":
    unittest.main()
