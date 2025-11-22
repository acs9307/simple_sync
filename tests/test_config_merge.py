"""Tests for merge-related configuration."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from simple_sync import config


class TestMergeConfiguration(unittest.TestCase):
    """Test merge configuration fields in ConflictBlock."""

    def test_default_merge_settings(self):
        """Test that merge settings have correct defaults."""
        block = config.ConflictBlock(policy="newest")
        self.assertTrue(block.merge_text_files)
        self.assertEqual(block.merge_fallback, "newest")

    def test_merge_text_files_can_be_disabled(self):
        """Test that merge_text_files can be set to False."""
        block = config.ConflictBlock(
            policy="newest",
            merge_text_files=False
        )
        self.assertFalse(block.merge_text_files)

    def test_merge_fallback_accepts_valid_values(self):
        """Test that merge_fallback accepts valid policy values."""
        for fallback in ["newest", "manual", "prefer"]:
            block = config.ConflictBlock(
                policy="newest",
                merge_fallback=fallback
            )
            self.assertEqual(block.merge_fallback, fallback)

    def test_load_profile_with_merge_settings(self):
        """Test loading a profile with merge settings."""
        toml_content = """
[profile]
name = "test"
description = "Test profile"

[conflict]
policy = "newest"
merge_text_files = true
merge_fallback = "newest"

[ignore]
patterns = []

[endpoints.local]
type = "local"
path = "/tmp/test"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as tmp:
            tmp.write(toml_content)
            tmp_path = Path(tmp.name)

        try:
            profile = config.load_profile_from_path(tmp_path)
            self.assertTrue(profile.conflict.merge_text_files)
            self.assertEqual(profile.conflict.merge_fallback, "newest")
        finally:
            tmp_path.unlink()

    def test_load_profile_with_merge_disabled(self):
        """Test loading a profile with merge disabled."""
        toml_content = """
[profile]
name = "test"
description = "Test profile"

[conflict]
policy = "newest"
merge_text_files = false
merge_fallback = "manual"

[ignore]
patterns = []

[endpoints.local]
type = "local"
path = "/tmp/test"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as tmp:
            tmp.write(toml_content)
            tmp_path = Path(tmp.name)

        try:
            profile = config.load_profile_from_path(tmp_path)
            self.assertFalse(profile.conflict.merge_text_files)
            self.assertEqual(profile.conflict.merge_fallback, "manual")
        finally:
            tmp_path.unlink()

    def test_load_profile_without_merge_settings_uses_defaults(self):
        """Test that profiles without merge settings use defaults."""
        toml_content = """
[profile]
name = "test"
description = "Test profile"

[conflict]
policy = "newest"

[ignore]
patterns = []

[endpoints.local]
type = "local"
path = "/tmp/test"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as tmp:
            tmp.write(toml_content)
            tmp_path = Path(tmp.name)

        try:
            profile = config.load_profile_from_path(tmp_path)
            # Should use defaults
            self.assertTrue(profile.conflict.merge_text_files)
            self.assertEqual(profile.conflict.merge_fallback, "newest")
        finally:
            tmp_path.unlink()

    def test_invalid_merge_fallback_raises_error(self):
        """Test that invalid merge_fallback values raise ConfigError."""
        toml_content = """
[profile]
name = "test"
description = "Test profile"

[conflict]
policy = "newest"
merge_fallback = "invalid"

[ignore]
patterns = []

[endpoints.local]
type = "local"
path = "/tmp/test"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as tmp:
            tmp.write(toml_content)
            tmp_path = Path(tmp.name)

        try:
            with self.assertRaises(config.ConfigError) as ctx:
                config.load_profile_from_path(tmp_path)
            self.assertIn("merge_fallback", str(ctx.exception))
            self.assertIn("invalid", str(ctx.exception))
        finally:
            tmp_path.unlink()

    def test_profile_to_toml_includes_merge_settings(self):
        """Test that serializing a profile includes merge settings."""
        profile_cfg = config.ProfileConfig(
            profile=config.ProfileBlock(name="test", description="Test"),
            endpoints={"local": config.EndpointBlock(name="local", type="local", path="/tmp/test")},
            conflict=config.ConflictBlock(
                policy="newest",
                merge_text_files=True,
                merge_fallback="manual"
            ),
            ignore=config.IgnoreBlock(patterns=[]),
        )

        toml_text = config.profile_to_toml(profile_cfg)

        self.assertIn("merge_text_files = true", toml_text)
        self.assertIn('merge_fallback = "manual"', toml_text)

    def test_profile_to_toml_with_merge_disabled(self):
        """Test serializing a profile with merge disabled."""
        profile_cfg = config.ProfileConfig(
            profile=config.ProfileBlock(name="test", description="Test"),
            endpoints={"local": config.EndpointBlock(name="local", type="local", path="/tmp/test")},
            conflict=config.ConflictBlock(
                policy="newest",
                merge_text_files=False,
                merge_fallback="newest"
            ),
            ignore=config.IgnoreBlock(patterns=[]),
        )

        toml_text = config.profile_to_toml(profile_cfg)

        self.assertIn("merge_text_files = false", toml_text)
        self.assertIn('merge_fallback = "newest"', toml_text)

    def test_merge_with_prefer_policy(self):
        """Test merge configuration with prefer policy."""
        toml_content = """
