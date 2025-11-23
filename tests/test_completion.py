"""Tests for tab completion functionality."""

from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path

from simple_sync import completion, config


class TestProfileCompleter(unittest.TestCase):
    """Test profile name completion."""

    def test_completes_matching_profiles(self):
        """Test that profile completer returns matching profile names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profiles_dir = Path(tmpdir) / "profiles"
            profiles_dir.mkdir(parents=True)

            # Create test profiles
            (profiles_dir / "dev.toml").touch()
            (profiles_dir / "development.toml").touch()
            (profiles_dir / "production.toml").touch()

            ns = argparse.Namespace(config_dir=tmpdir)

            # Test prefix matching
            results = list(completion.profile_completer("dev", ns))
            self.assertIn("dev", results)
            self.assertIn("development", results)
            self.assertNotIn("production", results)

    def test_completes_all_profiles_with_empty_prefix(self):
        """Test that empty prefix returns all profiles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profiles_dir = Path(tmpdir) / "profiles"
            profiles_dir.mkdir(parents=True)

            (profiles_dir / "profile1.toml").touch()
            (profiles_dir / "profile2.toml").touch()

            ns = argparse.Namespace(config_dir=tmpdir)

            results = list(completion.profile_completer("", ns))
            self.assertEqual(len(results), 2)
            self.assertIn("profile1", results)
            self.assertIn("profile2", results)

    def test_returns_empty_if_no_profiles_dir(self):
        """Test that completer returns empty list if profiles directory doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ns = argparse.Namespace(config_dir=tmpdir)
            results = list(completion.profile_completer("", ns))
            self.assertEqual(results, [])

    def test_handles_no_config_dir_argument(self):
        """Test that completer handles missing config_dir gracefully."""
        ns = argparse.Namespace()
        # Should use default config dir
        results = list(completion.profile_completer("nonexistent", ns))
        # Should return empty or profiles from default location
        self.assertIsInstance(results, list)

    def test_profiles_sorted_alphabetically(self):
        """Test that profile names are returned in sorted order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profiles_dir = Path(tmpdir) / "profiles"
            profiles_dir.mkdir(parents=True)

            (profiles_dir / "zebra.toml").touch()
            (profiles_dir / "alpha.toml").touch()
            (profiles_dir / "beta.toml").touch()

            ns = argparse.Namespace(config_dir=tmpdir)

            results = list(completion.profile_completer("", ns))
            self.assertEqual(results, ["alpha", "beta", "zebra"])


class TestEndpointCompleter(unittest.TestCase):
    """Test endpoint name completion."""

    def test_completes_endpoint_names_from_profile(self):
        """Test that endpoint completer returns endpoint names from profile."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profiles_dir = Path(tmpdir) / "profiles"
            profiles_dir.mkdir(parents=True)

            # Create a profile with endpoints
            profile_content = """
[profile]
name = "test"
description = "Test"

[conflict]
policy = "newest"

[ignore]
patterns = []

[endpoints.local]
type = "local"
path = "/tmp/local"

[endpoints.remote]
type = "ssh"
host = "example.com"
path = "/tmp/remote"

[endpoints.backup]
type = "local"
path = "/tmp/backup"
"""
            (profiles_dir / "test.toml").write_text(profile_content)

            ns = argparse.Namespace(config_dir=tmpdir, profile="test")

            results = list(completion.endpoint_completer("", ns))
            self.assertEqual(len(results), 3)
            self.assertIn("local", results)
            self.assertIn("remote", results)
            self.assertIn("backup", results)

    def test_filters_by_prefix(self):
        """Test that endpoint completer filters by prefix."""
        with tempfile.TemporaryDirectory() as tmpdir:
            profiles_dir = Path(tmpdir) / "profiles"
            profiles_dir.mkdir(parents=True)

            profile_content = """
[profile]
name = "test"
description = "Test"

[conflict]
policy = "newest"

[ignore]
patterns = []

[endpoints.remote1]
type = "local"
path = "/tmp/r1"

[endpoints.remote2]
type = "local"
path = "/tmp/r2"

[endpoints.local]
type = "local"
path = "/tmp/local"
"""
            (profiles_dir / "test.toml").write_text(profile_content)

            ns = argparse.Namespace(config_dir=tmpdir, profile="test")

            results = list(completion.endpoint_completer("remote", ns))
            self.assertIn("remote1", results)
            self.assertIn("remote2", results)
            self.assertNotIn("local", results)

    def test_returns_empty_if_profile_not_specified(self):
        """Test that completer returns empty if no profile specified."""
        ns = argparse.Namespace()
        results = list(completion.endpoint_completer("", ns))
        self.assertEqual(results, [])

    def test_returns_empty_if_profile_doesnt_exist(self):
        """Test that completer returns empty if profile doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ns = argparse.Namespace(config_dir=tmpdir, profile="nonexistent")
            results = list(completion.endpoint_completer("", ns))
            self.assertEqual(results, [])


class TestPolicyCompleter(unittest.TestCase):
    """Test policy name completion."""

    def test_completes_all_policies(self):
        """Test that all policy names are returned."""
        ns = argparse.Namespace()
        results = list(completion.policy_completer("", ns))
        self.assertEqual(set(results), {"newest", "prefer", "manual"})

    def test_filters_by_prefix(self):
        """Test that policies are filtered by prefix."""
        ns = argparse.Namespace()
        results = list(completion.policy_completer("n", ns))
        self.assertEqual(results, ["newest"])

    def test_no_matches_returns_empty(self):
        """Test that non-matching prefix returns empty."""
        ns = argparse.Namespace()
        results = list(completion.policy_completer("xyz", ns))
        self.assertEqual(results, [])


class TestEndpointTypeCompleter(unittest.TestCase):
    """Test endpoint type completion."""

    def test_completes_all_types(self):
        """Test that all endpoint types are returned."""
        ns = argparse.Namespace()
        results = list(completion.endpoint_type_completer("", ns))
        self.assertEqual(set(results), {"local", "ssh"})

    def test_filters_by_prefix(self):
        """Test that types are filtered by prefix."""
        ns = argparse.Namespace()
        results = list(completion.endpoint_type_completer("s", ns))
        self.assertEqual(results, ["ssh"])


if __name__ == "__main__":
    unittest.main()
