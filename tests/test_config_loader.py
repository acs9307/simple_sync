"""Tests for config loading and validation."""

from __future__ import annotations

import tempfile
import textwrap
import unittest
from pathlib import Path

from simple_sync import config


def _write_profile(tmpdir: Path, name: str, contents: str) -> Path:
    base = config.ensure_config_structure(tmpdir)
    path = base / "profiles" / f"{name}.toml"
    path.write_text(textwrap.dedent(contents).strip() + "\n")
    return path


class TestConfigLoader(unittest.TestCase):
    def test_load_profile_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_profile(
                Path(tmp),
                "demo",
                """
                [profile]
                name = "demo"
                description = "Demo profile"

                [conflict]
                policy = "newest"

                [ignore]
                patterns = [".git"]

                [schedule]
                enabled = true
                interval_seconds = 120
                run_on_start = false

                [ssh]
                use_agent = true

                [endpoints.local]
                type = "local"
                path = "/tmp/a"

                [endpoints.remote]
                type = "ssh"
                host = "example.com"
                path = "/tmp/b"
                """,
            )
            profile = config.load_profile("demo", Path(tmp))
        self.assertEqual(profile.profile.name, "demo")
        self.assertEqual(len(profile.endpoints), 2)
        self.assertTrue(profile.ignore.patterns)
        self.assertTrue(profile.schedule.enabled)

    def test_missing_profile_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(config.ConfigError) as err:
                config.load_profile("missing", Path(tmp))
        self.assertIn("not found", str(err.exception))

    def test_missing_endpoint_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_profile(
                Path(tmp),
                "demo",
                """
                [profile]
                name = "demo"
                description = "Demo profile"

                [conflict]
                policy = "newest"

                [endpoints.local]
                type = "local"
                """,
            )
            with self.assertRaises(config.ConfigError) as err:
                config.load_profile("demo", Path(tmp))
        self.assertIn("path", str(err.exception))

    def test_prefer_policy_requires_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_profile(
                Path(tmp),
                "demo",
                """
                [profile]
                name = "demo"
                description = "Demo profile"

                [conflict]
                policy = "prefer"

                [endpoints.local]
                type = "local"
                path = "/tmp/a"

                [endpoints.remote]
                type = "local"
                path = "/tmp/b"
                """,
            )
            with self.assertRaises(config.ConfigError) as err:
                config.load_profile("demo", Path(tmp))
        self.assertIn("prefer", str(err.exception))

    def test_prefer_policy_requires_known_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_profile(
                Path(tmp),
                "demo",
                """
                [profile]
                name = "demo"
                description = "Demo profile"

                [conflict]
                policy = "prefer"
                prefer = "missing"

                [endpoints.local]
                type = "local"
                path = "/tmp/a"

                [endpoints.remote]
                type = "local"
                path = "/tmp/b"
                """,
            )
            with self.assertRaises(config.ConfigError) as err:
                config.load_profile("demo", Path(tmp))
        self.assertIn("not defined", str(err.exception))


if __name__ == "__main__":
    unittest.main()