[profile]
name = "test"
description = "Test profile"

[conflict]
policy = "prefer"
prefer = "local"
merge_text_files = true
merge_fallback = "prefer"

[ignore]
patterns = []

[endpoints.local]
type = "local"
path = "/tmp/test"

[endpoints.remote]
type = "local"
path = "/tmp/remote"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as tmp:
            tmp.write(toml_content)
            tmp_path = Path(tmp.name)

        try:
            profile = config.load_profile_from_path(tmp_path)
            self.assertEqual(profile.conflict.policy, "prefer")
            self.assertEqual(profile.conflict.prefer, "local")
            self.assertTrue(profile.conflict.merge_text_files)
            self.assertEqual(profile.conflict.merge_fallback, "prefer")
        finally:
            tmp_path.unlink()

    def test_merge_with_manual_policy(self):
        """Test merge configuration with manual policy."""
        toml_content = """
[profile]
name = "test"
description = "Test profile"

[conflict]
policy = "manual"
manual_behavior = "copy_both"
merge_text_files = true
merge_fallback = "manual"

[ignore]
patterns = []

[endpoints.local]
type = "local"
path = "/tmp/test"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as tmp:
            tmp.write(toml_content)
            tmp_path = Path(tmp.name)

        try:
            profile = config.load_profile_from_path(tmp_path)
            self.assertEqual(profile.conflict.policy, "manual")
            self.assertEqual(profile.conflict.manual_behavior, "copy_both")
            self.assertTrue(profile.conflict.merge_text_files)
            self.assertEqual(profile.conflict.merge_fallback, "manual")
        finally:
            tmp_path.unlink()

    def test_roundtrip_profile_with_merge_settings(self):
        """Test that profile can be saved and loaded with merge settings."""
        original = config.ProfileConfig(
            profile=config.ProfileBlock(name="test", description="Test"),
            endpoints={"local": config.EndpointBlock(name="local", type="local", path="/tmp/test")},
            conflict=config.ConflictBlock(
                policy="newest",
                merge_text_files=False,
                merge_fallback="manual"
            ),
            ignore=config.IgnoreBlock(patterns=[".git"]),
        )

        # Serialize to TOML
        toml_text = config.profile_to_toml(original)

        # Save to file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as tmp:
            tmp.write(toml_text)
            tmp_path = Path(tmp.name)

        try:
            # Load back
            loaded = config.load_profile_from_path(tmp_path)

            # Verify merge settings match
            self.assertEqual(loaded.conflict.merge_text_files, original.conflict.merge_text_files)
            self.assertEqual(loaded.conflict.merge_fallback, original.conflict.merge_fallback)
            self.assertEqual(loaded.conflict.policy, original.conflict.policy)
        finally:
            tmp_path.unlink()


if __name__ == "__main__":
    unittest.main()
