"""Integration tests for building and exercising standalone binaries."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from simple_sync import config

SUPPORTED_PLATFORMS = ("darwin", "linux")


def _is_supported_platform() -> bool:
    return any(sys.platform.startswith(prefix) for prefix in SUPPORTED_PLATFORMS)


def _require_pyinstaller() -> None:
    try:
        import PyInstaller  # type: ignore  # noqa: F401
    except Exception as exc:  # pragma: no cover - exercised via skip
        raise unittest.SkipTest(
            "PyInstaller is required for binary tests. Install with 'pip install simple-sync[binary]'."
        ) from exc


def _build_binary(build_root: Path) -> Path:
    dist_dir = build_root / "dist"
    work_dir = build_root / "work"
    source = Path(__file__).resolve().parents[1] / "scripts" / "pyinstaller_entry.py"
    env = os.environ.copy()
    env.update(
        {
            "PYINSTALLER_CONFIG_DIR": str(build_root / "config"),
            "PYINSTALLER_CACHE_DIR": str(build_root / "cache"),
        }
    )
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--log-level=WARN",
        f"--distpath={dist_dir}",
        f"--workpath={work_dir}",
        f"--specpath={work_dir}",
        f"--paths={Path(__file__).resolve().parents[1]}",
        "--name",
        "simple-sync",
        str(source),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=build_root,
        env=env,
        timeout=300,
    )
    if result.returncode != 0:
        raise AssertionError(f"PyInstaller build failed:\nstdout: {result.stdout}\nstderr: {result.stderr}")
    app_dir = dist_dir / "simple-sync"
    binary_name = "simple-sync.exe" if sys.platform.startswith("win") else "simple-sync"
    binary = app_dir / binary_name
    if not binary.exists():
        raise AssertionError("Standalone binary was not produced.")
    return binary


def _write_profile(config_dir: Path, src: Path, dst: Path, *, scheduled: bool) -> None:
    profile_cfg = config.ProfileConfig(
        profile=config.ProfileBlock(name="demo", description="Demo profile"),
        endpoints={
            "A": config.EndpointBlock(name="A", type="local", path=str(src)),
            "B": config.EndpointBlock(name="B", type="local", path=str(dst)),
        },
        conflict=config.ConflictBlock(policy="newest"),
        ignore=config.IgnoreBlock(patterns=[]),
        schedule=config.ScheduleBlock(enabled=scheduled, interval_seconds=1, run_on_start=True),
        ssh=config.SshBlock(),
    )
    base = config.ensure_config_structure(config_dir)
    (base / "profiles" / "demo.toml").write_text(config.profile_to_toml(profile_cfg))


def _binary_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}}
    env["PYTHONPATH"] = ""
    env["PYTHONHOME"] = ""
    return env


@unittest.skipUnless(_is_supported_platform(), "Standalone binary tests target macOS and Linux only.")
class TestStandaloneBinary(unittest.TestCase):
    """Build a PyInstaller binary and run a couple of commands against it."""

    @classmethod
    def setUpClass(cls):
        _require_pyinstaller()
        cls.build_root = Path(tempfile.mkdtemp(prefix="ss-bin-build-"))
        cls.binary_path = _build_binary(cls.build_root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.build_root, ignore_errors=True)

    def test_binary_is_native_executable(self):
        header = self.binary_path.read_bytes()[:4]
        signatures = (b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe")
        self.assertTrue(any(header.startswith(sig) for sig in signatures), f"Unexpected header: {header!r}")

    def test_run_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "config"
            src = Path(tmpdir) / "src"
            dst = Path(tmpdir) / "dst"
            src.mkdir()
            dst.mkdir()
            (src / "hello.txt").write_text("hello")
            _write_profile(config_dir, src, dst, scheduled=False)

            result = subprocess.run(
                [str(self.binary_path), "--config-dir", str(config_dir), "run", "demo"],
                capture_output=True,
                text=True,
                env=_binary_env(),
                timeout=120,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertEqual((dst / "hello.txt").read_text(), "hello")
            self.assertTrue((config_dir / "state" / "demo.json").exists())

    def test_daemon_command_runs_once(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = Path(tmpdir) / "config"
            src = Path(tmpdir) / "src"
            dst = Path(tmpdir) / "dst"
            src.mkdir()
            dst.mkdir()
            (src / "payload.txt").write_text("payload")
            _write_profile(config_dir, src, dst, scheduled=True)

            result = subprocess.run(
                [str(self.binary_path), "--config-dir", str(config_dir), "daemon", "start", "--once"],
                capture_output=True,
                text=True,
                env=_binary_env(),
                timeout=120,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertEqual((dst / "payload.txt").read_text(), "payload")
            self.assertTrue((config_dir / "logs" / "demo.log").exists())
